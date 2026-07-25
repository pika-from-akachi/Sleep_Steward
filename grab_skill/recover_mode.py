"""把臂从零力拖拽(leader)模式切回可控模式。

calib_teach.py 跑完/Ctrl+C 后, 臂可能卡在 leader (零力) 模式。
NERO V112 不支持 set_normal_mode, 这里用 enable + set_follower_mode 切回。

用法: python3 recover_mode.py
若 move_j 仍失败, 请断电重启臂再上电。
"""
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
time.sleep(0.3)
arm.enable(); time.sleep(0.8)
try:
    arm.set_follower_mode(); time.sleep(0.5)
    print("✅ 已切回 follower (可控) 模式")
except Exception as e:
    print(f"set_follower_mode 失败: {e}")

fp = arm.get_flange_pose()
if fp and fp.msg:
    print(f"flange 位姿可读: {np_round(fp.msg) if False else [round(v,3) for v in fp.msg]}")
else:
    print("⚠️ flange 读不到")

# 小测试: 微动关节1 验证可控 (±0.02rad, 几乎不动)
try:
    cur = list(arm.get_joint_angles().msg[:7])
    arm.set_speed_percent(5)
    arm.move_j([cur[0] + 0.02] + cur[1:])
    time.sleep(1.0)
    arm.move_j(cur)   # 回原位
    print("✅ move_j 测试通过 — 臂可控")
except Exception as e:
    print(f"❌ move_j 失败 ({e}) — 请断电重启臂再上电")
arm.disconnect()
