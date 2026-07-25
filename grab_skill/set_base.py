"""设置手眼标定的基准姿态 (BASE)。

实时显示: 标记是否可见 / 标记在画面的中心像素 / 距离 / 当前关节角。
点动机械臂到 "标记居中、距离 0.30~0.50m、相机正视标记" 的姿态, 按 s 保存为 BASE。
保存后 auto_calib_poses.py 会自动加载这个新 BASE。

用法: python3 set_base.py
命令: 1+/1-/3++/3-- 点动  s=保存BASE  p=拍预览  h=归零  d=禁用  e=使能  q=退出
"""
import subprocess, time, threading, sys, json, termios, tty, os
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

# ─── ArUco ──────────────────────────────────────────────────
MARKER_ID, MARKER_SIZE = 0, 0.10
_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_DET = cv2.aruco.ArucoDetector(_DIC, cv2.aruco.DetectorParameters())
_OBJ = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                 [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)

# ─── CAN + 臂 ───────────────────────────────────────────────
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
arm.set_speed_percent(15)
arm.set_crash_protection_rating(joint_index=255, rating=0)
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_joints(): return list(arm.get_joint_angles().msg)
def get_flange():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None

print(f"[set_base] 臂已使能, 速度 15%")
print(f"[set_base] 当前关节: {[round(j, 3) for j in get_joints()]}")

# ─── ROS2 + 相机订阅 ────────────────────────────────────────
rclpy.init()
node = Node("set_base")
_latest = {"img": None, "K": None, "dist": None, "t": 0}
_q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST, depth=1)


def _on_image(msg):
    nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
    if msg.encoding.startswith('rgb'):
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    elif msg.encoding != 'bgr8':
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    _latest["img"] = img


def _on_info(msg):
    if _latest["K"] is None:
        _latest["K"] = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        _latest["dist"] = np.array(msg.d, dtype=np.float64).reshape(-1)


node.create_subscription(Image, "/camera/color/image_raw", _on_image, _q)
node.create_subscription(CameraInfo, "/camera/color/camera_info", _on_info, _q)


def grab_frame():
    _latest["img"] = None
    for _ in range(30):
        rclpy.spin_once(node, timeout_sec=0.05)
        if _latest["img"] is not None:
            return _latest["img"]
    return None


def detect(img):
    """返回 (found, info_dict)"""
    if img is None:
        return False, {}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _DET.detectMarkers(gray)
    if ids is None or MARKER_ID not in ids.flatten():
        return False, {}
    idx = list(ids.flatten()).index(MARKER_ID)
    K = _latest["K"]
    info = {}
    if K is not None:
        ok, rvec, tvec = cv2.solvePnP(_OBJ, corners[idx], K, _latest["dist"])
        if ok:
            t = tvec.flatten()
            cx, cy = corners[idx][0].mean(axis=0)
            info = {"t": t, "cx": cx, "cy": cy,
                    "h": img.shape[0], "w": img.shape[1]}
    return True, info


# ─── 实时反馈线程 ────────────────────────────────────────────
running = True


def feedback_loop():
    while running:
        img = grab_frame()
        found, info = detect(img)
        joints = get_joints()
        if found and "t" in info:
            t, cx, cy = info["t"], info["cx"], info["cy"]
            h, w = info["h"], info["w"]
            # 画面中心偏差
            offx = cx - w / 2
            offy = cy - h / 2
            dist_ok = "✓" if 0.30 <= t[2] <= 0.55 else "⚠️距离"
            center_ok = "✓" if abs(offx) < 60 and abs(offy) < 60 else "⚠️偏心"
            print(f"\r  标记: 距离={t[2]:.2f}m{dist_ok}  偏心=({offx:+.0f},{offy:+.0f})px{center_ok}  "
                  f"J=[{joints[0]:.2f},{joints[1]:.2f},{joints[2]:.2f}]   ", end="", flush=True)
        else:
            print(f"\r  ❌ 标记不可见  J=[{joints[0]:.2f},{joints[1]:.2f},{joints[2]:.2f}]                    ", end="", flush=True)
        time.sleep(0.6)


# ─── 点动 + 命令 ────────────────────────────────────────────
def clear_buf():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)


def save_base():
    joints = get_joints()
    fp = get_flange()
    out = {"joints": joints, "flange": fp,
           "_note": "auto_calib_poses.py 的 BASE, 由 set_base.py 生成"}
    path = "/root/grab_skill/calibration/base_pose.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n\n  ✅ 已保存 BASE → {path}")
    print(f"     关节: {[round(j, 4) for j in joints]}")
    if fp:
        print(f"     flange: {[round(v, 4) for v in fp]}")
    print(f"     auto_calib_poses.py 下次启动会自动加载此 BASE\n")


def cmd_loop():
    print("""
╔══════════════════════════════════════════════════╗
║  目标: 标记居中(偏心<60px) + 距离0.30~0.55m     ║
║  命令:                                          ║
║    N+ / N-     关节 N 微调 (±0.05)             ║
║    N++ / N--   关节 N 大调 (±0.20)             ║
║    s           保存为 BASE                      ║
║    p           拍预览图                         ║
║    h           归零  d=禁用  e=使能  q=退出     ║
╚══════════════════════════════════════════════════╝
""")
    while running:
        try:
            clear_buf()
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "q":
            print("退出"); break
        elif cmd == "s":
            save_base(); continue
        elif cmd == "p":
            img = grab_frame()
            if img is not None:
                found, info = detect(img)
                if found:
                    cv2.aruco.drawDetectedMarkers(img, *cv2.aruco.detectMarkers(
                        cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))[:2])
                p = "/root/grab_skill/calibration/preview_setbase.jpg"
                cv2.imwrite(p, img)
                print(f"\n  📷 预览 → {p}\n")
            continue
        elif cmd == "h":
            try: arm.move_j([0]*7); print("  归零")
            except Exception as e: print(f"  {e}")
            continue
        elif cmd == "d":
            try: arm.disable(); print("  已禁用")
            except Exception as e: print(f"  {e}")
            continue
        elif cmd == "e":
            try: arm.enable(); print("  已使能")
            except Exception as e: print(f"  {e}")
            continue
        elif not cmd: continue

        sign, mag, jn = 0, 0.05, ""
        if   cmd.endswith("++"): sign, mag, jn =  1, 0.20, cmd[:-2]
        elif cmd.endswith("--"): sign, mag, jn = -1, 0.20, cmd[:-2]
        elif cmd.endswith("+"):  sign, jn =  1, cmd[:-1]
        elif cmd.endswith("-"):  sign, jn = -1, cmd[:-1]
        else: print("  用法: 1+ 1- 3++ 3-- / s / p / h / d / e / q"); continue
        try: idx = int(jn) - 1
        except ValueError: print("  关节号 1-7"); continue
        if not (0 <= idx < 7): print("  关节号 1-7"); continue
        try:
            cur = list(get_joints()); cur[idx] += sign * mag
            arm.move_j(cur)
        except Exception as e:
            print(f"\n  运动失败: {e}")


# ─── 启动 ───────────────────────────────────────────────────
fb = threading.Thread(target=feedback_loop, daemon=True)
fb.start()
try:
    cmd_loop()
finally:
    running = False
    time.sleep(0.3)
    arm.disconnect()
    print("\n断开 (保持使能)")
