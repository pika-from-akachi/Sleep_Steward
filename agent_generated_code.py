import time
import traceback
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

SAFE_SPEED = 20

try:
    cfg = create_agx_arm_config(
        robot=ArmModel.NERO,
        firmeware_version=NeroFW.V112,
        interface="socketcan",
        channel="can1",
    )
    arm = AgxArmFactory.create_arm(cfg)
    arm.connect()

    arm.set_speed_percent(SAFE_SPEED)
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)

    while not arm.enable():
        time.sleep(0.01)

    ja = arm.get_joint_angles()
    if ja is None:
        raise RuntimeError("无法读取关节角")
    home = list(ja.msg)

    target = home.copy()
    target[6] = home[6] + 0.03
    print(f"[SAFE] 目标关节角: {[round(t, 4) for t in target]}")
    arm.move_j(target)
    time.sleep(3)

    print(f"[SAFE] 目标关节角: {[round(t, 4) for t in home]}")
    arm.move_j(home)
    time.sleep(3)

    arm.disable()
    arm.disconnect()

except Exception as e:
    print(f"[SAFETY] 异常: {e}")
    traceback.print_exc()
    try:
        arm.disable()
        arm.disconnect()
    except:
        pass
