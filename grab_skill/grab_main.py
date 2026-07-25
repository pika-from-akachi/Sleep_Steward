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

import argparse, re, time, sys, json, subprocess
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
MID_POSE_FILE = Path("/root/grab_skill/calibration/mid_pose.json")
PLACE_POSE_FILE = Path("/root/grab_skill/calibration/place_pose.json")
DEFAULT_OBSERVE = [1.51, -0.20, -2.757, 1.67, 2.757, 0.363, -0.773]

GRIPPER_TOOL_LEN = 0.13   # 夹爪尖端在 flange 下方的垂直距离 (斜抓投影; 0.12偏低0.14偏高, 取0.13)
GRASP_DESCEND = 0.10      # approach → grasp 下抓行程 (m, 夹爪尖端从物体上方下到物体)
# 斜抓几何补偿 [dx, dy, dz] (实测微调得到, 下次自动对准, 不用手动微调)
GRASP_OFFSET = [-0.06, 0.01, -0.06]
PLACE_OFFSET = [-0.05, -0.03, 0.0]   # 放置点偏置
GRASP_SPEED = 15
GRIPPER_OPEN = 0.07
# 抓取朝向 [roll,pitch,yaw] (基座系, +Y前+Z上)
# ⚠️ 固件 IK 对 pitch 挑剔: 观测朝向 pitch=1.305 (接近 π/2 奇异边界) 被 REACH 拒绝;
#    pitch=1.0 接受 (diag_approach2 验证全高度可达)。夹爪斜前下 ~57° 抓取。
#    如夹不稳再微调 (试 pitch=0.9/1.1, 保持远离 ±π/2)
GRASP_RPY = [1.094, 1.0, 1.402]   # 已验证能下降的朝向


def activate_can():
    subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
    time.sleep(0.5)


def load_observe_pose():
    """加载观测姿态 (标定基准, 相机能看到桌面)"""
    if OBSERVE_FILE.exists():
        return list(json.loads(OBSERVE_FILE.read_text())["joints"])
    print("[Observe] ⚠️ 无 base_pose.json, 用默认观测姿态")
    return list(DEFAULT_OBSERVE)


def load_mid_pose(fallback):
    """加载示教中间位置, 不存在则返回 fallback"""
    if MID_POSE_FILE.exists():
        return list(json.loads(MID_POSE_FILE.read_text())["joints"])
    print("[MidPose] ⚠️ 无 mid_pose.json, 用回退姿态")
    return list(fallback)


def load_place_pose():
    """加载示教放置位置, 不存在返回 None"""
    if PLACE_POSE_FILE.exists():
        fp = json.loads(PLACE_POSE_FILE.read_text())["flange"]
        print(f"[PlacePose] 固定放置点: x={fp[0]:.3f} y={fp[1]:.3f} z={fp[2]:.3f}")
        return [fp[0], fp[1], fp[2]]
    return None


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


