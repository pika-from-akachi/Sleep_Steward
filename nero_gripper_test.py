"""
NERO 夹爪 (AgxGripper) 测试
来源: 官方 test1.py Gripper 段落 + agx_gripper_api.md
前提: 夹爪已安装并连接到 CAN 总线
"""
import time
from platform import system
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW


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
    raise RuntimeError("Unsupported platform")


# ==================== 连接 ====================
robot_cfg = create_demo_config()
robot = AgxArmFactory.create_arm(robot_cfg)
robot.connect()
print(f"已连接: {robot.get_channel()}")

# ==================== 初始化夹爪 ====================
# 夹爪也走 CAN 总线，通过 robot 的 init_effector 创建
end_effector = robot.init_effector(robot.OPTIONS.EFFECTOR.AGX_GRIPPER)
print(f"夹爪已初始化: {end_effector.__doc__}")

# ==================== 读夹爪状态 ====================
print("\n--- 夹爪当前状态 ---")
gs = end_effector.get_gripper_status()
if gs:
    print(f"  模式: {gs.msg.mode}")
    print(f"  开度: {gs.msg.value:.4f} ({'m' if gs.msg.mode == 'width' else 'deg'})")
    print(f"  力: {gs.msg.force:.4f} N.m")
    print(f"  使能状态: {gs.msg.foc_status.driver_enable_status}")

# ==================== 校准夹爪（首次必做！）====================
print("\n--- 夹爪校准 ---")
print("1. 下使能夹爪...")
end_effector.disable_gripper()

print("2. 设置最大行程 (默认 0.07m)...")
end_effector.set_gripper_teaching_pendant_param(max_range_config=0.07)

# 如果你知道实际最大行程，改这里:
# end_effector.set_gripper_teaching_pendant_param(max_range_config=0.10)  # 10cm

input("3. 用手把夹爪推到完全闭合位置, 然后按 Enter...")

print("4. 执行校准...")
end_effector.calibrate_gripper()
print("校准完成!")

# ==================== 使能机械臂 + 夹爪 ====================
print("\n使能机械臂...")
robot.set_speed_percent(30)
robot.set_crash_protection_rating(joint_index=255, rating=2)
while not robot.enable():
    time.sleep(0.01)
print("已使能!")

# ==================== 夹爪运动 ====================
# 夹爪用 "位置模式" (P mode) 控制
robot.set_motion_mode(robot.OPTIONS.MOTION_MODE.P)

print("\n--- 夹爪运动测试 ---")

print("张开到 0.07m...")
end_effector.move_gripper_m(0.07)
time.sleep(0.5)

print("合拢到 0.03m...")
end_effector.move_gripper_m(0.03)
time.sleep(0.5)

print("完全闭合 (0°)...")
end_effector.move_gripper_deg(0)
time.sleep(0.5)

print("张开到 0.05m...")
end_effector.move_gripper_m(0.05)
time.sleep(0.5)

print("\n--- 最终状态 ---")
gs = end_effector.get_gripper_status()
if gs:
    print(f"  开度: {gs.msg.value:.4f} {gs.msg.mode}")
    print(f"  力: {gs.msg.force:.4f} N.m")

# ==================== 下使能 ====================
print("\n下使能...")
robot.disable()
print("测试完成")
robot.disconnect()
