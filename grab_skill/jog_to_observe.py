"""交互式点动: 微调各关节到"相机看清桌面"的观测姿态, 满意了存 observation_pose.json。

命令 (回车执行):
  1+ / 1-     关节1 ±0.05 rad (约3°)
  3++ / 3--   关节3 ±0.2  rad (约11°, 大步)
  v           刷新深度统计 + 存 /tmp/jog_view.jpg
  p           打印当前关节角
  s           保存为观测姿态
  q           退出(不存)
每步运动后自动打印 关节角 + 深度统计。相机驱动需在跑(没跑也能动臂,只是没深度反馈)。
"""
import json
from pathlib import Path
import numpy as np
from arm_control import NeroArm

# 可选: 相机深度反馈
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image
    rclpy.init()
    _n = Node("jog_depth")
    _late = [None]
    _n.create_subscription(Image, "/camera/depth/image_raw",
                           lambda m: _late.__setitem__(0, m),
                           QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                                      history=HistoryPolicy.KEEP_LAST, depth=1))
    _CAM = True
except Exception as e:
    _CAM = False
    print(f"(相机反馈不可用: {e})")

OBS_FILE = Path("/root/grab_skill/observation_pose.json")
STEP, BIG = 0.05, 0.2


def depth_stats():
    if not _CAM:
        return
    rclpy.spin_once(_n, timeout_sec=0.25)
    m = _late[0]
    if m is None:
        print("  深度: (没收到, 相机驱动在跑吗?)"); return
    a = np.frombuffer(m.data, np.uint16).reshape((m.height, m.width)).astype(np.float32) * 0.001
    v = a[a > 0.05]
    if len(v) == 0:
        print("  深度: 全0 (LDP? 没桌面?)"); return
    med = float(np.median(v))
    hint = "← 大概率看到桌面/工作区" if 0.3 <= med <= 1.2 else "(中位深度偏远/近, 调整角度)"
    print(f"  深度: 有效{len(v)/a.size*100:.0f}% 范围{v.min():.2f}~{v.max():.2f}m 中位{med:.2f}m {hint}")


arm = NeroArm(); arm.connect(); arm.enable()


def show(j):
    print("  关节角:", [round(x, 3) for x in j[:7]])


j = arm.get_joint_angles(); show(j); depth_stats()

while True:
    try:
        cmd = input("> ").strip().lower()
    except EOFError:
        break
    if cmd == "q":
        print("退出, 未保存"); break
    if cmd == "s":
        OBS_FILE.write_text(json.dumps(list(j[:7])))
        print(f"✅ 已存观测姿态(7关节) -> {OBS_FILE}")
        try:
            print("  对应 TCP:", [round(x, 3) for x in arm.get_tcp_pose()])
        except Exception:
            pass
        break
    if cmd == "p":
        j = arm.get_joint_angles(); show(j); continue
    if cmd == "v":
        depth_stats(); continue
    # 解析 N+ / N- / N++ / N--
    sign, mag, jn = 0, STEP, ""
    if cmd.endswith("++"):
        sign, mag, jn = 1, BIG, cmd[:-2]
    elif cmd.endswith("--"):
        sign, mag, jn = -1, BIG, cmd[:-2]
    elif cmd.endswith("+"):
        sign, jn = 1, cmd[:-1]
    elif cmd.endswith("-"):
        sign, jn = -1, cmd[:-1]
    else:
        print("  不识别。用法: 1+ 1- 3++ 3-- / v / p / s / q"); continue
    try:
        idx = int(jn) - 1
    except ValueError:
        print("  关节号错"); continue
    if not (0 <= idx < 7):
        print("  关节号 1-7"); continue
    j = arm.get_joint_angles()
    target = list(j[:7]); target[idx] += sign * mag
    print(f"  → 关节{idx+1} {sign*mag:+.2f}rad → 目标 {round(target[idx],3)}")
    try:
        arm.move_joints(target, speed_pct=8)
    except Exception as e:
        print("  运动失败:", e); continue
    j = arm.get_joint_angles(); show(j); depth_stats()

arm.disconnect()  # 不下使能
