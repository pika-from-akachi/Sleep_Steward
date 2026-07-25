"""NERO 手眼标定 — 自动摆位姿 (配合 handeye_calibration 终端使用)。

工作流:
  - 本终端: 自动 move_j 走预设的 15 个多样性姿态, 每个到位后停住等你确认
  - 标定终端: 每当本终端提示 "已到位", 在那里按 Enter 采集一组数据

⚠️ 姿态基于 observation_pose.json (相机俯视桌面看 ArUco 标记) 的基准扰动。
    第一次运行请盯紧机械臂, 如有碰撞风险立即 Ctrl+C 或在本终端按 q。

用法: python3 auto_calib_poses.py
交互: Enter=走下一个姿态  r=重测当前  s=显示位姿  q=退出
"""
import subprocess, time, threading, sys, termios, tty, os, json
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import Pose, Point, Quaternion
import tf_transformations as tt
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

# ─── ArUco 检测器 (和 aruco_detect.py 一致: DICT_5X5_50 ID0 size=0.1) ──
MARKER_ID = 0
MARKER_SIZE = 0.10
_ARUCO_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_ARUCO_DET = cv2.aruco.ArucoDetector(_ARUCO_DIC, cv2.aruco.DetectorParameters())
_OBJ_PTS = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                     [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)
PREVIEW_DIR = "/root/grab_skill/calibration"

# ─── CAN + 臂初始化 ─────────────────────────────────────────
CAN_IF = "can1"
subprocess.run(f"ip link set {CAN_IF} up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)

cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel=CAN_IF)
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass

# ⚠️ 慢速 + 碰撞保护, 标定时安全第一
arm.set_speed_percent(8)
arm.set_crash_protection_rating(joint_index=255, rating=0)

t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)


def get_joints():
    return list(arm.get_joint_angles().msg)


def get_flange():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None


joints = get_joints()
print(f"[auto_calib] 臂已使能, 当前关节: {[round(j, 3) for j in joints]}")
print(f"[auto_calib] 速度 8% | 碰撞保护 0 级")

# ─── ROS2 发布 /nero/end_pose + 订阅相机图像 ────────────────
rclpy.init()
node = Node("auto_calib_poses")
pub = node.create_publisher(Pose, "/nero/end_pose", 10)

# 最新一帧图像 + 内参 (线程间共享, 由 executor 回调写入)
_latest = {"img": None, "K": None, "dist": None}
_img_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                      history=HistoryPolicy.KEEP_LAST, depth=1)


def _on_image(msg):
    nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
    if msg.encoding.startswith('rgb'):
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    elif msg.encoding == 'bgr8':
        pass
    else:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    _latest["img"] = img


def _on_info(msg):
    if _latest["K"] is None:
        _latest["K"] = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        _latest["dist"] = np.array(msg.d, dtype=np.float64).reshape(-1)


node.create_subscription(Image, "/camera/color/image_raw", _on_image, _img_qos)
node.create_subscription(CameraInfo, "/camera/color/camera_info", _on_info, _img_qos)


def check_marker_visible(label=""):
    """抓当前帧检测 ArUco, 保存预览图, 返回 (可见, tvec)。"""
    # 等一帧新鲜图像
    _latest["img"] = None
    for _ in range(40):  # 最多等 ~2s
        rclpy.spin_once(node, timeout_sec=0.05)
        if _latest["img"] is not None:
            break
    img = _latest["img"]
    if img is None:
        print("    ⚠️  没收到相机图像 (终端1相机在跑吗?)")
        return False, None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _ARUCO_DET.detectMarkers(gray)
    found = ids is not None and MARKER_ID in ids.flatten()

    if found:
        idx = list(ids.flatten()).index(MARKER_ID)
        cv2.aruco.drawDetectedMarkers(img, corners, ids)
        K = _latest["K"]
        if K is not None:
            ok, rvec, tvec = cv2.solvePnP(_OBJ_PTS, corners[idx], K, _latest["dist"])
            if ok:
                cv2.drawFrameAxes(img, K, _latest["dist"], rvec, tvec, 0.03)
                tvec = tvec.flatten()
                print(f"    ✅ 标记可见  t=[{tvec[0]:.3f}, {tvec[1]:.3f}, {tvec[2]:.3f}] m")
                # 可见性质量: 距离 + 是否在画面中心区域
                h, w = img.shape[:2]
                cx, cy = corners[idx][0].mean(axis=0)
                edge = min(cx, cy, w - cx, h - cy)
                if tvec[2] < 0.10:
                    print(f"    ⚠️  标记太近 ({tvec[2]:.2f}m), 标定误差大")
                if edge < 40:
                    print(f"    ⚠️  标记靠近画面边缘, 建议跳过 (n)")
        else:
            tvec = None
            print("    ✅ 标记可见 (无内参, 不画坐标轴)")
    else:
        tvec = None
        print("    ❌ 未检测到标记 — 可能出视野/反光/太近. 建议: 按 n 跳过此姿态")

    # 保存预览图
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    cv2.imwrite(f"{PREVIEW_DIR}/preview_{label}.jpg", img)
    return found, tvec


