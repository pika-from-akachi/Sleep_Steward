"""眼在手上 变换工具 (A 路线 — 直连 pyAgxArm, 不依赖 MoveIt/mock)。

核心公式:
    p_base = T_base_flange · T_flange_cam · p_cam
  - p_cam          物体在相机光学系的坐标 (深度+内参算出; +X右 +Y下 +Z前)
  - T_base_flange  flange(link7) 在基座系的位姿, 由 arm.get_flange_pose() 读出
  - T_flange_cam   相机相对 flange 的固定安装变换 (实测, 可调; 见 CAM_MOUNT)

RPY 约定 (单点标定实测): R = Rz(roll)·Rx(pitch)·Ry(yaw)。
基座系: +Y=前方, +Z=上方 (注意不是 +X 前!)。
"""
import numpy as np


def rpy_to_matrix(roll, pitch, yaw):
    """RPY -> 3x3 旋转矩阵。
    约定 (pyAgxArm Nero API 文档): R = Rz(yaw)·Ry(pitch)·Rx(roll)
    (roll/pitch/yaw 分别绕 X/Y/Z; pitch∈[-π/2,π/2])。基座系: +Y=前, +Z=上。"""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])   # yawabout Z
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])   # pitch about Y
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])   # roll about X
    return Rz @ Ry @ Rx


def xyzrpy_to_matrix(xyzrpy):
    """[x,y,z,roll,pitch,yaw] -> 4x4 齐次矩阵"""
    T = np.eye(4)
    T[:3, :3] = rpy_to_matrix(xyzrpy[3], xyzrpy[4], xyzrpy[5])
    T[:3, 3] = xyzrpy[:3]
    return T


def eye_in_hand_to_base(p_cam, flange_xyzrpy, cam_xyzrpy):
    """物体: 相机光学系 -> 基座系 (眼在手上)。

    Args:
        p_cam: [x,y,z] 相机光学系坐标 (米)
        flange_xyzrpy: get_flange_pose() 返回的 [x,y,z,roll,pitch,yaw]
        cam_xyzrpy: 相机安装变换 [x,y,z,roll,pitch,yaw] (flange 系下, 见 CAM_MOUNT)
    Returns:
        [x,y,z] 基座系坐标 (米)
    """
    T_bf = xyzrpy_to_matrix(flange_xyzrpy)
    T_fc = xyzrpy_to_matrix(cam_xyzrpy)
    p = np.array([p_cam[0], p_cam[1], p_cam[2], 1.0])
    return (T_bf @ T_fc @ p)[:3]


# ─── 相机相对 flange(link7/TCP) 的安装变换 ─────────────────────────
# 单点标定实测 (TCP 系): 相机在 flange 前方 ~10cm (沿 TCP+Z=approach), 小侧偏。
# 光学系与 TCP 系对齐 (光学 +Z = TCP +Z = 夹爪前方)。
# ⚠️ 单点标定, 在观测姿态附近准确; 其它姿态/视野边缘可能有残差, 需多点再精校。
CAM_MOUNT = {
    "xyz": [0.0312, 0.0681, -0.0263],       # TCP 系: x,y,z (米)
    "rpy": [-2.2851, -1.5502, -1.1256],             # [roll,pitch,yaw], R=Rz(yaw)·Ry(p)·Rx(r)
}

# 抓取姿态 (flange/TCP 在基座系的姿态): 夹爪朝向物体
# 这个值要按实际夹爪安装方向定, 先用估计, 实测调整
GRASP_ORIENTATION = [0.0, 0.0, 0.0]     # [roll,pitch,yaw], 待定


def cam_mount_xyzrpy():
    return list(CAM_MOUNT["xyz"]) + list(CAM_MOUNT["rpy"])