def get_depth_robust(depth_map, cx, cy, bbox_norm=None, inner_radius=8, outer_radius=25):
    """物体区域鲁棒深度估计 (多区域 + 离群值剔除)

    策略:
      1) 先用小半径 (inner) 取物体中心的深度 → 大概率命中物体表面
      2) 再用大半径 (outer) 取邻域深度 → 检测环境一致性
      3) 如果内圈深度与外圈差 > 阈值 → 可能在边缘, 回退到更大范围搜索
      4) 可选: 如果提供 bbox, 优先在 bbox 中心 30% 区域内搜索

    Args:
        depth_map: HxW float32 深度图 (米)
        cx, cy: 物体中心像素
        bbox_norm: 可选 [x1,y1,x2,y2] 归一化 bbox
        inner_radius: 内圈半径 (像素)
        outer_radius: 外圈半径 (像素)

    Returns:
        depth_meters: 物体深度 (米), 0.0 表示无效
    """
    h, w = depth_map.shape

    # 如果提供了 bbox, 在 bbox 中心区域内采样 (避开边缘)
    if bbox_norm is not None:
        x1 = int(bbox_norm[0] * w)
        y1 = int(bbox_norm[1] * h)
        x2 = int(bbox_norm[2] * w)
        y2 = int(bbox_norm[3] * h)
        # 缩到中心 40% 区域 (避开 bbox 边缘)
        margin_x = int((x2 - x1) * 0.3)
        margin_y = int((y2 - y1) * 0.3)
        bx1, bx2 = max(x1 + margin_x, 0), min(x2 - margin_x, w)
        by1, by2 = max(y1 + margin_y, 0), min(y2 - margin_y, h)
        if bx2 > bx1 and by2 > by1:
            region = depth_map[by1:by2, bx1:bx2]
            valid = region[(region > 0.05) & (region < 5.0)]
            if len(valid) >= 10:
                # 使用 10%-90% 截尾均值 (抗离群值)
                lo, hi = np.percentile(valid, [10, 90])
                trimmed = valid[(valid >= lo) & (valid <= hi)]
                if len(trimmed) >= 5:
                    return float(np.median(trimmed))

    # 回退: 围绕中心点的同心圆采样
    r1 = max(cy - inner_radius, 0)
    r2 = min(cy + inner_radius + 1, h)
    c1 = max(cx - inner_radius, 0)
    c2 = min(cx + inner_radius + 1, w)
    inner = depth_map[r1:r2, c1:c2]
    inner_valid = inner[(inner > 0.05) & (inner < 5.0)]

    if len(inner_valid) >= 5:
        inner_med = float(np.median(inner_valid))
        # 检查内圈深度一致性 (std 太大说明在边缘)
        inner_std = float(np.std(inner_valid))
        if inner_std < 0.05:  # < 5cm std → 可靠
            return inner_med

        # std 较大: 取截尾均值
        lo, hi = np.percentile(inner_valid, [15, 85])
        trimmed = inner_valid[(inner_valid >= lo) & (inner_valid <= hi)]
        if len(trimmed) >= 3:
            return float(np.median(trimmed))

    # 最后回退: 标准中位数 (原逻辑)
    return get_depth_median(depth_map, cx, cy, radius=outer_radius)


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