def pub_pose():
    fp = get_flange()
    if fp is None:
        return
    x, y, z, roll, pitch, yaw = fp
    msg = Pose()
    msg.position = Point(x=x, y=y, z=z)
    q = tt.quaternion_from_euler(roll, pitch, yaw, axes='sxyz')
    msg.orientation = Quaternion(x=q[0], y=q[1], z=q[2], w=q[3])
    pub.publish(msg)


node.create_timer(0.05, pub_pose)  # 20Hz

# ─── 预设姿态列表 ───────────────────────────────────────────
# 基准 BASE: 相机俯视桌面看 ArUco 标记
# 索引: [J1底座, J2肩, J3肘, J4肘转, J5腕俯, J6腕转, J7末端roll]
# 优先加载 set_base.py 保存的姿态, 否则用默认
_BASE_FILE = "/root/grab_skill/calibration/base_pose.json"
_DEFAULT_BASE = [1.5099, -0.5499, -2.7571, 1.1706, 2.7575, 0.0132, -0.7231]
if os.path.exists(_BASE_FILE):
    try:
        _bd = json.loads(open(_BASE_FILE).read())
        BASE = list(_bd["joints"])
        print(f"[auto_calib] 加载自定义 BASE: {[round(j, 3) for j in BASE]}")
    except Exception as e:
        BASE = list(_DEFAULT_BASE)
        print(f"[auto_calib] BASE 文件读取失败 ({e}), 用默认")
else:
    BASE = list(_DEFAULT_BASE)
    print(f"[auto_calib] 用默认 BASE (建议先跑 set_base.py 定基准)")


def pose(offsets):
    """offsets: {关节索引(0-6): 偏移} → 完整 7 关节姿态"""
    p = list(BASE)
    for jidx, d in offsets.items():
        p[jidx] += d
    return p


# 18 个姿态: Dabai RGB 视野窄, 用小扰动 + J5/J6 旋转组合
# 偏移单位 rad。J5腕俯/J6腕偏 提供旋转多样性, J1/J2/J3 小幅平移
POSES = [
    pose({}),                                 # P1  基准
    pose({4: 0.12}),                          # P2  腕俯仰+
    pose({4: -0.12}),                         # P3  腕俯仰-
    pose({5: 0.15}),                          # P4  腕偏航+
    pose({5: -0.15}),                         # P5  腕偏航-
    pose({4: 0.10, 5: 0.10}),                 # P6  俯+偏
    pose({4: -0.10, 5: -0.10}),               # P7  俯-偏-
    pose({4: 0.08, 5: -0.10}),                # P8  俯+偏-
    pose({4: -0.08, 5: 0.10}),                # P9  俯-偏+
    pose({1: 0.12, 2: -0.08}),                # P10 后仰远离
    pose({1: -0.12, 2: 0.08}),                # P11 前倾靠近
    pose({0: 0.10, 4: 0.08}),                 # P12 底座转+腕俯
    pose({0: -0.10, 5: -0.10}),               # P13 底座转+腕偏
    pose({1: 0.08, 4: 0.10}),                 # P14
    pose({0: 0.08, 5: 0.12}),                 # P15
    pose({6: 0.08}),                          # P16 末端roll小幅+
    pose({6: -0.08, 4: 0.06}),                # P17 末端roll小幅-
    pose({1: -0.08, 5: 0.08, 4: -0.06}),      # P18 组合
]


