"""示教中间位置 — 使能状态下手动点动关节, 摆好后保存。

用法:
    python3 teach_mid.py                # 点动摆臂, Enter保存
    python3 teach_mid.py --go           # 去已保存的中间位置
    python3 teach_mid.py --show         # 查看已保存位置

点动: 输入关节编号(1-7)和方向(+/-/++/--), 例如:
    1+   = 关节1 +0.05rad       1-   = 关节1 -0.05rad
    1++  = 关节1 +0.2rad        1--  = 关节1 -0.2rad
    Enter = 保存当前位置         q    = 退出不保存
"""
import json, sys, time
from pathlib import Path
from arm_control import NeroArm

MID_FILE = Path(__file__).parent / "calibration" / "mid_pose.json"


def activate_can():
    import subprocess
    subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
    time.sleep(0.5)


def show_joints(joints):
    print(f"  J1:{joints[0]:7.3f}  J2:{joints[1]:7.3f}  J3:{joints[2]:7.3f}  "
          f"J4:{joints[3]:7.3f}  J5:{joints[4]:7.3f}  J6:{joints[5]:7.3f}  "
          f"J7:{joints[6]:7.3f}")


def main():
    if "--show" in sys.argv:
        if MID_FILE.exists():
            d = json.loads(MID_FILE.read_text())
            show_joints(d["joints"])
        else:
            print("尚未保存中间位置")
        return

    activate_can()
    arm = NeroArm()
    arm.connect(speed_pct=15)

    if "--go" in sys.argv:
        if not MID_FILE.exists():
            print("尚未保存中间位置"); sys.exit(1)
        d = json.loads(MID_FILE.read_text())
        print("去中间位置...")
        arm.move_joints(d["joints"], speed_pct=20, timeout=60)
        print("✅ 到达")
        arm.disconnect()
        return

    # ── 点动模式 ──
    arm.enable()
    print("=" * 60)
    print("  点动摆臂: 1+/-  1++/--   Enter=保存  q=退出")
    show_joints(arm.get_joint_angles())
    print("=" * 60)

    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "":
            joints = arm.get_joint_angles()
            MID_FILE.parent.mkdir(parents=True, exist_ok=True)
            MID_FILE.write_text(json.dumps({"joints": joints}, indent=2))
            print(f"✅ 已保存中间位置")
            break
        if cmd.lower() == "q":
            print("退出, 未保存")
            break

        # 解析: 关节编号 + 方向
        import re
        m = re.match(r'(\d)\s*(\+\+|\-\-|\+|\-)', cmd)
        if not m:
            print("  格式: 1+ / 2- / 3++ / 4-- / Enter / q")
            continue

        j = int(m.group(1)) - 1
        direction = m.group(2)
        if j < 0 or j > 6:
            print("  关节编号 1-7")
            continue

        delta = 0.2 if len(direction) == 2 else 0.05
        if direction[0] == '-':
            delta = -delta

        joints = arm.get_joint_angles()
        joints[j] += delta
        try:
            arm.move_joints(joints, speed_pct=10, timeout=5.0)
            show_joints(arm.get_joint_angles())
        except Exception as e:
            print(f"  ⚠️ 移动失败: {e}")

    arm.disconnect()


if __name__ == "__main__":
    main()
