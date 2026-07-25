"""
云端视觉抓取主程序 — 眼在手上 (camera on flange)
流程: 观测姿态 → RGB-D 捕获 → 云端VLM检测 → 深度3D定位 → 手眼变换 → 笛卡尔抓取

坐标变换链 (眼在手上):
    p_base = T_base_flange · T_flange_cam · p_cam
  - p_cam          像素+深度+内参 → 相机光学系 (+X右 +Y下 +Z前)
  - T_flange_cam   来自手眼标定 (transforms.py 的 CAM_MOUNT)
  - T_base_flange  实时读 arm.get_flange_pose()  ← 采图瞬间必须读, 相机随臂动!

用法:
    source /opt/ros/humble/setup.bash
    # 仅检测 (不连臂, 不抓)
    python3 grab_main.py --object "黄色罐子" --detect-only
    # 模拟 (连臂+定位+规划, 但不执行抓取)
    python3 grab_main.py --object "饮料瓶" --dry-run --enable-depth
    # 实抓
    python3 grab_main.py --object "饮料瓶" --enable-depth
"""

import argparse, time, sys, json, subprocess
from contextlib import nullcontext
from pathlib import Path
import cv2, numpy as np

from camera import StereoCamera
from detector import CloudDetector
from arm_control import NeroArm
from transforms import eye_in_hand_to_base, cam_mount_xyzrpy

# ─── 配置 ────────────────────────────────────────────────
STEPFUN_API_KEY = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"

# 观测姿态 (相机俯视桌面, 能看到物体) — 用标定基准姿态
OBSERVE_FILE = Path("/root/grab_skill/calibration/base_pose.json")
DEFAULT_OBSERVE = [1.51, -0.20, -2.757, 1.67, 2.757, 0.363, -0.773]

GRIPPER_TOOL_LEN = 0.13   # 夹爪尖端在 flange 下方的垂直距离 (斜抓投影; 0.12偏低0.14偏高, 取0.13)
GRASP_DESCEND = 0.10      # approach → grasp 下抓行程 (m, 夹爪尖端从物体上方下到物体)
# 斜抓几何补偿 [dx, dy, dz] (实测微调得到, 下次自动对准, 不用手动微调)
GRASP_OFFSET = [0.0, -0.03, -0.12]   # z: 固化 z-0.05 微调
GRASP_SPEED = 15
GRIPPER_OPEN = 0.07
# 抓取朝向 [roll,pitch,yaw] (基座系, +Y前+Z上)
# ⚠️ 固件 IK 对 pitch 挑剔: 观测朝向 pitch=1.305 (接近 π/2 奇异边界) 被 REACH 拒绝;
#    pitch=1.0 接受 (diag_approach2 验证全高度可达)。夹爪斜前下 ~57° 抓取。
#    如夹不稳再微调 (试 pitch=0.9/1.1, 保持远离 ±π/2)
GRASP_RPY = [1.094, 1.0, 1.402]


def activate_can():
    subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
    time.sleep(0.5)


def load_observe_pose():
    """加载观测姿态 (标定基准, 相机能看到桌面)"""
    if OBSERVE_FILE.exists():
        return list(json.loads(OBSERVE_FILE.read_text())["joints"])
    print("[Observe] ⚠️ 无 base_pose.json, 用默认观测姿态")
    return list(DEFAULT_OBSERVE)


def pixel_to_camera_3d(u, v, depth_m, K):
    """像素 + 深度 + 内参 → 相机光学系 3D 坐标 (+X右 +Y下 +Z前)"""
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    return np.array([(u - cx) * depth_m / fx, (v - cy) * depth_m / fy, depth_m])


def get_depth_median(depth_map, cx, cy, radius=15):
    """物体中心附近深度的中位数 (抗噪)"""
    h, w = depth_map.shape
    region = depth_map[max(0, cy - radius):min(h, cy + radius + 1),
                       max(0, cx - radius):min(w, cx + radius + 1)]
    valid = region[(region > 0.05) & (region < 5.0)]
    return float(np.median(valid)) if len(valid) >= 5 else 0.0


