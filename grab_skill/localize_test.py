"""眼在手上定位验证 (不动臂): 读 flange 位姿 + 采深度 + 取一个有效深度点 → 算 base 坐标, 看是否合理。
臂需在已知姿态(如零位)且前方有物体。相机光学系: +X右 +Y下 +Z前。"""
import time
import numpy as np

from arm_control import NeroArm
from camera import StereoCamera
from transforms import eye_in_hand_to_base, cam_mount_xyzrpy, CAM_MOUNT

# 1. 读 flange(link7) 位姿 (臂保持当前姿态, 不动)
arm = NeroArm(); arm.connect(); arm.enable()
flange = arm.get_tcp_pose()
arm.disconnect()  # 不下使能
print("flange(link7) 位姿 [x,y,z,r,p,y]:", [round(v, 3) for v in flange])

# 2. 采一帧深度
with StereoCamera(camera_model="dabai_dc1", enable_depth=True) as cam:
    time.sleep(2)
    rgb, depth, K = cam.capture(timeout=12.0)
if depth is None:
    print("❌ 没采到深度"); raise SystemExit(1)

fx, fy = K[0, 0], K[1, 1]
cxK, cyK = K[0, 2], K[1, 2]
h, w = depth.shape
valid = depth > 0.05
n = int(valid.sum())
print(f"深度有效像素: {n}/{depth.size} ({n/depth.size*100:.1f}%)")
if n == 0:
    print("❌ 全帧无有效深度 (LDP? 镜头遮挡? 没物体?)"); raise SystemExit(1)

# 取图像中心附近一个有效深度点 (用中心 100x100 区域的中位有效深度 + 中心像素)
cy, cx = h // 2, w // 2
region = depth[max(0, cy-50):cy+50, max(0, cx-50):cx+50]
rv = region[region > 0.05]
d = float(np.median(rv)) if len(rv) else float(depth[valid].median())
# 用中心像素做方向 (近似)
p_cam = np.array([(cx - cxK) * d / fx, (cy - cyK) * d / fy, d])
print(f"取点: 像素({cx},{cy}) 深度≈{d:.3f}m → 相机光学系 p_cam={[round(v,3) for v in p_cam]}")

# 3. 眼在手上 → 基座系
p_base = eye_in_hand_to_base(p_cam, flange, cam_mount_xyzrpy())
print(f"\n基座系 p_base = [x前, y左, z高] = {[round(v,3) for v in p_base]} (米)")
print(f"当前 CAM_MOUNT: xyz={CAM_MOUNT['xyz']} rpy={CAM_MOUNT['rpy']}")
print("\n合理性判断: 物体应在臂前方(x>0)、桌面高度(z≈0~0.1)。若 x<0 或 z 异常 → CAM_MOUNT/约定要调。")
