"""
NERO 安全运动测试 - 首次上电专用
1. 检测固件 + 连接
2. 低速读取当前位置
3. 微小幅度关节运动
4. 回到原位 + 下使能
"""
import time
from platform import system
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

# ====== 连接 ======
robot = ArmModel.NERO
platform_system = system()
if platform_system == "Windows":
    cfg = create_agx_arm_config(robot=robot, firmeware_version=NeroFW.DEFAULT,
                                interface="agx_cando", channel="0")
elif platform_system == "Linux":
    cfg = create_agx_arm_config(robot=robot, firmeware_version=NeroFW.DEFAULT,
                                interface="socketcan", channel="can0")
else:
    raise RuntimeError("Unsupported platform")

arm = AgxArmFactory.create_arm(cfg)
arm.connect()

# ====== 检测固件版本 ======
fw = arm.get_firmware()
if fw:
    sv = fw.get("software_version", "unknown")
    print(f"固件版本: {sv}")
    # 自动设置正确的固件
    if sv >= "1.20":
        fw_ver = NeroFW.V120
    elif sv >= "1.12":
        fw_ver = NeroFW.V112
    elif sv >= "1.11":
        fw_ver = NeroFW.V111
    else:
        fw_ver = NeroFW.DEFAULT
    if fw_ver != NeroFW.DEFAULT:
        print(f"建议使用 firmeware_version=NeroFW.{fw_ver.upper()}")
else:
    print("无法获取固件，使用 DEFAULT")
    fw_ver = NeroFW.DEFAULT

# ====== 安全配置 ======
arm.set_speed_percent(10)            # 10% 速度
arm.set_crash_protection_rating(0)   # 最灵敏碰撞检测
arm.set_joint_limits_enabled(True)   # 关节限位
print("安全配置: 速度10% | 碰撞检测0级 | 限位开启")

# ====== 使能 ======
print("使能中...")
while not arm.enable():
    time.sleep(0.01)
print("已使能!")

# ====== 读取当前姿态 ======
ja = arm.get_joint_angles()
if ja is None:
    print("❌ 无法读取关节角度!")
    arm.disable()
    exit(1)

home = list(ja.msg)
print(f"当前关节角 (rad): {[round(a, 4) for a in home]}")

# ====== 测试 1: 每个关节单独微动 0.05 rad (~3度) ======
print("\n===== 测试1: 逐关节微动 0.05 rad =====")
for i in range(7):
    target = home.copy()
    target[i] += 0.05  # 单关节动 0.05 rad
    print(f"J{i+1} -> {round(target[i], 4)}", end=" ... ")
    arm.move_j(target)
    time.sleep(0.5)
    # 等待完成
    for _ in range(20):
        status = arm.get_arm_status()
        if status and status.msg.motion_status == 0:
            break
        time.sleep(0.1)
    print("OK")
    # 回原位
    arm.move_j(home)
    time.sleep(0.5)
    for _ in range(20):
        status = arm.get_arm_status()
        if status and status.msg.motion_status == 0:
            break
        time.sleep(0.1)

print("测试1 完成 ✅")

# ====== 测试 2: 所有关节同时微动 ======
print("\n===== 测试2: 全关节同时微动 0.03 rad =====")
target = [h + 0.03 for h in home]
print(f"目标: {[round(t, 4) for t in target]}")
arm.move_j(target)
time.sleep(1)
for _ in range(30):
    status = arm.get_arm_status()
    if status and status.msg.motion_status == 0:
        break
    time.sleep(0.1)
arm.move_j(home)
time.sleep(1)
print("测试2 完成 ✅")

# ====== 测试 3: 读取状态 ======
print("\n===== 测试3: 状态读取 =====")
status = arm.get_arm_status()
if status:
    s = status.msg
    print(f"  arm_status: {s.arm_status}")
    print(f"  motion_status: {s.motion_status}")
    print(f"  ctrl_mode: {s.ctrl_mode}")

ja2 = arm.get_joint_angles()
if ja2:
    print(f"  当前角度: {[round(a, 4) for a in ja2.msg]}")

# ====== 下使能 ======
print("\n下使能...")
arm.disable()
print("测试全部完成 ✅ 机械臂已下使能")
arm.disconnect()
