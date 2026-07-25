"""
NERO 官方 test1.py 安全精简版
只保留: 连接 → 低速使能 → 小幅度运动 → 状态读取 → 下使能
已移除: MIT模式 / 力矩测试 / 夹爪 / 灵巧手 / 主从 / CPV调参 / Leader-Follower
"""
import time
from platform import system
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW


def wait_motion_done(robot, timeout: float = 5.0, poll_interval: float = 0.1) -> bool:
    """Wait until motion_status == 0 or timeout."""
    time.sleep(0.5)
    start_t = time.monotonic()
    while True:
        status = robot.get_arm_status()
        if status is not None and getattr(status.msg, "motion_status", None) == 0:
            print("  -> 运动完成")
            return True
        if time.monotonic() - start_t > timeout:
            print(f"  -> 等待超时 ({timeout:.1f}s)")
            return False
        time.sleep(poll_interval)


def create_demo_config():
    platform_system = system()
    if platform_system == "Windows":
        return create_agx_arm_config(
            robot=ArmModel.NERO, firmeware_version=NeroFW.DEFAULT,
            interface="agx_cando", channel="0",
        )
    if platform_system == "Linux":
        return create_agx_arm_config(
            robot=ArmModel.NERO, firmeware_version=NeroFW.DEFAULT,
            interface="socketcan", channel="can0",
        )
    if platform_system == "Darwin":
        return create_agx_arm_config(
            robot=ArmModel.NERO, firmeware_version=NeroFW.DEFAULT,
            interface="slcan", channel="/dev/ttyACM0",
        )
    raise RuntimeError("只支持 Linux(socketcan) / Windows(agx_cando) / macOS(slcan)")


# ======================== 连接 ========================
robot_cfg = create_demo_config()
print(f"配置: {robot_cfg}")
robot = AgxArmFactory.create_arm(robot_cfg)
robot.connect()
print(f"通道: {robot.get_channel()}")

# ======================== 安全配置 ========================
robot.set_speed_percent(10)               # 10% 速度
robot.set_crash_protection_rating(joint_index=255, rating=0)  # 全关节最灵敏
robot.set_joint_limits_enabled(True)       # 开启关节限位
print("安全配置: 速度10% | 碰撞0级 | 限位ON")

# ======================== 使能 ========================
print("使能中...")
while not robot.enable():
    time.sleep(0.01)
print("已使能!")

# ======================== 读当前姿态 ========================
ja = robot.get_joint_angles()
if ja is None:
    print("无法读取关节角度, 退出")
    robot.disable()
    exit(1)

home = list(ja.msg)
print(f"当前关节角 (rad): {[round(a, 4) for a in home]}")

# ======================== 运动测试 ========================

# -- 测试1: 各关节单独微动后回原位 --
print("\n--- 测试1: 单关节微动 (±0.1 rad) ---")
for i in range(7):
    for delta in [0.1, -0.1, 0.0]:
        target = home.copy()
        target[i] += delta
        print(f"  J{i+1}: delta={delta:+.1f} -> {round(target[i], 4)}", end="")
        robot.move_j(target)
        wait_motion_done(robot, timeout=5.0)
print("测试1 OK")

# -- 测试2: 笛卡尔点对点运动 (微小位移) --
print("\n--- 测试2: 笛卡尔 P2P (2cm) ---")
flange = robot.get_flange_pose()
if flange:
    p = list(flange.msg)
    p[0] += 0.02  # X+2cm
    print(f"  目标位姿: {[round(x, 4) for x in p]}")
    robot.move_p(p)
    wait_motion_done(robot, timeout=5.0)
    robot.move_j(home)
    wait_motion_done(robot, timeout=10.0)
print("测试2 OK")

# -- 测试3: 直线运动 (微小位移) --
print("\n--- 测试3: 直线运动 (1cm) ---")
flange = robot.get_flange_pose()
if flange:
    p = list(flange.msg)
    p[2] += 0.01  # Z+1cm
    print(f"  目标位姿: {[round(x, 4) for x in p]}")
    robot.move_l(p)
    wait_motion_done(robot, timeout=10.0)
    robot.move_j(home)
    wait_motion_done(robot, timeout=5.0)
print("测试3 OK")

# ======================== 状态读取 ========================
print("\n--- 状态汇总 ---")
status = robot.get_arm_status()
if status:
    s = status.msg
    print(f"  arm_status: {s.arm_status}")
    print(f"  motion_status: {s.motion_status}")
    print(f"  ctrl_mode: {s.ctrl_mode}")

fw = robot.get_firmware()
if fw:
    print(f"  固件: {fw.get('software_version', '?')}")

ja = robot.get_joint_angles()
if ja:
    print(f"  关节角: {[round(a, 4) for a in ja.msg]}")

fp = robot.get_flange_pose()
if fp:
    print(f"  法兰位姿: {[round(x, 4) for x in fp.msg]}")

for i in range(7):
    ms = robot.get_motor_states(i + 1)
    ds = robot.get_driver_states(i + 1)
    if ms and ds:
        m = ms.msg
        d = ds.msg
        print(f"  J{i+1}: pos={m.position:.4f} vel={m.velocity:.2f} cur={m.current:.3f}A "
              f"torque={m.torque:.3f}Nm motor_temp={d.motor_temp}°C "
              f"collision={d.foc_status.collision_status}")

# ======================== 下使能 ========================
print("\n下使能...")
robot.disable()
print("测试全部完成, 机械臂已下使能")
robot.disconnect()
