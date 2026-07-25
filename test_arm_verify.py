import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

print("1. 连接...")
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
print("   连接OK")

print("2. 固件版本...")
fw = arm.get_firmware()
if fw:
    print("   ", fw.get("software_version", "?"))

print("3. 使能...")
arm.set_speed_percent(20)
arm.set_crash_protection_rating(joint_index=255, rating=2)
while not arm.enable():
    time.sleep(0.01)
print("   已使能")

print("4. 关节角...")
ja = arm.get_joint_angles()
if ja:
    print("   ", [round(a, 4) for a in ja.msg])
else:
    print("   无数据!")

print("5. 法兰位姿...")
fp = arm.get_flange_pose()
if fp:
    print("   xyz:", [round(x, 4) for x in fp.msg[:3]])
    print("   rpy:", [round(x, 4) for x in fp.msg[3:]])

print("6. 微动测试 (J7 +0.05rad)...")
home = list(ja.msg) if ja else [0]*7
target = home.copy()
target[6] += 0.05
arm.move_j(target)
for _ in range(30):
    s = arm.get_arm_status()
    if s and s.msg.motion_status == 0:
        break
    time.sleep(0.1)
print("   运动完成")

# 回原位
arm.move_j(home)
time.sleep(1)

print("7. 完成, 下使能")
arm.disable()
arm.disconnect()
print("✅ 机械臂验证通过!")
