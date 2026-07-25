"""诊断 move_p: 到当前位姿能否原地 (验证 RPY 约定一致性)。

测1: move_p(当前flange位姿) - 应原地不动 status=0
测2: move_p(z+0.05, 其余不变) - 应上升 5cm
若测1 失败 → move_p 的 RPY 约定和反馈不一致 (核心 bug)

用法: python3 diag_move_p2.py
"""
import subprocess, time
import numpy as np
np.float = float; np.int = int; np.bool = bool
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

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
try: arm.set_motion_mode(arm.OPTIONS.MOTION_MODE.P)
except Exception: pass

def fp(): return list(arm.get_flange_pose().msg)
def st(): return arm.get_arm_status().msg.motion_status

cur0 = fp()
print(f"当前 flange: {np.round(cur0, 4).tolist()}")

print("\n[测1] move_p(当前 flange 位姿) — 期望原地不动, status=0")
arm.clear_joint_error(); arm.move_p(list(cur0)); time.sleep(2.0)
c = fp(); print(f"  status={st()}  z={c[2]:.4f} (原 {cur0[2]:.4f})  rpy={np.round(c[3:],4).tolist()}")

print("\n[测2] move_p(z+0.05, 其余不变) — 期望上升 5cm")
t2 = list(cur0); t2[2] = cur0[2] + 0.05
arm.clear_joint_error(); arm.move_p(t2); time.sleep(2.0)
c = fp(); print(f"  status={st()}  z={c[2]:.4f} (目标 {t2[2]:.4f})")

print("\n[测3] move_p(z-0.05, 其余不变) — 期望下降 5cm")
t3 = list(cur0); t3[2] = cur0[2] - 0.05
arm.clear_joint_error(); arm.move_p(t3); time.sleep(2.0)
c = fp(); print(f"  status={st()}  z={c[2]:.4f} (目标 {t3[2]:.4f})")

arm.disconnect()
print("\n结论: 测1失败=RPY约定不匹配; 测1成&测2/3成=move_p正常, 之前是xy问题")
