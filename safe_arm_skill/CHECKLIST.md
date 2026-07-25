# NERO 安全执行器 - 验证清单

## 运行环境

```bash
ssh root@192.168.128.10
cd /root/nanobot_workspace
```

---

## 验证 1: 安全检查器能拦截危险代码

**命令:**
```bash
python3 /root/safe_arm_skill/verify_safety.py
```

**输入** (粘贴这段故意有问题的代码, 然后输入 END):
```python
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO,
    firmeware_version=NeroFW.DEFAULT,
    interface="socketcan", channel="can0")
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
arm.set_normal_mode()
arm.enable()
arm.set_speed_percent(100)
arm.move_j([0, 0, 0, 0, 0, 0, 0])
arm.disable()
END
```

**预期结果:** ❌ 不通过, 应该报出以下问题:
- ❌ CAN口: can0 不是 can1
- ❌ 固件: NeroFW.DEFAULT 不是 V112
- ❌ 禁止项: set_normal_mode
- ❌ 速度: 100% 超过 50%
- ❌ 缺少碰撞保护
- ❌ 缺少关节限位
- ❌ 没读当前角度

---

## 验证 2: 安全代码能通过审查

**命令:**
```bash
python3 /root/safe_arm_skill/verify_safety.py
```

**输入** (粘贴这段安全代码):
```python
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
try:
    cfg = create_agx_arm_config(robot=ArmModel.NERO,
        firmeware_version=NeroFW.V112,
        interface="socketcan", channel="can1")
    arm = AgxArmFactory.create_arm(cfg)
    arm.connect()
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)
    arm.set_speed_percent(20)
    while not arm.enable():
        time.sleep(0.01)
    ja = arm.get_joint_angles()
    home = list(ja.msg)
    target = home.copy()
    target[6] += 0.05
    print(f"[SAFE] 目标: {[round(t,4) for t in target]}")
    arm.move_j(target)
    time.sleep(1)
    arm.disable()
    arm.disconnect()
except Exception as e:
    print(f"[SAFETY] 异常: {e}")
    try:
        arm.disable()
        arm.disconnect()
    except:
        pass
END
```

**预期结果:** ✅ 全部通过

---

## 验证 3: Agent 生成代码 + 安全检查器

**命令:**
```bash
timeout 90 /root/nanobot_venv/bin/nanobot agent \
  -w /root/nanobot_workspace \
  -c /root/.nanobot/config.json \
  -m "使用 agx-arm-codegen 和 safe-arm-executor 技能，生成让 NERO 第7关节运动 0.05 弧度然后回原位的安全代码。只输出 Python 代码。"
```

**然后运行:**
```bash
python3 /root/safe_arm_skill/verify_safety.py /tmp/agent_code.py
```

**预期结果:** Agent 生成代码 → 安全检查器通过 ✅

---

## 验证 4: 在机械臂上实际执行 🚨

**前置条件:** NERO 上电, CAN 连接, 机械臂无障碍

```bash
# 确保 CAN 激活
sudo ip link set can1 up type can bitrate 1000000

# 先用纯通信测试(不动)
python3 -c "
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface='socketcan', channel='can1')
arm = AgxArmFactory.create_arm(cfg); arm.connect()
print('通信OK')
ja = arm.get_joint_angles()
print('关节角:', [round(a,4) for a in ja.msg] if ja else '无数据')
arm.disconnect()
"

# 通信OK后跑验证脚本，输入安全代码 + 输入 yes 执行
python3 /root/safe_arm_skill/verify_safety.py
```

**预期结果:** J7 微动 0.05 rad → 回原位，机械臂平稳运动

---

## 达标判定

| 验证项 | 通过标准 |
|------|------|
| ✅ 验证1 | 安全检查器拦截 7 个危险项 |
| ✅ 验证2 | 安全代码 100% 通过审查 |
| ✅ 验证3 | Agent 生成代码通过审查 |
| ✅ 验证4 | 实机运动平稳, 无抖动/碰撞 (可选) |

前三项通过即**达标**。
