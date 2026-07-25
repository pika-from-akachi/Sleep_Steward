"""只读当前关节角 vs 零位, 判断是回绕假象还是真的远 (不产生任何运动)"""
import math, subprocess, time
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.5)
from arm_control import NeroArm

with NeroArm() as arm:
    j = arm.get_joint_angles()
    h = arm.get_home_position()

print("current:", [round(x, 3) for x in j])
print("home:   ", [round(x, 3) for x in h])
worst_raw = worst_wrap = 0.0
for i, (c, t) in enumerate(zip(j, h)):
    d = abs(c - t)
    dw = min(d, 2 * math.pi - d)   # 考虑回绕的最短角距
    flag = "  ← wrap假象(短路径很小)" if dw < d - 0.1 else ""
    print(f"  j{i}: cur={c:+.3f} home={t:+.3f}  rawΔ={d:.3f}  wrapΔ={dw:.3f}{flag}")
    worst_raw, worst_wrap = max(worst_raw, d), max(worst_wrap, dw)
print(f"\nmax rawΔ={worst_raw:.3f} rad   max wrapΔ={worst_wrap:.3f} rad")
print("→ wrapΔ < 2.0 说明是回绕假象, 可走短路径归零; 否则真的远, 需手动/分步。")
