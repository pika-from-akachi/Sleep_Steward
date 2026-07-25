"""只读: 关节角 + TCP 位姿 + 零位, 用于确认 NERO 的坐标系约定 (不产生运动)"""
import subprocess, time
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.5)
from arm_control import NeroArm

with NeroArm() as arm:
    j = arm.get_joint_angles()
    tcp = arm.get_tcp_pose()
    home = arm.get_home_position()

print("joints :", None if j is None else [round(x, 3) for x in j])
print("home   :", [round(x, 3) for x in home])
print("tcp    :", None if tcp is None else [round(x, 4) for x in tcp])
if tcp:
    x, y, z, r, p, yw = tcp
    print(f"  → TCP 位置 (基座系): x={x:.3f} y={y:.3f} z={z:.3f} (m)")
    import math
    print(f"  → TCP 姿态 RPY (rad): roll={r:.3f}({math.degrees(r):.0f}°) "
          f"pitch={p:.3f}({math.degrees(p):.0f}°) yaw={yw:.3f}({math.degrees(yw):.0f}°)")
    print("判断: z 通常=高度(朝上), x 通常=前方距离; 若 tcp 接近 home 则臂在零位。")