def interactive_fine_tune(arm, base_xy, above_z, rpy6, grasp_z0):
    """交互式 XYZ 三方向微调 — 在物体上方用相对位移精确对准。

    每次输入立即执行小幅 move_l 移动, 机械臂实时响应, 方便目视确认。

    命令格式:
      x+0.01    X方向+1cm  (基座系 +Y=前, +X=右)
      x-0.005   X方向-0.5cm
      y+0.01    Y方向+1cm
      y-0.005   Y方向-0.5cm
      z+0.01    抓取深度+1cm (夹爪更高 → 抓更浅)
      z-0.01    抓取深度-1cm (夹爪更低 → 抓更深)
      +0.01     等同于 z-0.01 (简写: 正数=下压更深, 常用)
      Enter     确认当前位姿, 开始下降抓取
      q / quit  放弃本次抓取

    返回值: (xy_final, grasp_z_final) 或 (None, None) 表示放弃
    """
    offset_x, offset_y, offset_z = 0.0, 0.0, 0.0
    grasp_z = grasp_z0

    print("\n" + "─" * 50)
    print("  🎮 XYZ 微调模式")
    print("  命令: x±/y±/z± 单位米 | +0.01=下压1cm | Enter=确认 | q=放弃")
    print("─" * 50)

    while True:
        # 显示当前状态
        cur_x = base_xy[0] + offset_x
        cur_y = base_xy[1] + offset_y
        print(f"\n  📍 TCP: x={cur_x:.4f} y={cur_y:.4f} z={above_z:.4f} | "
              f"偏移: dx={offset_x:+.4f} dy={offset_y:+.4f} | 抓取深度: {grasp_z:.4f}")

        ans = input("  🎯 微调 > ").strip()

        if ans == "":
            print("  ✅ 确认, 开始下降抓取")
            break
        if ans.lower() in ("q", "quit", "exit"):
            print("  ❌ 放弃抓取")
            return None, None

        # 解析: ±0.01 简写 → 视为 z- (正数=下压更深)
        simple = re.match(r'^([+-]\d+\.?\d*)$', ans)
        if simple:
            delta = float(simple.group(1))
            grasp_z += delta  # +0.01 → 下压1cm
            print(f"  → 抓取深度调整: grasp_z={grasp_z:.4f} (偏移{delta:+.4f}m)")
            continue

        # 解析: 方向+偏移量 (如 x+0.01, y-0.005, z+0.02)
        m = re.match(r'([xyz])\s*([+-]\d+\.?\d*)', ans.lower())
        if not m:
            print("  ⚠️ 无法识别, 可用: x+0.01 / y-0.005 / z+0.02 / +0.01 / Enter / q")
            continue

        axis, delta = m.group(1), float(m.group(2))

        if axis == 'z':
            # Z 偏移: 直接改抓取深度, 不动臂 (在 safety height 调 Z 无意义)
            grasp_z += delta
            print(f"  → 抓取深度: grasp_z={grasp_z:.4f} (偏移{delta:+.4f}m)")
            continue

        # X/Y 偏移: 更新偏移量, 并移动臂到新位置
        idx = {'x': 0, 'y': 1}[axis]
        if idx == 0:
            offset_x += delta
        else:
            offset_y += delta

        # 安全检查: 不超出工作空间
        new_x = base_xy[0] + offset_x
        new_y = base_xy[1] + offset_y
        if abs(new_x) > 0.28:
            print(f"  ⚠️ x={new_x:.3f} 超出安全范围 (±0.28m), 已回退")
            if idx == 0:
                offset_x -= delta
            else:
                offset_y -= delta
            continue
        if new_y < 0.22 or new_y > 0.52:
            print(f"  ⚠️ y={new_y:.3f} 超出安全范围 (0.22~0.52m), 已回退")
            if idx == 0:
                offset_x -= delta
            else:
                offset_y -= delta
            continue

        # 执行小幅移动
        target = [new_x, new_y, above_z, *rpy6]
        try:
            print(f"  → 移动到 x={new_x:.4f} y={new_y:.4f} z={above_z:.4f}")
            arm.move_linear(target, speed_pct=8, timeout=8.0)
        except Exception as e:
            print(f"  ⚠️ 移动失败: {e}")
            if idx == 0:
                offset_x -= delta
            else:
                offset_y -= delta

    return ([base_xy[0] + offset_x, base_xy[1] + offset_y], grasp_z)


