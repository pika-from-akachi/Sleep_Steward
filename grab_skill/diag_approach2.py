"""诊断: 用固件接受的朝向 [1.094, 1.0, 1.402] 测 approach 可达性。

之前 diag_approach 全失败是因为用了观测朝向 pitch=1.305 (固件拒)。
现改 pitch=1.0 (固件 accept), 测物体上方各高度能否 move_p 到。

用法: python3 diag_approach2.py
"""
import subprocess, time, json
from pathlib import Path
import numpy as np
np.float = float; np.int = int; np.bool = bool
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

OBSERVE = list(json.loads(Path("/root/grab_skill/calibration/base_pose.json").read_text())["joints"])
OBJ_XY = [-0.063, 0.435]
ACCEPT_RPY = [1.094, 1.0, 1.402]   # 固件 accept 的朝向 (pitch=1.0)

subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112, interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
arm.set_speed_percent(8); arm.set_crash_protection_rating(joint_index=255, rating=0)
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)
P = arm.OPTIONS.MOTION_MODE.P; J = arm.OPTIONS.MOTION_MODE.J
def setm(m):
    try: arm.set_motion_mode(m)
    except Exception: pass

arm.clear_joint_error(); setm(J); arm.move_j(OBSERVE); time.sleep(1.5)
print(f"朝向={ACCEPT_RPY} (pitch=1.0, 固件accept), 物体xy={OBJ_XY}\n")

results = []
for z in [0.40, 0.35, 0.30, 0.25, 0.20, 0.162]:
    arm.clear_joint_error(); setm(P)
    target = [OBJ_XY[0], OBJ_XY[1], z] + ACCEPT_RPY
    arm.move_p(target); time.sleep(2.5)
    s = arm.get_arm_status().msg.motion_status
    a = list(arm.get_flange_pose().msg)
    ok = "SUCCESS" in str(s) and abs(a[2]-z) < 0.03
    print(f"  z={z:.3f}  status={s}  实际z={a[2]:.3f}  pitch={a[4]:.3f}  {'✅' if ok else '❌'}")
    results.append((z, ok))
    arm.clear_joint_error(); setm(J)
    try: arm.move_j(OBSERVE)
    except Exception: pass
    time.sleep(1.5)

ok_z = [z for z, ok in results if ok]
print("\n" + "="*50)
print(f"可达高度: {['%.3f'%z for z in ok_z] or '无'}")
if ok_z:
    print(f"→ approach 用 z={min(ok_z):.3f} (GRASP_APPROACH_Z={min(ok_z)-0.042:.3f})")
arm.disconnect()