def clear_input_buffer():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)


def move_to(joints_target, label=""):
    """安全移动到目标关节角"""
    try:
        print(f"  → 移动到 {label} ...", end="", flush=True)
        arm.move_j(joints_target)
        time.sleep(1.5)  # 等臂停稳 + 相机曝光稳定
        cur = get_joints()
        fp = get_flange()
        print(" OK")
        if fp:
            print(f"    flange: ({fp[0]:.3f}, {fp[1]:.3f}, {fp[2]:.3f}) "
                  f"rpy=({fp[3]:.2f}, {fp[4]:.2f}, {fp[5]:.2f})")
    except Exception as e:
        print(f" 失败: {e}")


def main_loop():
    print("""
╔════════════════════════════════════════════════════╗
║  自动摆位姿标定 — 共 18 个姿态                    ║
║                                                    ║
║  流程:                                             ║
║   1. 本脚本走到姿态 i 并停住, 自动检测标记可见性    ║
║   2. ✅ 可见 → 去【标定终端】按 Enter 采集一组      ║
║      ❌ 不可见 → 这里按 n 跳过此姿态               ║
║   3. 回到这里按 Enter 走下一个姿态                  ║
║                                                    ║
║  命令: Enter=下一个  n=跳过  r=重测  s=状态  q=退出 ║
║  预览图: /root/grab_skill/calibration/preview_P*.jpg║
╚════════════════════════════════════════════════════╝
""")
    input("先确认 ArUco 标记在桌上。按 Enter 开始 (先归基准姿态)...")
    move_to(BASE, "base")
    time.sleep(1.0)
    print("\n  检查基准姿态标记可见性:")
    ok, _ = check_marker_visible("base")
    if not ok:
        print("\n  ⚠️  基准姿态都看不到标记! 请调整标记位置或 BASE 姿态后重试。")
        print("     预览图: /root/grab_skill/calibration/preview_base.jpg")
        return

    i = 0
    collected = 0
    skipped = 0
    while i < len(POSES):
        print(f"\n{'='*50}")
        print(f"  姿态 {i+1}/{len(POSES)}  (已采集 {collected}, 跳过 {skipped})")
        print(f"{'='*50}")
        move_to(POSES[i], f"P{i+1}")
        time.sleep(0.8)
        ok, _ = check_marker_visible(f"P{i+1}")

        if not ok:
            print(f"\n  >>> 姿态 {i+1} 标记不可见 <<<")
            print(f"  建议: 按 n 跳过 (或 r 重测, 调整标记后再试)")
        else:
            print(f"\n  >>> 姿态 {i+1} 已到位, 标记可见 <<<")
            print(f"  去【标定终端】按 Enter 采集 (已采集 {collected} 组)")

        try:
            clear_input_buffer()
            cmd = input("  [Enter=下一个 n=跳过 r=重测 s=状态 q=退出]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "q":
            print("退出"); break
        elif cmd == "s":
            fp = get_flange()
            if fp:
                print(f"  flange: {fp}")
            print(f"  joints: {get_joints()}")
            continue
        elif cmd == "r":
            print("  重测当前姿态 (不前进)")
            continue
        elif cmd == "n":
            print("  跳过此姿态 (不采集)")
            skipped += 1
            i += 1
            continue
        else:
            collected += 1
            i += 1

    print(f"\n{'='*50}")
    print(f"  完成! 采集 {collected} 组, 跳过 {skipped} 个")
    if collected < 8:
        print(f"  ⚠️  采集不足 8 组, 标定可能不准。建议重跑并调整标记位置")
    else:
        print(f"  现在去【标定终端】按 q 计算结果")
    print(f"{'='*50}")


threading.Thread(target=main_loop, daemon=True).start()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    print("\n断开 (保持使能)...")
    arm.disconnect()
