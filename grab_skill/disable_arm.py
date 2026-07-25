"""人工下使能机械臂 —— 按需运行。

⚠️ arm_control.py 已改为"不自动下使能"。臂用完若要下使能(电机掉电),
   人工运行本脚本:  python3 disable_arm.py
"""
import subprocess, time
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.5)

from arm_control import NeroArm

arm = NeroArm()
arm.connect()
arm.enable()      # 先确保使能状态可读
arm.disable()     # ← 人工下使能
arm.disconnect()  # 仅断开, 不再下使能
print("✅ 已人工下使能, 电机掉电")
