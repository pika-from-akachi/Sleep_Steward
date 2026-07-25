"""NERO 标定点动 — 发布 flange 位姿 + 关节交互点动。
供 handeye_calibration_ros 读取 /nero/end_pose (geometry_msgs/Pose)。

RPY 约定 (pyAgxArm Nero API): R = Rz(yaw)·Ry(pitch)·Rx(roll)
四元数: tf_transformations.quaternion_from_euler(roll, pitch, yaw, axes='sxyz')
基座系: +Y=前方, +Z=上方

用法: python3 nero_calib_jog.py
点动: 1+/1-/3++/3-- (关节±0.05/±0.2rad, 共 7 关节)
       d(禁用使能)  e(使能)  h(归零)  s(状态)  q(退出)
"""
import subprocess, time, math, threading, sys, termios, tty
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, Point, Quaternion
import tf_transformations as tt
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

# ─── CAN 初始化 ─────────────────────────────────────────────
CAN_IF = "can1"
subprocess.run(f"ip link set {CAN_IF} up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)

cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel=CAN_IF)
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_joints():
    """读取 7 个关节角 (list of float)"""
    return list(arm.get_joint_angles().msg)

if not get_joints():
    print("[FATAL] 无法读取关节角 — 检查 CAN/电机电源")
    arm.disconnect(); sys.exit(1)

joints = get_joints()[:7]
print(f"[nero_calib_jog] 臂已使能, 关节: {[round(j, 3) for j in joints]}")
print(f"[nero_calib_jog] 发布 /nero/end_pose @ 20Hz")

# ─── ROS2 发布节点 ──────────────────────────────────────────
rclpy.init()
node = Node("nero_calib_jog")
pub = node.create_publisher(Pose, "/nero/end_pose", 10)


def pub_pose():
    """发布 flange 位姿 (Pose):
    约定 R = Rz(yaw)·Ry(pitch)·Rx(roll), quaternion 用 sxyz 生成。"""
    fp = arm.get_flange_pose()
    if fp is None or fp.msg is None:
        return
    x, y, z, roll, pitch, yaw = fp.msg
    msg = Pose()
    msg.position = Point(x=x, y=y, z=z)
    # R = Rz(yaw)·Ry(pitch)·Rx(roll) — 与 transforms.py 一致
    q = tt.quaternion_from_euler(roll, pitch, yaw, axes='sxyz')
    msg.orientation = Quaternion(x=q[0], y=q[1], z=q[2], w=q[3])
    pub.publish(msg)


node.create_timer(0.05, pub_pose)  # 20Hz


# ─── 辅助方法 ────────────────────────────────────────────────
def show_status():
    fp = arm.get_flange_pose()
    if fp and fp.msg:
        x, y, z, r, p, yw = fp.msg
        print(f"\n  flange: pos=({x:.4f}, {y:.4f}, {z:.4f}) rpy=({r:.3f}, {p:.3f}, {yw:.3f})")
    joints = get_joints()
    print(f"  joints: {[round(j, 3) for j in joints]}")


def clear_input_buffer():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try: tty.setraw(fd)
    finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─── 点动 ────────────────────────────────────────────────────
def jog_loop():
    STEP, BIG = 0.05, 0.2
    print("""
╔══════════════════════════════════════════╗
║  点动命令:                               ║
║    N+ / N-     关节 N 微调 (±0.05 rad)  ║
║    N++ / N--   关节 N 大调 (±0.20 rad)  ║
║    s           显示当前姿态               ║
║    d           禁用使能 (手动拖拽)        ║
║    e           重新使能                   ║
║    h           归零 (home)                ║
║    q           退出                       ║
╚══════════════════════════════════════════╝
""")
    while True:
        try:
            clear_input_buffer()
            cmd = input("jog> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "q": print("退出点动"); break
        elif cmd == "s": show_status(); continue
        elif cmd == "d":
            try: arm.disable(); print("  已禁用使能 (可手动拖拽)")
            except Exception as e: print(f"  disable 失败: {e}")
            continue
        elif cmd == "e":
            try: arm.enable(); print("  已重新使能")
            except Exception as e: print(f"  enable 失败: {e}")
            continue
        elif cmd == "h":
            try: arm.move_j([0, 0, 0, 0, 0, 0, 0]); print("  已归零")
            except Exception as e: print(f"  home 失败: {e}")
            continue
        elif not cmd: continue

        # 解析 N+/N-/N++/N--
        sign, mag, jn = 0, STEP, ""
        if   cmd.endswith("++"): sign, mag, jn =  1, BIG, cmd[:-2]
        elif cmd.endswith("--"): sign, mag, jn = -1, BIG, cmd[:-2]
        elif cmd.endswith("+"):  sign, jn =  1, cmd[:-1]
        elif cmd.endswith("-"):  sign, jn = -1, cmd[:-1]
        else: print("  用法: 1+ 1- 3++ 3-- / s / d / e / h / q"); continue

        try: idx = int(jn) - 1
        except ValueError: print("  关节号错 (1-7)"); continue
        if not (0 <= idx < 7): print("  关节号 1-7"); continue

        try:
            cur = list(get_joints())
            tgt = list(cur); tgt[idx] += sign * mag
            arm.move_j(tgt)
            print(f"  J{idx+1}: {cur[idx]:.3f} → {tgt[idx]:.3f}")
        except Exception as e:
            print(f"  运动失败: {e}")


# ─── 主循环 ──────────────────────────────────────────────────
threading.Thread(target=jog_loop, daemon=True).start()
try:
    rclpy.spin(node)
except KeyboardInterrupt:
    pass
finally:
    print("\n断开 CAN (保持使能状态)...")
    arm.disconnect()
    print("结束。")
