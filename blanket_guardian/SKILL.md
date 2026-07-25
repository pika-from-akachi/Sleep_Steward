---
name: blanket-guardian
description: 盖被子机器人核心技能。当用户需要监测小朋友踢被子、自动盖被子时触发。支持摄像头监测、VLM 视觉分析、NERO机械臂抓取被子、TRACER底盘导航。
metadata:
  bins: ["python3", "ffmpeg"]
---

# 盖被子机器人技能

## 触发条件

- 用户说"开始守护"、"盖被子"、"监测被子"、"夜间守护"等
- 定时自动触发 (每30秒检查)

## 工作流程

### 1. 视觉监测
- 使用 ffmpeg 从 `/dev/video0` 拍照
- 调用 StepFun `step-3.7-flash` VLM 分析图像
- 检测: 是否有人? 被子盖着吗? 盖到哪个位置?

### 2. 踢被子判定
- VLM 返回 `covered=false` 或 `cover_level=chest_below` → 可能踢被子
- 连续 3 次确认 → 触发盖被子动作

### 3. 盖被子动作序列
1. NERO 展开到观察位姿
2. TRACER 缓慢靠近床边
3. NERO 抓被子边缘 → 夹爪闭合
4. NERO 向上拉被子到胸口位置
5. 夹爪松开
6. TRACER 后退
7. NERO 回收

### 4. 安全保护
- NERO 速度限制 20%
- 碰撞检测最灵敏
- 遥控器始终可以接管
- 异常时自动急停

## API 参考

### pyAgxArm (NERO 控制)
- 连接: `create_agx_arm_config(robot=ArmModel.NERO, interface="socketcan", channel="can1")`
- 使能: `arm.enable()`
- 关节运动: `arm.move_j([j1,j2,j3,j4,j5,j6,j7])`
- 夹爪: `gripper = arm.init_effector(arm.OPTIONS.EFFECTOR.AGX_GRIPPER)`
- 夹爪闭合: `gripper.move_gripper_deg(0)`
- 夹爪张开: `gripper.move_gripper_m(0.07)`

### TRACER (底盘控制)
- 通过 ROS2 topic `/cmd_vel` (geometry_msgs/Twist)
- 启动: `ros2 launch tracer_base tracer_base.launch.py port_name:=can1`
- 前进: `linear.x > 0` (m/s)
- 后退: `linear.x < 0`

### 预设位姿 (保存在 nero_poses.json)
- `home`: 收纳位
- `observe`: 观察位 (看向床)
- `grab_blanket`: 抓被子边缘
- `pull_up`: 把被子拉到胸口

## 运行

```bash
cd /root/blanket_guardian
python3 blanket_guardian.py
```
