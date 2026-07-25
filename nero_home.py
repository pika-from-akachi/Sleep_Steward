"""
NERO 机械零位管理
  set   - 手动摆好姿态后记录为零位
  go    - 自动归到零位
  show  - 显示当前零位
"""
import time
import json
import sys
from pathlib import Path
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

HOME_FILE = Path("/root/nero_home_position.json")
CAN_CONFIG = dict(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                  interface="socketcan", channel="can1")

# 默认零位 (出厂推荐的安全姿态: 各关节接近 0)
FACTORY_ZERO = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def connect():
    cfg = create_agx_arm_config(**CAN_CONFIG)
    arm = AgxArmFactory.create_arm(cfg)
    arm.connect()
    return arm


def set_home():
    """将当前姿态记录为机械零位"""
    arm = connect()
    arm.set_speed_percent(20)
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)

    while not arm.enable():
        time.sleep(0.01)

    ja = arm.get_joint_angles()
    if ja is None:
        print("❌ 无法读取关节角")
        arm.disable()
        return

    position = [round(a, 4) for a in ja.msg]
    HOME_FILE.write_text(json.dumps(position, indent=2))
    print(f"✅ 机械零位已记录: {position}")

    arm.disable()
    arm.disconnect()


def go_home(speed: int = 20):
    """自动归到机械零位"""
    if not HOME_FILE.exists():
        print("⚠️  未设置机械零位, 使用出厂零位")
        target = FACTORY_ZERO
    else:
        target = json.loads(HOME_FILE.read_text())

    arm = connect()
    arm.set_speed_percent(speed)
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)

    while not arm.enable():
        time.sleep(0.01)

    # 读当前位置
    ja = arm.get_joint_angles()
    if ja is None:
        print("❌ 无法读取关节角")
        arm.disable()
        return False

    current = list(ja.msg)
    print(f"当前位置: {[round(a, 4) for a in current]}")
    print(f"机械零位: {[round(a, 4) for a in target]}")

    # 安全检查: 单关节运动幅度
    max_delta = max(abs(target[i] - current[i]) for i in range(7))
    if max_delta > 2.0:
        print(f"❌ 单关节运动 {max_delta:.2f} rad 超过安全阈值 2.0 rad!")
        print("   请先手动把臂摆在接近零位的位置")
        arm.disable()
        return False

    print(f"最大运动幅度: {max_delta:.3f} rad, 安全")
    print("[SAFE] 正在归零...")

    try:
        arm.move_j(target)
        # 等待完成 (最大 30 秒)
        for _ in range(150):
            status = arm.get_arm_status()
            if status and status.msg.motion_status == 0:
                break
            time.sleep(0.2)

        ja2 = arm.get_joint_angles()
        if ja2:
            final = list(ja2.msg)
            error = [abs(final[i] - target[i]) for i in range(7)]
            print(f"最终位置: {[round(a, 4) for a in final]}")
            print(f"误差:     {[round(e, 4) for e in error]}")
            if max(error) < 0.05:
                print("✅ 归零完成")
                return True
            else:
                print("⚠️  归零有偏差, 但运动已安全完成")
                return True
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False
    finally:
        arm.disable()
        arm.disconnect()

    return False


def show_home():
    if HOME_FILE.exists():
        target = json.loads(HOME_FILE.read_text())
        print(f"机械零位: {[round(a, 4) for a in target]}")
    else:
        print(f"机械零位 (未设置, 出厂默认): {FACTORY_ZERO}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "set":
        set_home()
    elif cmd == "go":
        speed = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        go_home(speed)
    elif cmd == "show":
        show_home()
    else:
        print(__doc__)
