"""
NERO 开机归零 — 一条命令从任意位置到零位
用法: python3 nero_startup.py
"""
import time
import json
import subprocess
import sys
from pathlib import Path
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

HOME_FILE = Path("/root/nero_home_position.json")
FACTORY_ZERO = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def activate_can():
    cmd = "ip link set can1 up type can bitrate 1000000 2>/dev/null"
    subprocess.run(cmd, shell=True)
    time.sleep(0.5)


def get_home():
    if HOME_FILE.exists():
        return json.loads(HOME_FILE.read_text())
    return FACTORY_ZERO


activate_can()

cfg = create_agx_arm_config(
    robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
    interface="socketcan", channel="can1",
)
arm = AgxArmFactory.create_arm(cfg)
arm.connect()

arm.set_speed_percent(20)
arm.set_crash_protection_rating(joint_index=255, rating=0)
arm.set_joint_limits_enabled(True)

while not arm.enable():
    time.sleep(0.01)
print("已使能")

ja = arm.get_joint_angles()
if ja is None:
    print("无法读取关节角")
    sys.exit(1)

current = list(ja.msg)
target = get_home()

print(f"当前: {[round(a, 4) for a in current]}")
print(f"零位: {[round(a, 4) for a in target]}")

# 安全检查 (多轴连续运动, 3.5 rad ~200° 对7轴臂安全)
delta = max(abs(target[i] - current[i]) for i in range(7))
if delta > 3.5:
    print(f"偏差 {delta:.2f} rad > 3.5, 请手动摆近些")
    arm.disable()
    sys.exit(1)
if delta > 2.0:
    print(f"⚠️  大幅运动 {delta:.2f} rad, 确认周围无障碍")

# 归零
print(f"归零中 (最大幅度 {delta:.3f} rad)...")
arm.move_j(target)

# 等待完成
for _ in range(150):
    s = arm.get_arm_status()
    if s and s.msg.motion_status == 0:
        break
    time.sleep(0.2)

# 验证
ja2 = arm.get_joint_angles()
if ja2:
    final = list(ja2.msg)
    err = max(abs(final[i] - target[i]) for i in range(7))
    print(f"完成! 误差 {err:.4f} rad" if err < 0.05 else f"完成, 偏差 {err:.4f}")

print("✅ 归零完成, 保持使能 (Ctrl+C 退出并下使能)")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n下使能中...")
finally:
    arm.disable()
    arm.disconnect()
    print("已下使能")