def compute_grasp_pose(pos_base, rpy):
    """物体位置 + 朝向 → (预抓取, 抓取) flange 位姿 [x,y,z,r,p,y]。
    move_p 目标是 flange, 但夹爪从 flange 往下伸 TOOL_LEN →
    grasp flange z = 物体z + TOOL_LEN (让夹爪尖端到物体);
    approach flange z 再高 DESCEND (尖端在物体上方)。"""
    grasp_z = pos_base[2] + GRIPPER_TOOL_LEN + GRASP_OFFSET[2]
    approach_z = grasp_z + GRASP_DESCEND
    approach = [pos_base[0]+GRASP_OFFSET[0], pos_base[1]+GRASP_OFFSET[1], approach_z]
    grasp = [pos_base[0]+GRASP_OFFSET[0], pos_base[1]+GRASP_OFFSET[1], grasp_z]
    return (approach + list(rpy), grasp + list(rpy))


def main():
    parser = argparse.ArgumentParser(description="云端视觉抓取 (眼在手上)")
    parser.add_argument("--object", "-o", required=True)
    parser.add_argument("--camera", "-c", default="dabai_dc1")
    parser.add_argument("--detect-only", action="store_true", help="仅检测, 不连臂")
    parser.add_argument("--dry-run", action="store_true", help="连臂+定位+规划, 不抓")
    parser.add_argument("--yes", action="store_true", help="跳过抓取前确认 (熟练后用)")
    parser.add_argument("--enable-depth", action="store_true", help="启用深度 (3D定位)")
    args = parser.parse_args()

    detect_only = args.detect_only
    do_grasp = not args.dry_run and not detect_only
    # eye-in-hand: 相机装在臂上, 必须臂到观测姿态才有正确视野 → detect-only 也连臂
    need_arm = True

    if do_grasp:
        activate_can()

    detector = CloudDetector(STEPFUN_API_KEY)
    observe = load_observe_pose()
    cam_mount = cam_mount_xyzrpy()
    print("=" * 60)
    print(f"🎯 {args.object} | 📷 {args.camera} | 深度={'on' if args.enable_depth else 'off'}")
    print(f"   观测姿态关节: {[round(j,2) for j in observe]}")
    print(f"   CAM_MOUNT(flange系) xyz={[round(v,4) for v in cam_mount[:3]]}")
    print("=" * 60)

    # 连臂 (detect-only 不连); 实抓退出/异常时 with 自动 disconnect
    with (NeroArm() if need_arm else nullcontext()) as arm:
        # ── [0] 去观测姿态 + 开夹爪 (必须在采图前, 相机视野取决于臂位姿) ──
        flange_at_capture = None
        if need_arm:
            print("\n[0] 去观测姿态 + 张开夹爪...")
            arm.move_joints(observe, speed_pct=15)
            if do_grasp:
                arm.init_gripper()
                arm.gripper_open(GRIPPER_OPEN)
            print("  ✅ 已到观测姿态")

        # ── [1] 捕获 RGB-D ──
        with StereoCamera(camera_model=args.camera, enable_depth=args.enable_depth) as cam:
            time.sleep(1.0)
            print("\n[1] 捕获 RGB-D...")
            rgb, depth, K = cam.capture(timeout=5.0)
            # ⚠️ 关键: 采图瞬间读 flange 位姿, 眼在手上相机随臂动
            if need_arm:
                flange_at_capture = arm.get_flange_pose()

        if rgb is None:
            print("❌ RGB 采集失败"); sys.exit(1)
        h, w = rgb.shape[:2]
        print(f"  分辨率: {w}x{h}")
        if depth is not None:
            print(f"  深度: {depth.min():.2f}~{depth.max():.2f}m")
        else:
            print("  深度: 不可用")
        if K is not None:
            print(f"  内参: fx={K[0,0]:.0f} fy={K[1,1]:.0f}")
        if need_arm and flange_at_capture:
            print(f"  flange: pos={np.round(flange_at_capture[:3],3).tolist()} "
                  f"rpy={np.round(flange_at_capture[3:],3).tolist()}")

        # ── [2] 检测 ──
        print(f"\n[2] 云端 VLM: '{args.object}'...")
        bbox, center_uv, label = detector.detect(rgb, args.object)
        if bbox is None:
            print(f"❌ 未找到 '{args.object}'"); sys.exit(1)

        vis = rgb.copy()
        cv2.rectangle(vis, (int(bbox[0]*w), int(bbox[1]*h)),
                      (int(bbox[2]*w), int(bbox[3]*h)), (0,255,0), 2)
        cv2.circle(vis, center_uv, 5, (0,0,255), -1)
        cv2.putText(vis, label, (int(bbox[0]*w), max(int(bbox[1]*h)-10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.imwrite("/tmp/grab_detection.jpg", vis)
        print(f"  ✅ {label} | bbox={[round(v,3) for v in bbox]} | center={center_uv}")

        if detect_only:
            print("\n✅ 检测完成 (--detect-only)"); sys.exit(0)
        if depth is None:
            print("\n⚠️ 深度不可用 (加 --enable-depth), 仅完成视觉检测"); sys.exit(0)
        if flange_at_capture is None:
            print("❌ 无 flange 位姿, 无法做眼在手上变换"); sys.exit(1)

        # ── [3] 3D 定位: 像素+深度 → 相机系 → 基座系 (手眼变换) ──
        print(f"\n[3] 3D 定位 (眼在手上)...")
        depth_val = get_depth_median(depth, center_uv[0], center_uv[1])
        if depth_val <= 0:
            print("❌ 深度无效 (物体区域无有效深度 — 可能 RGB/depth 不对齐或超出深度范围)")
            sys.exit(1)

        pos_cam = pixel_to_camera_3d(center_uv[0], center_uv[1], depth_val, K)
        pos_base = eye_in_hand_to_base(pos_cam, flange_at_capture, cam_mount)
        print(f"  深度={depth_val:.3f}m | 相机系={[round(v,3) for v in pos_cam]}")
        print(f"  基座系={[round(v,3) for v in pos_base]}  (物体在基座系位置)")
        # 工作空间预检 (NERO 臂展有限, 超范围 move_p 会 silent 拒绝 = 原地不动)
        if abs(pos_base[0]) > 0.25 or pos_base[1] > 0.48 or pos_base[1] < 0.25:
            print(f"  ⚠️ 物体可能超工作空间 (x={pos_base[0]:.2f}, y={pos_base[1]:.2f})")
            print(f"     推荐 |x|<0.25, y∈[0.25,0.48] (臂正前方 25~48cm, 左右±25cm)")
            print(f"     超范围 approach 会原地不动, 请把物体放近/居中")

        # 抓取朝向: 用固件 IK 接受的 GRASP_RPY (观测朝向 pitch=1.305 被拒, 用 pitch=1.0)
        grasp_rpy = list(GRASP_RPY)
        print(f"  抓取朝向 rpy={grasp_rpy} (固件 IK accept)")

        # ── [4] 规划 ──
        approach_pose, grasp_pose = compute_grasp_pose(pos_base, grasp_rpy)
        print(f"\n[4] 抓取规划:")
        print(f"  预抓取(TCP): {[round(v,3) for v in approach_pose]}")
        print(f"  抓取点(TCP): {[round(v,3) for v in grasp_pose]}")

        if args.dry_run:
            print("\n✅ 模拟完成 (--dry-run, 未执行抓取)"); sys.exit(0)

        # ── [5] 执行 ──
        print(f"\n[5] 执行抓取...")
        try:
            # 标准 approach: 先到物体正上方高位 → 在高空微调 xy 对准 → 纯竖直下降 → 夹
            # 关键: xy 微调在高空(z=0.42)进行, 水平移动不会碰倒物体; 下降时 xy 已固定, 纯竖直
            ABOVE_Z = 0.42   # 物体上方高位 (diag验证可达)
            rpy6 = approach_pose[3:]
            cur_xy = [approach_pose[0], approach_pose[1]]   # 微调 xy (高空)
            z_off = 0.0                                       # 微调夹取深度偏移
            print(f"  → 先到物体上方 (z={ABOVE_Z})")
            arm.move_to_pose([cur_xy[0], cur_xy[1], ABOVE_Z, *rpy6],
                             speed_pct=GRASP_SPEED, safe_z_first=False)
            if not args.yes:
                print(f"\n  在高空微调 xy 对准物体 (水平移安全, 不会碰倒):")
                while True:
                    print(f"  上方 xy=[{cur_xy[0]:.3f},{cur_xy[1]:.3f}]  夹取深度偏移 z={z_off:+.3f}")
                    ans = input("  Enter=竖直下降夹取 | 微调如 'x+0.02 y-0.01 z-0.04' | b=退回: ").strip().lower()
                    if ans == "":
                        break
                    if ans == "b":
                        print("  退回观测姿态"); arm.move_joints(observe, speed_pct=15); sys.exit(0)
                    dx = dy = dz = 0.0
                    for tok in ans.split():
                        if len(tok) >= 2 and tok[0] in "xyz":
                            try:
                                d = float(tok[1:])
                                if tok[0] == "x": dx = d
                                elif tok[0] == "y": dy = d
                                else: dz = d
                            except ValueError:
                                pass
                    if dx == dy == dz == 0:
                        print("  (无有效微调, 例: x+0.02)"); continue
                    cur_xy[0] += dx; cur_xy[1] += dy; z_off += dz
                    print(f"  ✓ 微调生效: xy=[{cur_xy[0]:.3f},{cur_xy[1]:.3f}]  z_off={z_off:+.3f} (影响下降深度)")
                    try:
                        arm.move_to_pose([cur_xy[0], cur_xy[1], ABOVE_Z, *rpy6],
                                         speed_pct=8, safe_z_first=False)
                    except Exception as e:
                        print(f"  ⚠️ 微调失败 ({e}), 试更小步长")
            # 纯竖直下降到夹取高度 (xy 已对准, 只降 z, 不碰物体)
            final_z = approach_pose[2] + z_off
            print(f"\n  → 竖直下降到夹取高度 (z={final_z:.3f}, 分步)")
            z = ABOVE_Z
            reached = ABOVE_Z
            while z > final_z + 0.005:
                z = max(final_z, z - 0.04)
                try:
                    arm.move_to_pose([cur_xy[0], cur_xy[1], z, *rpy6],
                                     speed_pct=8, safe_z_first=False)
                    reached = z
                    time.sleep(0.3)
                except Exception:
                    print(f"  ⚠️ z={z:.3f} 不可达 (工作空间下限), 停在 z={reached:.3f}")
                    if reached - final_z > 0.05:
                        print(f"  ❌ 夹取高度差 {reached-final_z:.2f}m 够不到物体 — 物体太靠边/太远")
                        print(f"     → 放居中 (|x|<0.15, y∈[0.30,0.45]), NERO 左/右边低 z 够不到")
                        arm.move_joints(observe, speed_pct=15); sys.exit(1)
                    print(f"  (差 {reached-final_z:.2f}m 较小, 继续尝试夹取)")
                    break
            # 夹取 (当前位置)
            print(f"  🤏 夹取 (z={final_z:.3f})")
            arm.gripper_close()
            # 抬起 (z+12cm)
            print(f"  → 抬起")
            lift = [cur_xy[0], cur_xy[1], final_z + 0.12, *rpy6]
            try:
                arm.move_to_pose(lift, speed_pct=GRASP_SPEED, safe_z_first=False)
            except Exception as e:
                print(f"  ⚠️ 抬起失败: {e}")
            # 回观测位置, 直接松开夹爪
            print(f"  → 回观测位置")
            arm.move_joints(observe, speed_pct=15)
            time.sleep(0.5)
            _fp = arm.get_flange_pose()
            if _fp:
                print(f"  ✋ 已回观测: flange=[{_fp[0]:.3f},{_fp[1]:.3f},{_fp[2]:.3f}]  (应为 ≈[-0.094,0.358,0.485])")
            print(f"  → 放开夹爪")
            arm.gripper_open(GRIPPER_OPEN)
            time.sleep(0.8)
            print("\n✅ 抓取完成, 回到观测姿态并松开")
        except Exception as e:
            print(f"\n❌ approach 失败: {e}")
            try:
                print(f"  物体基座系 xy=({pos_base[0]:.3f},{pos_base[1]:.3f})  "
                      f"approach=({approach_pose[0]:.3f},{approach_pose[1]:.3f},z={approach_pose[2]:.3f})")
            except Exception:
                pass
            print("  若 REACH_TARGET_POS_FAILED/超时: 物体可能在 NERO 工作空间边缘")
            print("    (太左/太右/太远/太近) → 试放到臂正前方居中 (左右±15cm, 前方 30~50cm)")
            import traceback; traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
