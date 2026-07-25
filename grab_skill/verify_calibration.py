"""验证手眼标定质量。

原理: ArUco 标记静止在桌上 → 用标定结果把标记从相机系换算到基座系,
      不同臂姿态下算出的「标记在基座系位置」应该一致。
      离散度 (标准差) < 1.5cm = 优秀, < 3cm = 可用, > 3cm = 建议重标。

公式: p_marker_base = T_base_flange · T_flange_cam · p_marker_cam
  - T_flange_cam   来自标定结果 (CAM_MOUNT)
  - T_base_flange  来自 arm.get_flange_pose()
  - p_marker_cam   来自 ArUco 检测的 tvec (标记在相机光学系)

用法: python3 verify_calibration.py
摆 5-8 个不同姿态, 每个按 Enter 采样, 按 q 结束看统计。
"""
import subprocess, time, sys, glob, os, json, termios, tty
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
import tf_transformations as tt
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

CALIB_DIR = "/root/grab_skill/calibration"
MARKER_ID, MARKER_SIZE = 0, 0.15   # 与打印标记一致
_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_DET = cv2.aruco.ArucoDetector(_DIC, cv2.aruco.DetectorParameters())
_OBJ = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                 [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)


def load_T_flange_cam():
    """读最新的标定 json, 返回 4x4 T_flange_cam"""
    files = sorted(glob.glob(f"{CALIB_DIR}/*_calibration.json"))
    if not files:
        print("❌ 找不到标定结果 json"); sys.exit(1)
    d = json.loads(open(files[-1]).read())
    q = d["orientation"]  # xyzw
    t = d["position"]
    T = tt.quaternion_matrix(q)
    T[:3, 3] = t
    print(f"加载标定: {os.path.basename(files[-1])}")
    print(f"  T_flange_cam pos={t}  quat={q}")
    print(f"  相机距 flange: {np.linalg.norm(t):.3f} m\n")
    return T


# ─── CAN + 臂 ───────────────────────────────────────────────
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_flange_xyzrpy():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None


# ─── ROS2 + 相机 ────────────────────────────────────────────
rclpy.init()
node = Node("verify_calib")
_latest = {"img": None, "K": None, "dist": None}
_q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST, depth=1)


def _on_image(msg):
    nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
    _latest["img"] = img if msg.encoding == 'bgr8' else \
        cv2.cvtColor(img, cv2.COLOR_RGB2BGR if msg.encoding.startswith('rgb') else cv2.COLOR_GRAY2BGR)


def _on_info(msg):
    if _latest["K"] is None:
        _latest["K"] = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        _latest["dist"] = np.array(msg.d, dtype=np.float64).reshape(-1)


node.create_subscription(Image, "/camera/color/image_raw", _on_image, _q)
node.create_subscription(CameraInfo, "/camera/color/camera_info", _on_info, _q)


def grab_marker():
    """抓一帧, 返回标记在相机光学系的位置 p_cam (3,) 或 None"""
    _latest["img"] = None
    for _ in range(30):
        rclpy.spin_once(node, timeout_sec=0.05)
        if _latest["img"] is not None:
            break
    img = _latest["img"]
    if img is None or _latest["K"] is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _DET.detectMarkers(gray)
    if ids is None or MARKER_ID not in ids.flatten():
        return None
    idx = list(ids.flatten()).index(MARKER_ID)
    ok, rvec, tvec = cv2.solvePnP(_OBJ, corners[idx], _latest["K"], _latest["dist"])
    return tvec.flatten() if ok else None


def clear_buf():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)


def xyzrpy_to_matrix(xyzrpy):
    """[x,y,z,roll,pitch,yaw] → 4x4, 约定 R=Rz(yaw)·Ry(pitch)·Rx(roll) (sxyz)"""
    x, y, z, r, p, y = xyzrpy
    T = np.eye(4)
    T[:3, :3] = tt.euler_matrix(r, p, y, axes='sxyz')[:3, :3]
    T[:3, 3] = [x, y, z]
    return T


