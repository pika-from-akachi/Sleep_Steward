---
name: safe-arm-executor
description: 安全执行 NERO 机械臂代码。当用户要求实际运行机械臂代码时触发。自动对生成的代码进行安全检查、修正后执行。
always: true
metadata:
  bins: ["python3"]
---

# 安全机械臂执行器

## 核心安全规则（不可违反！）

### 规则 1: CAN 接口
- **必须**使用 `channel="can1"` (不是 can0)
- **必须**使用 `interface="socketcan"`

### 规则 2: 固件版本
- 用户固件是 **1.121**，使用 `firmeware_version=NeroFW.V112`
- **禁止**调用 `set_normal_mode()` (仅 ≤1.11 固件需要)

### 规则 3: 速度限制
- 首次测试:**必须** `set_speed_percent(20)` (不超过 20%)
- 熟练后可以提高到 50%，**禁止**超过 80%

### 规则 4: 碰撞保护
- **必须** `set_crash_protection_rating(joint_index=255, rating=0)` (最灵敏)
- 关节限位:**必须** `set_joint_limits_enabled(True)`

### 规则 5: 运动范围
- 单次关节运动范围:**不超过 ±0.5 弧度** (~28°)
- 必须**先读取当前位置**，基于当前角度计算目标

### 规则 6: 运动前确认
- 执行运动前**必须**打印目标关节角让用户确认
- 格式:`[SAFE] 目标关节角: [j1, j2, j3, j4, j5, j6, j7]`

### 规则 7: 异常保护
- 代码**必须**包裹在 try/except 中
- except 块中**必须**调用 `arm.disable()` + `arm.disconnect()`

## 代码模板（必须遵循）

```python
import time
import traceback
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

SAFE_SPEED = 20  # 首次必须 20%

try:
    cfg = create_agx_arm_config(
        robot=ArmModel.NERO,
        firmeware_version=NeroFW.V112,
        interface="socketcan",
        channel="can1",
    )
    arm = AgxArmFactory.create_arm(cfg)
    arm.connect()

    # 安全配置
    arm.set_speed_percent(SAFE_SPEED)
    arm.set_crash_protection_rating(joint_index=255, rating=0)
    arm.set_joint_limits_enabled(True)

    # 使能
    while not arm.enable():
        time.sleep(0.01)

    # 读取当前角度
    ja = arm.get_joint_angles()
    if ja is None:
        raise RuntimeError("无法读取关节角")
    home = list(ja.msg)

    # === 用户操作放在这里 ===
    # target = home.copy()
    # target[X] = Y  # 修改目标关节
    # print(f"[SAFE] 目标关节角: {[round(t,4) for t in target]}")
    # arm.move_j(target)

    # 下使能
    arm.disable()
    arm.disconnect()

except Exception as e:
    print(f"[SAFETY] 异常: {e}")
    traceback.print_exc()
    try:
        arm.disable()
        arm.disconnect()
    except:
        pass
```

## 禁止操作
- ❌ set_normal_mode()
- ❌ move_mit() (阻抗控制, 参数不对会损坏电机)
- ❌ set_speed_percent(>50)
- ❌ 单关节移动 >0.5 rad
- ❌ channel="can0"
- ❌ firmeware_version=NeroFW.DEFAULT (用户是 V112)
- ❌ 不读当前角度直接设置 target
