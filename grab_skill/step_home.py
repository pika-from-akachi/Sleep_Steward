"""分步归零: 每步每个关节最多走 STEP rad, 慢速, 每步按 Enter 才继续, q 停止。
⚠️ 必须在设备终端交互式运行 (有 input 确认); 运行前确认臂周围无遮挡、可随时急停。

用法:  python3 step_home.py
"""
import math, subprocess, time

STEP = 1.0      # 每步每关节最大移动量 (rad) —— < go_home 的 2.0 安全阈值
SPEED = 10      # 慢速 %

subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.5)

from arm_control import NeroArm

with NeroArm() as arm:
    home = arm.get_home_position()
    print("零位目标:", [round(t, 3) for t in home])
    print(f"每步每关节 ≤ {STEP} rad, 速度 {SPEED}%, 每步按 Enter 继续, q 退出\n")

    step = 0
    while True:
        cur = arm.get_joint_angles()
        if cur is None:
            print("读关节角失败"); break
        delta = [home[i] - cur[i] for i in range(7)]
        maxd = max(abs(d) for d in delta)

        if maxd < 0.05:
            print(f"\n✅ 已到零位 (maxΔ={maxd:.4f} rad)")
            break

        # 本步目标: 朝 home 走, 每关节限幅 ±STEP
        target = [cur[i] + max(-STEP, min(STEP, delta[i])) for i in range(7)]
        step += 1
        print(f"[步{step}] maxΔ={maxd:.3f} rad")
        print(f"   当前: {[round(c,2) for c in cur]}")
        print(f"   →此步: {[round(t,2) for t in target]}")

        ans = input("   按 Enter 移动 (q 退出): ").strip().lower()
        if ans == "q":
            print("已中止, 臂停在当前位置"); break

        try:
            arm.move_joints(target, speed_pct=SPEED)
        except Exception as e:
            print(f"   ❌ 运动失败: {e}"); break

    # 收尾: 报告最终偏差
    cur = arm.get_joint_angles()
    if cur:
        err = max(abs(cur[i] - home[i]) for i in range(7))
        print(f"\n最终 maxΔ={err:.3f} rad  (go_home 阈值 2.0, <0.05 视为到位)")
