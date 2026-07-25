from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.DEFAULT,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
print("连接OK")
ja = arm.get_joint_angles()
if ja:
    print("关节角:", [round(a, 4) for a in ja.msg])
arm.disconnect()
