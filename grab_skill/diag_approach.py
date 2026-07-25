"""诊断: approach 位姿多高才可达 (找 NERO 工作空间下限)。

不动夹爪, 只测臂能否 move_p 到物体上方的不同高度 (保持观测朝向)。
每次测完回观测姿态。找出最低可达 z, 作为 approach 高度。

用法: python3 diag_approach.py
"""
import subprocess, time, json
from pathlib import Path
import numpy as np
np.float = float; np.int = int; np.bool = bool
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

OBSERVE = list(json.loads(Path("/root/grab_skill/calibration/base_pose.json").read_text())["joints"])
OBJ_XY = [-0.063, 0.435]   # 上次物体基座系 xy (可达性诊断用, 小偏差不影响)

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

def tcp(): return list(arm.get_tcp_pose().msg)
def status(): return arm.get_arm_status().msg.motion_status
def set_mode(m):
    try: arm.set_motion_mode(m)
    except Exception as e: print(f"  (set_mode {m} err: {e})")

P = arm.OPTIONS.MOTION_MODE.P
J = arm.OPTIONS.MOTION_MODE.J
print(f"auto_set_motion_mode_enabled: {arm.get_auto_set_motion_mode_enabled()}")

# 回观测姿态 (J 模式)
arm.clear_joint_error(); set_mode(J); arm.move_j(OBSERVE); time.sleep(1.5)
cur = tcp()
rpy = cur[3:]
print(f"观测姿态: tcp_z={cur[2]:.3f}  rpy={np.round(rpy,3).tolist()}")
print(f"\n测试物体上方不同高度 (xy={OBJ_XY}, 朝向=观测朝向, P模式):\n")

results = []
for z in [0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.162]:
    arm.clear_joint_error()
    set_mode(P)   # ← move_p 前显式设 P 模式
    target = [OBJ_XY[0], OBJ_XY[1], z] + rpy
    arm.move_p(target)
    time.sleep(2.5)   # 等运动完成
    s = status()
    az = tcp()[2]
    ok = (str(s) == "0" or "0" in str(s)) and abs(az - z) < 0.03
    flag = "✅可达" if ok else f"❌{s}"
    print(f"  目标 z={z:.3f}  →  实际z={az:.3f}  status={s}  {flag}")
    results.append((z, ok))
    # 回观测 (J 模式)
    arm.clear_joint_error(); set_mode(J)
    try: arm.move_j(OBSERVE)
    except Exception: pass
    time.sleep(1.5)

reachable = [z for z, ok in results if ok]
print("\n" + "=" * 50)
if reachable:
    print(f"✅ 可达的最低高度: z={min(reachable):.3f}m")
    print(f"   建议 approach 高度 ≥ {min(reachable) - OBJ_XY[1]*0 + 0.02:.3f}m")
    print(f"   (物体在 z≈0.042, 建议 approach 距物体 ≥ {min(reachable)-0.042:.3f}m)")
else:
    print("❌ 所有高度都不可达 — xy 或朝向在工作空间外")
arm.disconnect()
