"""全自动独立验证 (随机姿态, 不同于标定姿态)。

用随机生成的姿态测「标记在基座系位置」的一致性:
  - 标记静止 → 不同姿态算出的位置应该一致
  - σx/σy/σz 越小标定越准
  - 重点看 σy (深度方向, 之前病态轴): <2cm = 成功

与标定姿态独立 (随机生成), 是真正的泛化测试, 不是训练误差。

用法: python3 verify_auto.py
依赖: 终端1相机在跑; 已有标定结果
"""
import subprocess, time, sys, glob, os, json
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
MARKER_ID, MARKER_SIZE = 0, 0.15
_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_DET = cv2.aruco.ArucoDetector(_DIC, cv2.aruco.DetectorParameters())
_OBJ = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                 [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)

# ─── 加载标定结果 ───────────────────────────────────────────
def load_T_flange_cam():
    files = sorted(glob.glob(f"{CALIB_DIR}/*_calibration.json"))
    if not files:
        print("❌ 找不到标定结果 json"); sys.exit(1)
    d = json.loads(open(files[-1]).read())
    T = tt.quaternion_matrix(d["orientation"]); T[:3, 3] = d["position"]
    print(f"[verify] 标定: {os.path.basename(files[-1])}")
    print(f"         pos={np.round(d['position'],4)}  距flange={np.linalg.norm(d['position']):.3f}m\n")
    return T

def load_base():
    f = f"{CALIB_DIR}/base_pose.json"
    if os.path.exists(f):
        return list(json.loads(open(f).read())["joints"])
    return [1.51, -0.20, -2.757, 1.67, 2.757, 0.363, -0.773]

# ─── 随机姿态生成 (独立于标定姿态) ─────────────────────────
BASE = load_base()
# 各关节随机扰动范围 (rad), 参考 calib_auto 有效范围, 保证大部分可见
JITTER = np.array([0.15, 0.25, 0.20, 0.10, 0.20, 0.20, 0.12])

def gen_random_poses(n=18, seed=None):
    rng = np.random.RandomState(seed)
    poses = []
    for _ in range(n):
        p = list(BASE) + rng.uniform(-1, 1, 7) * JITTER
        poses.append(list(p))
    return poses

# ─── CAN + 臂 ───────────────────────────────────────────────
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
arm.set_speed_percent(8)
arm.set_crash_protection_rating(joint_index=255, rating=0)
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_flange_xyzrpy():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None

def xyzrpy_to_T(xyzrpy):
    x, y, z, r, p, yaw = xyzrpy
    T = np.eye(4); T[:3, :3] = tt.euler_matrix(r, p, yaw, axes='sxyz')[:3, :3]; T[:3, 3] = [x, y, z]
    return T

# ─── ROS2 + 相机 ────────────────────────────────────────────
rclpy.init()
node = Node("verify_auto")
_latest = {"img": None, "K": None, "dist": None}
_q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)
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

def grab_marker_median(n=5):
    pts = []
    for _ in range(n * 4):
        rclpy.spin_once(node, timeout_sec=0.05)
        img = _latest["img"]
        if img is None or _latest["K"] is None: continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = _DET.detectMarkers(gray)
        if ids is not None and MARKER_ID in ids.flatten():
            idx = list(ids.flatten()).index(MARKER_ID)
            ok, rvec, tvec = cv2.solvePnP(_OBJ, corners[idx], _latest["K"], _latest["dist"])
            if ok:
                pts.append(tvec.flatten())
                if len(pts) >= n: break
    if len(pts) < 2: return None
    return np.median(pts, axis=0)

def wait_camera():
    print("[verify] 等相机...", end="", flush=True)
    for _ in range(60):
        rclpy.spin_once(node, timeout_sec=0.1)
        if _latest["K"] is not None and _latest["img"] is not None:
            print(f" OK"); return True
    print(" ❌"); return False

# ─── 主流程 ─────────────────────────────────────────────────
def main():
    T_fc = load_T_flange_cam()
    if not wait_camera(): return

    seed = int(time.time()) % 100000
    poses = gen_random_poses(18, seed=seed)
    print(f"[verify] 随机生成 {len(poses)} 个独立姿态 (seed={seed})\n")

    samples = []
    skipped = 0
    # 先走基准确认可见
    arm.move_j(BASE); time.sleep(1.2)
    if grab_marker_median() is None:
        print("❌ 基准姿态看不到标记, 退出"); return

    for i, tgt in enumerate(poses):
        try:
            arm.move_j(tgt); time.sleep(1.0)
        except Exception as e:
            print(f"  V{i+1:2d}: 运动失败 {e}"); skipped += 1; continue
        p_cam = grab_marker_median()
        fp = get_flange_xyzrpy()
        if p_cam is None or fp is None:
            print(f"  V{i+1:2d}/{len(poses)}: ❌ 标记不可见, 跳过"); skipped += 1; continue
        T_bf = xyzrpy_to_T(fp)
        p_base = (T_bf @ T_fc @ np.array([p_cam[0], p_cam[1], p_cam[2], 1.0]))[:3]
        samples.append(p_base)
        print(f"  V{i+1:2d}/{len(poses)}: ✅ ({p_base[0]:.3f}, {p_base[1]:.3f}, {p_base[2]:.3f}) m")

    print("\n" + "=" * 55)
    if len(samples) < 6:
        print(f"  ❌ 有效样本仅 {len(samples)} (<6), 无法统计"); return

    arr = np.array(samples)
    mean, std = arr.mean(axis=0), arr.std(axis=0)
    spread = float(np.linalg.norm(std))
    print("  全自动独立验证结果 (随机姿态)")
    print("=" * 55)
    print(f"  有效: {len(samples)} 组 / 跳过: {skipped}")
    print(f"  标记在基座系均值: ({mean[0]:.3f}, {mean[1]:.3f}, {mean[2]:.3f}) m")
    print(f"  各轴标准差:  σx={std[0]*100:5.2f}cm  σy={std[1]*100:5.2f}cm  σz={std[2]*100:5.2f}cm")
    print(f"  综合离散度: {spread*100:.2f} cm")
    print("-" * 55)
    # 逐轴评级, 重点 σy
    for ax, nm in [(0,"x(左右)"), (1,"y(深度)"), (2,"z(高度)")]:
        if std[ax] < 0.015: g = "优秀 ✅"
        elif std[ax] < 0.030: g = "可用 🟡"
        else: g = "较差 ❌"
        star = " ⬅️ 关键!" if ax == 1 else ""
        print(f"  σ{nm}: {std[ax]*100:5.2f}cm  {g}{star}")
    print("=" * 55)
    if std[1] < 0.02 and std[0] < 0.03 and std[2] < 0.03:
        print("  🎉 标定成功! 可用于抓取。")
    elif std[1] > 0.05:
        print("  ❌ σy 仍大 → 深度方向未解决, 检查标记尺寸是否精确 150mm / 平整度")
    with open(f"{CALIB_DIR}/verify_result.json", "w") as f:
        json.dump({"samples": [list(s) for s in samples], "std_cm": list(std*100)}, f, indent=2)

try:
    main()
finally:
    arm.disconnect()
    print("[verify] 断开 (保持使能)")
