"""标定工具: 先自动回到观测姿态, 再 VLM 检测目标 → 算基座系 p_base, 和实测对比。
用法: python3 calib_point.py "目标名"   例如: python3 calib_point.py "红色瓶子"
会从任意姿态分步回观测姿态(每步≤1.2rad, 自动、你盯着), 然后采图标定。"""
import sys, time, json
from pathlib import Path
import numpy as np

from arm_control import NeroArm
from camera import StereoCamera
from detector import CloudDetector
from transforms import eye_in_hand_to_base, cam_mount_xyzrpy, CAM_MOUNT

OBS_FILE = Path("/root/grab_skill/observation_pose.json")
STEPFUN_API_KEY = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"
target_name = sys.argv[1] if len(sys.argv) > 1 else "目标物体"


def move_to_observation(arm, obs, speed=10, step=0.25):
    """从任意姿态分步回到观测姿态 (小步+先清故障, 否则大步会触发 REACH_TARGET_POS_FAILED)。"""
    try:
        arm._arm.clear_joint_error()
    except Exception:
        pass
    cur = list(arm.get_joint_angles()[:7])
    tgt = list(obs[:7])
    for it in range(60):
        delta = [tgt[i] - cur[i] for i in range(7)]
        md = max(abs(d) for d in delta)
        if md < 0.05:
            print(f"  已到观测姿态 (步{it}, maxΔ={md:.3f}rad)"); return True
        move = [cur[i] + max(-step, min(step, delta[i])) for i in range(7)]
        if it % 5 == 0:
            print(f"  [回观测] 步{it+1}: maxΔ={md:.2f}rad")
        try:
            arm.move_joints(move, speed_pct=speed)
        except Exception as e:
            print("  运动失败:", e); return False
        cur = list(arm.get_joint_angles()[:7])
    print("  ⚠️ 步数耗尽未到位"); return False


# 1. 臂: 回观测姿态 + 读 TCP
arm = NeroArm(); arm.connect(); arm.enable()
if OBS_FILE.exists():
    obs = json.loads(OBS_FILE.read_text())
    print(f"目标观测姿态: {[round(t, 3) for t in obs]}")
    move_to_observation(arm, obs)
else:
    print("⚠️ 无 observation_pose.json, 用当前姿态标定")
tcp = arm.get_tcp_pose()
print("TCP 位姿 [x,y,z,r,p,y]:", [round(v, 3) for v in tcp])

# 2. 采 RGB-D + VLM 检测 (臂保持观测姿态 + 使能)
det = CloudDetector(STEPFUN_API_KEY)
with StereoCamera(camera_model="dabai_dc1", enable_depth=True) as cam:
    time.sleep(2)
    rgb, depth, K = cam.capture(timeout=12.0)
arm.disconnect()  # 采完断开 (不下使能, 臂保持观测姿态)
if rgb is None or depth is None:
    print("❌ 采图失败"); raise SystemExit(1)

bbox, center, label = det.detect(rgb, target_name)
if bbox is None:
    print(f"❌ VLM 没找到 '{target_name}'"); raise SystemExit(1)
print(f"VLM: {label} center 像素={center}")

# 3. 目标深度 + 相机系坐标
cx, cy = center
region = depth[max(0, cy - 12):cy + 12, max(0, cx - 12):cx + 12]
rv = region[(region > 0.05) & (region < 5.0)]
d = float(np.median(rv)) if len(rv) >= 3 else 0.0
if d <= 0:
    print("❌ 目标处深度无效"); raise SystemExit(1)
fx, fy, cxK, cyK = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
p_cam = np.array([(cx - cxK) * d / fx, (cy - cyK) * d / fy, d])
print(f"目标深度={d:.3f}m  p_cam={[round(v,3) for v in p_cam]}")

# 4. 眼在手上 → 基座系
p_base = eye_in_hand_to_base(p_cam, tcp, cam_mount_xyzrpy())
print(f"\n>>> 计算 p_base = [x,y,z] = {[round(v,3) for v in p_base]} (米)")
print(f"    CAM_MOUNT: xyz={CAM_MOUNT['xyz']} rpy={[round(x,3) for x in CAM_MOUNT['rpy']]}")
print("把你实测的目标基座系位置(x前 y侧 z高)告诉我, 我对比误差、调 CAM_MOUNT。")
