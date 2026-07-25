import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
try:
    cfg = create_agx_arm_config(robot=ArmModel.NERO,
        firmeware_version=NeroFW.V112,
        interface="socketcan", channel="can1")
    arm = AgxArmFactory.create_arm(cfg)
    arm.connect()
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)
    arm.set_speed_percent(20)
    while not arm.enable():
        time.sleep(0.01)
    ja = arm.get_joint_angles()
    home = list(ja.msg)
    target = home.copy()
    target[6] += 0.05
    print(f"[SAFE] 目标: {[round(t,4) for t in target]}")
    arm.move_j(target)
    time.sleep(1)
    arm.disable()
    arm.disconnect()
except Exception as e:
    print(f"[SAFETY] 异常: {e}")
    try:
        arm.disable()
        arm.disconnect()
    except:
        pass
