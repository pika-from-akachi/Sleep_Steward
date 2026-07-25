from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO,
    firmeware_version=NeroFW.DEFAULT,
    interface="socketcan", channel="can0")
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
arm.set_normal_mode()
arm.enable()
arm.set_speed_percent(100)
arm.move_j([0, 0, 0, 0, 0, 0, 0])
arm.disable()