def wait_camera_ready():
    """spin 直到收到内参 K 和第一帧图像"""
    print("等待相机就绪...", end="", flush=True)
    for _ in range(60):
        rclpy.spin_once(node, timeout_sec=0.1)
        if _latest["K"] is not None and _latest["img"] is not None:
            print(f" OK (fx={_latest['K'][0,0]:.0f})")
            return True
    print("\n❌ 相机没数据! 确认终端1相机在跑 (ros2 launch orbbec_camera ...)")
    return False


def jog(cmd):
    """解析点动命令并执行, 返回 True 若是点动命令"""
    sign, mag, jn = 0, 0.05, ""
    if   cmd.endswith("++"): sign, mag, jn =  1, 0.20, cmd[:-2]
    elif cmd.endswith("--"): sign, mag, jn = -1, 0.20, cmd[:-2]
    elif cmd.endswith("+"):  sign, jn =  1, cmd[:-1]
    elif cmd.endswith("-"):  sign, jn = -1, cmd[:-1]
    else: return False
    try: idx = int(jn) - 1
    except ValueError: return False
    if not (0 <= idx < 7): return False
    try:
        cur = list(arm.get_joint_angles().msg[:7]); cur[idx] += sign * mag
        arm.move_j(cur); print(f"  J{idx+1}: → {cur[idx]:.3f}")
    except Exception as e:
        print(f"  运动失败: {e}")
    return True


def main():
    T_fc = load_T_flange_cam()
    if not wait_camera_ready():
        return

    # 先确认能看到标记
    p = grab_marker()
    if p is None:
        print("⚠️  当前姿态看不到标记, 先点动到能看到标记的姿态")
    else:
        print(f"当前标记可见 (相机系 t={p})\n")

    print("=" * 55)
    print("  验证: 摆 5-8 个不同姿态 (标记始终可见)")
    print("  N+/N-/N++/N-- 点动 | m=采样 | q=结束统计")
    print("=" * 55)

    samples = []
    while True:
        try:
            clear_buf()
            cmd = input(f"\n[已采样 {len(samples)} 组] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "q":
            break
        elif cmd == "m" or cmd == "":
            fp = get_flange_xyzrpy()
            p_cam = grab_marker()
            if fp is None:
                print("  ❌ 没读到臂位姿"); continue
            if p_cam is None:
                print("  ❌ 没看到标记, 调整姿态"); continue
            T_bf = xyzrpy_to_matrix(fp)
            p_cam_h = np.array([p_cam[0], p_cam[1], p_cam[2], 1.0])
            p_base = (T_bf @ T_fc @ p_cam_h)[:3]
            samples.append(p_base)
            print(f"  ✅ 标记在基座系: ({p_base[0]:.3f}, {p_base[1]:.3f}, {p_base[2]:.3f}) m")
        elif jog(cmd):
            pass  # 点动已执行
        elif cmd == "h":
            try: arm.move_j([0]*7); print("  归零")
            except Exception as e: print(f"  {e}")
        else:
            print("  用法: 1+ 1- 3++ 3-- 点动 / m 采样 / h 归零 / q 结束")

    if len(samples) < 3:
        print("\n❌ 至少 3 组才能统计"); return

    arr = np.array(samples)
    mean = arr.mean(axis=0)
    std = arr.std(axis=0)
    spread = np.linalg.norm(std)  # 综合离散度

    print("\n" + "=" * 55)
    print("  标定质量评估")
    print("=" * 55)
    print(f"  采样组数: {len(samples)}")
    print(f"  标记在基座系均值: ({mean[0]:.3f}, {mean[1]:.3f}, {mean[2]:.3f}) m")
    print(f"  各轴标准差:     σx={std[0]:.4f}  σy={std[1]:.4f}  σz={std[2]:.4f} m")
    print(f"  综合离散度: {spread*100:.2f} cm")
    print()
    if spread < 0.015:
        grade = "优秀 ✅ (可用于抓取)"
    elif spread < 0.030:
        grade = "可用 🟡 (精度一般)"
    else:
        grade = "较差 ❌ (建议重标: 增加姿态多样性, 避免重复姿态)"
    print(f"  评级: {grade}")
    print("=" * 55)


try:
    main()
finally:
    arm.disconnect()
    print("断开 (保持使能)")
