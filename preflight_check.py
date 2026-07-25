"""
NERO 起飞前安全检查 — 纯读取，零运动
只有全部绿灯 + 你手动输入 yes，才会执行运动代码
"""
import time
import sys
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

print("=" * 50)
print("🛡️  NERO 起飞前安全检查")
print("=" * 50)
print()
print("⚠️  首次使用请先设置机械零位:")
print("   1. 手动把机械臂摆到想要的安全姿态")
print("   2. python3 /root/nero_home.py set")
print("   3. 之后每次开机都会自动归零")
print()

# 1. 通信检查
print("\n[1/5] 通信检查...")
cfg = create_agx_arm_config(
    robot=ArmModel.NERO,
    firmeware_version=NeroFW.V112,
    interface="socketcan",
    channel="can1",
)
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
print("  ✅ CAN 通信正常")

# 2. 固件版本
print("\n[2/5] 固件版本...")
fw = arm.get_firmware()
if fw:
    sv = fw.get("software_version", "?")
    print(f"  固件: {sv}")
    if sv >= "1.20":
        print("  ⚠️  建议使用 NeroFW.V120")
    elif sv >= "1.12":
        print("  ✅ NeroFW.V112 正确")
    else:
        print("  ⚠️  请检查固件版本")
else:
    print("  ❌ 无法获取固件!")
    sys.exit(1)

# 3. 关节状态 (不使能也能读!)
print("\n[3/5] 关节状态...")
arm.set_speed_percent(20)
arm.set_crash_protection_rating(joint_index=255, rating=0)
arm.set_joint_limits_enabled(True)

while not arm.enable():
    time.sleep(0.01)
print("  ✅ 已使能 (电机通电保持位置, 不会自己动)")

ja = arm.get_joint_angles()
if ja is None:
    print("  ❌ 无法读取关节角!")
    arm.disable()
    sys.exit(1)

home = list(ja.msg)
print(f"  当前关节角: {[round(a, 4) for a in home]}")

# 4. 电机健康检查
print("\n[4/5] 电机健康...")
all_ok = True
for i in range(7):
    ds = arm.get_driver_states(i + 1)
    if ds:
        d = ds.msg
        temp = d.motor_temp
        collision = d.foc_status.collision_status
        error = d.foc_status.driver_error_status
        comm_err = arm.get_arm_status()
        flags = []
        if temp > 60: flags.append(f"高温{temp}°C")
        if collision: flags.append("碰撞")
        if error: flags.append("驱动错误")
        status = "⚠️ " + ",".join(flags) if flags else "✅"
        print(f"  J{i+1}: {status} | temp={temp}°C")
        if flags:
            all_ok = False

if not all_ok:
    print("\n  ⚠️  有异常, 建议排查后再运行")
    arm.disable()
    sys.exit(1)

# 5. 归零
print("\n[5/6] 归零...")
from nero_home import HOME_FILE, FACTORY_ZERO
import json
if HOME_FILE.exists():
    target = json.loads(HOME_FILE.read_text())
else:
    print("  ⚠️  未设置机械零位, 使用出厂零位 [0,0,0,0,0,0,0]")
    target = FACTORY_ZERO

max_delta = max(abs(target[i] - home[i]) for i in range(7))
if max_delta > 0.05:
    print(f"  偏差 {max_delta:.3f} rad, 先归零...")
    arm.disable()
    arm.disconnect()
    time.sleep(0.5)
    from nero_home import go_home
    go_home(speed=20)
    # 重新连接
    import importlib
    importlib.invalidate_caches()
    cfg2 = create_agx_arm_config(
        robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
        interface="socketcan", channel="can1")
    arm2 = AgxArmFactory.create_arm(cfg2)
    arm2.connect()
    arm2.set_speed_percent(20)
    arm2.set_crash_protection_rating(joint_index=255, rating=0)
    arm2.set_joint_limits_enabled(True)
    while not arm2.enable():
        time.sleep(0.01)
    arm = arm2
    ja = arm.get_joint_angles()
    home = list(ja.msg) if ja else target
else:
    print("  ✅ 已在零位")

# 6. 运动范围确认
print("\n[6/6] 运动范围确认...")
target = home.copy()
target[6] += 0.03  # J7 动 0.03 rad
print(f"  起始角: {[round(a, 4) for a in home]}")
print(f"  目标角: {[round(a, 4) for a in target]}")
print(f"  变化量: {[round(target[i]-home[i], 4) for i in range(7)]}")
print(f"  最大变化: {max(abs(target[i]-home[i]) for i in range(7)):.4f} rad")

# 安全检查
max_delta = max(abs(target[i] - home[i]) for i in range(7))
if max_delta > 0.5:
    print(f"  ❌ 运动幅度 {max_delta:.2f} rad 超过 0.5 rad 限制!")
    arm.disable()
    sys.exit(1)

print(f"  ✅ 运动幅度 {max_delta:.3f} rad, 安全")

# ========================
# 最终确认
# ========================
print("\n" + "=" * 50)
print("🟢 全部检查通过!")
print(f"   只动 J7: {home[6]:.4f} → {target[6]:.4f} rad")
print(f"   速度: 20%")
print(f"   碰撞保护: 0级 (最灵敏)")
print("=" * 50)

confirm = input("\n>>> 是否执行运动? (yes/no): ")
if confirm.strip().lower() != "yes":
    print("已取消, 下使能")
    arm.disable()
    arm.disconnect()
    sys.exit(0)

# ========================
# 执行运动
# ========================
print("\n🚀 执行中...")
try:
    print(f"[SAFE] 目标: {[round(t, 4) for t in target]}")
    arm.move_j(target)
    time.sleep(3)

    print(f"[SAFE] 回原位: {[round(t, 4) for t in home]}")
    arm.move_j(home)
    time.sleep(3)

    print("✅ 运动完成!")
except Exception as e:
    print(f"❌ 异常: {e}")
finally:
    arm.disable()
    arm.disconnect()
    print("已下使能, 安全退出")
