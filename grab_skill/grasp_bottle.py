"""第一次抓取测试 (眼在手上, path A)。
流程: 回观测→检测瓶子→定位 p_base→张开夹爪→移动 TCP 到抓取位姿→闭合。
抓取位姿 = p_base 沿夹爪前方退后 GRIPPER_OFFSET (让夹持点到达瓶子)。
低速 + safe_z。⚠️ 臂会大幅运动到桌面瓶子处, 现场盯着, 手放急停!
用法: python3 grasp_bottle.py [目标名] [gripper_offset]
"""
import sys, time, json
import numpy as np
from arm_control import NeroArm
from camera import StereoCamera
from detector import CloudDetector
from transforms import eye_in_hand_to_base, cam_mount_xyzrpy, xyzrpy_to_matrix

OBS = json.load(open('/root/grab_skill/observation_pose.json'))
STEPFUN = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"
target = sys.argv[1] if len(sys.argv) > 1 else "红盖水瓶"
GRIPPER_OFFSET = float(sys.argv[2]) if len(sys.argv) > 2 else 0.12  # flange→夹持点, 可调


def to_obs(arm, obs, speed=10, step=0.25):
    try: arm._arm.clear_joint_error()
    except Exception: pass
    cur = list(arm.get_joint_angles()[:7]); tgt = list(obs[:7])
    for it in range(60):
        d = [tgt[i] - cur[i] for i in range(7)]; md = max(abs(x) for x in d)
        if md < 0.05: return True
        m = [cur[i] + max(-step, min(step, d[i])) for i in range(7)]
        try: arm.move_joints(m, speed_pct=speed)
        except Exception as e: print("  回观测失败:", e); return False
        cur = list(arm.get_joint_angles()[:7])
    return False


arm = NeroArm(); arm.connect(); arm.enable()
print("[1/6] 回观测姿态"); to_obs(arm, OBS)
tcp = arm.get_tcp_pose()
print(f"      TCP={[round(v,3) for v in tcp]}")

print(f"[2/6] 采图 + VLM 检测 '{target}' (透明瓶深度可能要重试几次)")
det = CloudDetector(STEPFUN)
p_base = None
with StereoCamera(camera_model="dabai_dc1", enable_depth=True) as cam:
    time.sleep(2)
    for attempt in range(4):
        rgb, depth, K = cam.capture(timeout=12.0)
        if rgb is None or depth is None:
            continue
        bbox, center, label = det.detect(rgb, target)
        if bbox is None:
            print(f"  尝试{attempt+1}/4: 没找到 '{target}'"); continue
        cx, cy = center
        h, w = depth.shape
        bx1, by1, bx2, by2 = int(bbox[0]*w), int(bbox[1]*h), int(bbox[2]*w), int(bbox[3]*h)
        rg = depth[max(0, by1):by2, max(0, bx1):bx2]   # 整个 bbox 取深度
        rv = rg[(rg > 0.05) & (rg < 5)]
        d = float(np.median(rv)) if len(rv) >= 5 else 0.0
        print(f"  尝试{attempt+1}/4: center={center} bbox深度中位={d:.3f}m (有效点{len(rv)})")
        if d > 0:
            fx, fy, cxK, cyK = K[0,0], K[1,1], K[0,2], K[1,2]
            p_cam = np.array([(cx-cxK)*d/fx, (cy-cyK)*d/fy, d])
            p_base = eye_in_hand_to_base(p_cam, tcp, cam_mount_xyzrpy())
            break
        time.sleep(0.5)
if p_base is None:
    print("      ❌ 多次重试深度都无效 (透明瓶? 强烈建议换不透明物体: 易拉罐/纸盒)"); arm.disconnect(); sys.exit(1)
print(f"      瓶子 p_base={np.round(p_base,3).tolist()}")

print("[3/6] 算抓取位姿")
R = xyzrpy_to_matrix(tcp)[:3, :3]
approach = R[:, 2]                                   # TCP+Z 在基座系 = 夹爪前方
flange_target = p_base - GRIPPER_OFFSET * approach   # flange 退后, 让夹持点到瓶子
grasp_pose = [float(flange_target[0]), float(flange_target[1]), float(flange_target[2]),
              tcp[3], tcp[4], tcp[5]]
print(f"      抓取位姿(flange)={[round(v,3) for v in grasp_pose]}  offset={GRIPPER_OFFSET}")

print("[4/6] 张开夹爪")
arm.init_gripper(); arm.gripper_open(0.07)

print("[5/6] 移动到瓶子 (speed 8%, safe_z 先抬升) —— 🔴 盯着臂!")
try:
    arm.move_to_pose(grasp_pose, speed_pct=8)
except Exception as e:
    print("      ❌ 运动失败 (可能不可达/超时):", e); arm.disconnect(); sys.exit(1)

print("[6/6] 闭合夹爪"); arm.gripper_close()
print("=== 抓取动作完成, 看夹住没 ===")
arm.disconnect()  # 不下使能