def main():
    parser = argparse.ArgumentParser(description="云端视觉抓取 (眼在手上)")
    parser.add_argument("--object", "-o", required=True)
    parser.add_argument("--camera", "-c", default="dabai_dc1")
    parser.add_argument("--detect-only", action="store_true", help="仅检测, 不连臂")
    parser.add_argument("--dry-run", action="store_true", help="连臂+定位+规划, 不抓")
    parser.add_argument("--yes", action="store_true", help="跳过抓取前确认 (熟练后用)")
    parser.add_argument("--enable-depth", action="store_true", help="启用深度 (3D定位)")
    parser.add_argument("--place", "-p", type=str, default=None,
                        help="放置目标描述 (如 '黄色胶带'), 启用抓取+放置模式")
    parser.add_argument("--filter-frames", type=int, default=5,
                        help="深度时域滤波帧数 (3-7, 越多噪声越低但延迟越大; 默认5)")
    parser.add_argument("--grasp-rpy", type=str, default=None,
                        help="抓取朝向 [roll,pitch,yaw] 基座系, 如 '0,0,0'=垂直下")
    args = parser.parse_args()
    # 默认朝向已通过 parser default 设置

    detect_only = args.detect_only
    do_grasp = not args.dry_run and not detect_only
    # eye-in-hand: 相机装在臂上, 必须臂到观测姿态才有正确视野 → detect-only 也连臂
    need_arm = True
    if need_arm:
        activate_can()   # 任何需要臂的模式都要先激活 CAN (dry-run/detect-only/实抓)

    if do_grasp:
        pass  # CAN 已在 need_arm 时激活

    detector = CloudDetector(STEPFUN_API_KEY)
    observe = load_observe_pose()
    mid_pose = load_mid_pose(observe)  # 中间位置, 不存在则用观测姿态
    cam_mount = cam_mount_xyzrpy()
    print("=" * 60)
    print(f"🎯 {args.object} | 📷 {args.camera} | 深度={'on' if args.enable_depth else 'off'}")
    if args.enable_depth:
        print(f"   时域滤波: {args.filter_frames} 帧 | 对齐模式: depth_registration")
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
            if args.enable_depth:
                print(f"\n[1] 捕获 RGB-D (时域滤波 {args.filter_frames} 帧)...")
                rgb, depth, K = cam.capture_filtered(
                    num_frames=args.filter_frames, timeout=8.0)
            else:
                print("\n[1] 捕获 RGB...")
                rgb, depth, K = cam.capture(timeout=5.0)
            # ⚠️ 关键: 采图瞬间读 flange 位姿, 眼在手上相机随臂动
            if need_arm:
                flange_at_capture = arm.get_flange_pose()
            # 保存 RGB-D 叠加图用于诊断对齐质量
            if depth is not None:
                cam.save_alignment_check(rgb, depth, "/tmp/depth_alignment.png")

        if rgb is None:
            print("❌ RGB 采集失败"); sys.exit(1)
        h, w = rgb.shape[:2]
        print(f"  分辨率: {w}x{h}")
        if depth is not None:
            valid = depth[depth > 0]
            if len(valid) > 0:
                print(f"  深度: {valid.min():.2f}~{valid.max():.2f}m "
                      f"(中位={np.median(valid):.3f}m, 有效={(depth > 0).sum()}/{depth.size})")
            else:
                print("  深度: 全 0 (无有效深度)")
        else:
            print("  深度: 不可用")
        if K is not None:
            print(f"  内参: fx={K[0,0]:.1f} fy={K[1,1]:.1f} "
                  f"cx={K[0,2]:.1f} cy={K[1,2]:.1f}")
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

        # ── [2b] 放置目标 (固定示教优先) ──
        place_pos_base = load_place_pose()
        if place_pos_base is not None:
            print(f"\n[2b] 放置点: 使用固定示教位置")
        elif args.place:
            print(f"\n[2b] 云端 VLM: 放置点 '{args.place}'...")
            p_bbox, p_center, p_label = detector.detect(rgb, args.place)
            if p_bbox is None:
                print(f"  ⚠️ 未找到 '{args.place}', 只抓取不放置")
            else:
                cv2.rectangle(vis, (int(p_bbox[0]*w), int(p_bbox[1]*h)),
                              (int(p_bbox[2]*w), int(p_bbox[3]*h)), (255,0,0), 2)
                cv2.circle(vis, p_center, 5, (255,0,0), -1)
                cv2.putText(vis, p_label, (int(p_bbox[0]*w), max(int(p_bbox[1]*h)-10,20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,0,0), 2)
                print(f"  ✅ 放置点: {p_label} | center={p_center}")
                p_depth = get_depth_robust(depth, p_center[0], p_center[1], bbox_norm=p_bbox)
                if p_depth > 0:
                    p_cam = pixel_to_camera_3d(p_center[0], p_center[1], p_depth, K)
                    place_pos_base = eye_in_hand_to_base(p_cam, flange_at_capture, cam_mount)
                    place_pos_base[0] += PLACE_OFFSET[0]
                    place_pos_base[1] += PLACE_OFFSET[1]
                    place_pos_base[2] += PLACE_OFFSET[2]
                    print(f"  放置点基座系: {[round(v,3) for v in place_pos_base]}")
                else:
                    print("  ⚠️ 放置点深度无效, 只抓取不放置")
            cv2.imwrite("/tmp/grab_detection.jpg", vis)

        if detect_only:
            print("\n✅ 检测完成 (--detect-only)"); sys.exit(0)
        if depth is None:
            print("\n⚠️ 深度不可用 (加 --enable-depth), 仅完成视觉检测"); sys.exit(0)
        if flange_at_capture is None:
            print("❌ 无 flange 位姿, 无法做眼在手上变换"); sys.exit(1)

        # ── [3] 抓取3D定位 ──
        print(f"\n[3] 3D 定位 (眼在手上, 时域滤波depth)...")
        depth_val = get_depth_robust(depth, center_uv[0], center_uv[1],
                                     bbox_norm=bbox)
        if depth_val <= 0:
            print("❌ 深度无效 (物体区域无有效深度 — 可能 RGB/depth 不对齐或超出深度范围)")
            print("   提示: 检查 /tmp/depth_alignment.png 查看 RGB-D 叠加图")
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

        # 抓取朝向: CLI可覆盖, 默认用观测姿态的flange朝向
        if args.grasp_rpy:
            grasp_rpy = [float(x) for x in args.grasp_rpy.split(",")]
        else:
            grasp_rpy = list(GRASP_RPY)
        # 如果观测姿态的flange朝向可用, 优先用它 (自动避开π/2奇异)
        if need_arm:
            obs_fp = arm.get_flange_pose()
            if obs_fp:
                grasp_rpy = list(obs_fp[3:])
                # pitch 离 π/2 太近 → IK 无解, 自动压 0.1
                if abs(abs(grasp_rpy[1]) - 1.57) < 0.1:
                    grasp_rpy[1] = 1.4 if grasp_rpy[1] > 0 else -1.4
        print(f"  抓取朝向 rpy={[round(v,3) for v in grasp_rpy]}")

        # ── [4] 规划 ──
        approach_pose, grasp_pose = compute_grasp_pose(pos_base, grasp_rpy)
        print(f"\n[4] 抓取规划:")
        print(f"  预抓取(TCP): {[round(v,3) for v in approach_pose]}")
        print(f"  抓取点(TCP): {[round(v,3) for v in grasp_pose]}")

        if args.dry_run:
            print("\n✅ 模拟完成 (--dry-run, 未执行抓取)"); sys.exit(0)

        # ── [5] 执行抓取 ──
        print(f"\n[5] 执行抓取...")
        import threading as _th
        try:
            rpy6 = approach_pose[3:]
            grasp_pose_full = list(grasp_pose)

            # 1. 到物体上方 (XY到位, Z高10cm, 停住微调)
            above_z = grasp_pose_full[2] + 0.10
            xy_rpy = [grasp_pose_full[0], grasp_pose_full[1], above_z] + list(rpy6)
            print(f"  → 到物体上方 (z={above_z:.3f})")
            try:
                arm.move_to_pose(xy_rpy, speed_pct=GRASP_SPEED,
                                 safe_z_first=False, timeout=15.0)
                fp = arm.get_flange_pose()
                if fp: print(f"    到达 z={fp[2]:.3f}")
            except Exception as e:
                print(f"  ❌ 失败: {e}"); sys.exit(1)

            # 2. 在物体上方交互微调 (臂在物体上方, 目视参照)
            if not args.yes:
                xy_final, new_grasp_z = interactive_fine_tune(
                    arm, grasp_pose_full[:2], above_z, list(rpy6), grasp_pose_full[2])
                if xy_final is None:
                    print("放弃"); sys.exit(0)
                grasp_pose_full[0], grasp_pose_full[1] = xy_final[0], xy_final[1]
                grasp_pose_full[2] = new_grasp_z

            # 3. Z下降 (move_p + 等臂停稳 + 验证Z确实降了)
            print(f"  → Z下降 (到 z={grasp_pose_full[2]:.3f})")
            try:
                arm.move_to_pose(grasp_pose_full, speed_pct=10,
                                 safe_z_first=False, timeout=15.0)
            except Exception as e:
                print(f"  ❌ 下降失败: {e}"); sys.exit(1)
            time.sleep(0.5)  # 等臂停稳
            fp = arm.get_flange_pose()
            if fp:
                print(f"    当前 z={fp[2]:.3f}")
                if fp[2] > above_z - 0.01:
                    # move_p静默失败, 用关节插值再试
                    print("    ⚠️ move_p未降, 尝试关节方式...")
                    jj = arm.get_joint_angles()
                    if jj:
                        for s in range(15):
                            jj[1] += 0.03
                            jj[1] = min(jj[1], 2.5)
                            try:
                                arm.move_joints(jj, speed_pct=8, timeout=4.0)
                                fp2 = arm.get_flange_pose()
                                if fp2 and fp2[2] < above_z - 0.01:
                                    print(f"    ✅ 关节下降 z={fp2[2]:.3f}")
                                    break
                            except Exception:
                                break

            # 4. 夹爪闭合 + 持续 hold (防止运动中松开)
            print(f"  🤏 夹取")
            arm.gripper_close()
            time.sleep(0.5)
            _holding = True
            def _hold_gripper():
                while _holding:
                    try: arm._gripper.move_gripper_m(0.0)
                    except: pass
                    time.sleep(0.3)
            _ht = _th.Thread(target=_hold_gripper, daemon=True)
            _ht.start()

            # 5. 去中间位置 (夹持物体)
            print(f"  → 去中间位置 (夹持物体中)")
            for _att in range(3):
                try:
                    arm.move_joints(mid_pose, speed_pct=20, timeout=60)
                    break
                except Exception as e:
                    print(f"  ⚠️ 去中间位置失败 (尝试 {_att+1}/3): {e}")
                    if _att < 2:
                        time.sleep(1)

            # 6. 放置 或 松爪
            if place_pos_base is not None:
                # 到放置点上方, 不下降直接投放
                place_desc = args.place or "固定示教位置"
                print(f"\n  📍 放置: '{place_desc}' 位置=({place_pos_base[0]:.3f}, {place_pos_base[1]:.3f})")
                cur = arm.get_flange_pose()
                if cur: print(f"     当前 flange=({cur[0]:.3f}, {cur[1]:.3f}, {cur[2]:.3f})")
                if not args.yes:
                    input("  👀 夹持中, Enter=去放置点上方投放: ")
                place_xy = [place_pos_base[0], place_pos_base[1]]
                DROP_Z = 0.35
                placed = False
                try:
                    print(f"  → 移动到放置点上方 (z={DROP_Z})")
                    arm.move_to_pose([place_xy[0], place_xy[1], DROP_Z, *rpy6],
                                     speed_pct=12, safe_z_first=False, timeout=15.0)
                    placed = True
                except Exception as e:
                    print(f"  ⚠️ 移动失败: {e}, 不松爪")
                if placed:
                    # 在放置点上方交互微调
                    place_xy_final, _ = interactive_fine_tune(
                        arm, place_xy, DROP_Z, list(rpy6), DROP_Z)
                    if place_xy_final is None:
                        print("  放弃放置, 回观测")
                    else:
                        input("  👀 对准完成, Enter=松爪: ")
                    _holding = False
                    _ht.join(timeout=1)
                    print(f"  → 松爪 (投放)")
                    arm.gripper_open(GRIPPER_OPEN)
                    time.sleep(0.8)
                # 松爪后回中间位置
                print(f"  → 回中间位置")
                for _att in range(3):
                    try:
                        arm.move_joints(mid_pose, speed_pct=20, timeout=60)
                        break
                    except Exception:
                        if _att < 2: time.sleep(1)
            else:
                # 普通模式: 已在中间位置
                if not args.yes:
                    input(f"\n  👀 已到中间位置, 物体夹持中. Enter=松爪: ")
                _holding = False
                _ht.join(timeout=1)
                print(f"  → 放开夹爪")
                arm.gripper_open(GRIPPER_OPEN)
                time.sleep(0.8)
            print("\n✅ 完成: 到上方 → XYZ微调 → 下降 → 夹取 → 回观测 → 松爪")

        except Exception as e:
            print(f"\n❌ 失败: {e}")
            import traceback; traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
