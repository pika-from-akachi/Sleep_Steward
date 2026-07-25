"""示教放置位置 — 把臂摆到放置点正上方, 记录 flange 位姿。

用法:
    python3 teach_place.py                # 点动摆臂, Enter保存
    python3 teach_place.py --show         # 查看已保存的放置位置
    python3 teach_place.py --go           # 去已保存的放置位置 (验证用)

点动: 1+ / 1- / 1++ / 1-- / Enter=保存 / q=退出
"""
import json, sys, time
from pathlib import Path
from arm_control import NeroArm

PLACE_FILE = Path(__file__).parent / "calibration" / "place_pose.json"


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
        if PLACE_FILE.exists():
            d = json.loads(PLACE_FILE.read_text())
            p = d["flange"]
            print(f"放置点 flange: x={p[0]:.4f} y={p[1]:.4f} z={p[2]:.4f} "
                  f"r={p[3]:.4f} p={p[4]:.4f} y={p[5]:.4f}")
        else:
            print("尚未保存放置位置")
        return

    activate_can()
    arm = NeroArm()
    arm.connect(speed_pct=15)

    if "--go" in sys.argv:
        if not PLACE_FILE.exists():
            print("尚未保存放置位置"); sys.exit(1)
        d = json.loads(PLACE_FILE.read_text())
        fp = d["flange"]
        print(f"去放置位置: {[round(v,4) for v in fp]}")
        arm.move_to_pose(fp, speed_pct=15, safe_z_first=False, timeout=20.0)
        print("✅ 到达")
        arm.disconnect()
        return

    # ── 点动模式 ──
    arm.enable()
    print("=" * 60)
    print("  把臂摆到放置点正上方, 然后 Enter=保存")
    print("  点动: 1+/-  1++/--  Enter=保存  q=退出")
    show_joints(arm.get_joint_angles())
    fp = arm.get_flange_pose()
    if fp: print(f"  flange: x={fp[0]:.4f} y={fp[1]:.4f} z={fp[2]:.4f}")
    print("=" * 60)

    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "":
            fp = arm.get_flange_pose()
            if fp is None:
                print("⚠️ 无法读取 flange 位姿")
                continue
            PLACE_FILE.parent.mkdir(parents=True, exist_ok=True)
            PLACE_FILE.write_text(json.dumps({"flange": fp}, indent=2))
            print(f"✅ 已保存放置位置: x={fp[0]:.4f} y={fp[1]:.4f} z={fp[2]:.4f}")
            break
        if cmd.lower() == "q":
            print("退出, 未保存")
            break

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
            fp = arm.get_flange_pose()
            if fp: print(f"  flange: x={fp[0]:.4f} y={fp[1]:.4f} z={fp[2]:.4f}")
        except Exception as e:
            print(f"  ⚠️ 移动失败: {e}")

    arm.disconnect()


if __name__ == "__main__":
    main()
