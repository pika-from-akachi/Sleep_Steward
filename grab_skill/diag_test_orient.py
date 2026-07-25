"""诊断: 固件 IK 接受哪些朝向 (找能用于 move_p 抓取的朝向)。

原地改朝向 (xyz 不变), 测多个候选, 看固件 status=0 的是哪些。
每个测完回观测姿态。臂原地转朝向, 不位移, 相对安全。

用法: python3 diag_test_orient.py
"""
import subprocess, time, json, math
from pathlib import Path
import numpy as np
np.float = float; np.int = int; np.bool = bool
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

OBSERVE = list(json.loads(Path("/root/grab_skill/calibration/base_pose.json").read_text())["joints"])

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

# 回观测
arm.clear_joint_error(); setm(J); arm.move_j(OBSERVE); time.sleep(1.5)
cur = list(arm.get_flange_pose().msg)
xyz = cur[:3]
print(f"当前 flange xyz={np.round(xyz,3).tolist()}  观测rpy={np.round(cur[3:],3).tolist()}")
print(f"\n原地测各朝向 (xyz 固定={np.round(xyz,3).tolist()}):\n")

def clamp(rpy):
    return [max(-3.13, min(3.13, rpy[0])),
            max(-1.56, min(1.56, rpy[1])),
            max(-3.13, min(3.13, rpy[2]))]

cands = [
    ("观测原朝向",   [1.094, 1.305, 1.402]),
    ("官方例子朝向", [-1.5708, 0.0, -3.13]),
    ("pitch降到1.0", [1.094, 1.0, 1.402]),
    ("pitch降到0.5", [1.094, 0.5, 1.402]),
    ("pitch=0",      [1.094, 0.0, 1.402]),
    ("roll=π pitch=0",[3.13, 0.0, 0.0]),
    ("pitch=π/2垂直", [0.0, 1.56, 0.0]),
]

for name, rpy in cands:
    rc = clamp(rpy)
    target = list(xyz) + rc
    arm.clear_joint_error(); setm(P)
    arm.move_p(target); time.sleep(2.5)
    s = arm.get_arm_status().msg.motion_status
    a = list(arm.get_flange_pose().msg)
    ok = "0" in str(s) and abs(a[4]-rc[1]) < 0.1
    print(f"  {name:14s} rpy={np.round(rc,3).tolist()}  status={s}  实际pitch={a[4]:.3f}  {'✅' if ok else '❌'}")
    # 回观测
    arm.clear_joint_error(); setm(J)
    try: arm.move_j(OBSERVE)
    except Exception: pass
    time.sleep(1.5)

arm.disconnect()
print("\n→ 选 ✅ 且朝向下 (能抓物体) 的朝向作为 GRASP_RPY")
