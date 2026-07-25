<div align="center">

# 🛏️ Sleep Steward（睡眠管家）

**NERO 机械臂视觉抓取 + Tracer 移动底盘 + nanobot AI 智能体**  
*Eye-in-hand Visual Grasping · Mobile Base · AI Agent Orchestration*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ROS2](https://img.shields.io/badge/ROS2-Humble-22314E?logo=ros)](https://docs.ros.org/en/humble/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-RDK%20X5-E60012?)](https://developer.horizon.ai/)

</div>

---

## 项目简介

**Sleep Steward** 是一个运行在 RDK X5 上的机器人综合系统，核心能力：

- 🤖 **视觉抓取**：云端 VLM 检测物体 → 深度 3D 定位 → 机械臂抓取+放置
- 🚗 **底盘移动**：Tracer 差速底盘 CAN 直控
- 🧠 **nanobot 智能体**：AI agent 统一编排硬件设备和云端服务

---

## 硬件架构

```
┌─────────────────────────────────────────────────────────┐
│                       RDK X5                            │
│   ┌──────────┐  ┌──────────┐                       │
│   │ nanobot  │  │ ROS2     │                       │
│   │ AI Agent │  │ Humble   │                       │
│   └────┬─────┘  └────┬─────┘                       │
│        │             │                              │
│   ┌────┴─────────────┴─────────────────────────┐    │
│   │              CAN bus / USB                      │    │
│   │  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │    │
│   │  │ NERO 臂  │  │ Tracer   │  │ Orbbec DC1  │  │    │
│   │  │ 7-DOF    │  │ 差速底盘  │  │ RGB-D 相机   │  │    │
│   │  │ CAN1@1M  │  │ CAN@500k │  │ USB 2.0     │  │    │
│   │  └──────────┘  └──────────┘  └─────────────┘  │    │
│   └────────────────────────────────────────────────┘    │
│                         │                               │
│                    ┌────┴────┐                          │
│                    │  StepFun │  云端 VLM 检测            │
│                    │  API     │  step-3.7-flash          │
│                    └─────────┘                          │
└─────────────────────────────────────────────────────────┘
```

| 设备 | 接口 | 用途 |
|---|---|---|
| **RDK X5** | — | 主控 (地平线 ARM Ubuntu 22.04) |
| **NERO 机械臂** | CAN1 @ 1Mbps | 7-DOF 抓取 |
| **Orbbec DaBai DC1** | USB 2.0 | 眼在手上 RGB-D |
| **Tracer 1.0** | CAN @ 500kbps | 移动底盘 |
| **StepFun API** | HTTPS | 云端 VLM 目标检测 |

---

## 目录结构

```
ring_sound_SDK/
├── grab_skill/                # 🎯 视觉抓取核心
│   ├── grab_main.py           #   主入口：检测→定位→抓取→放置
│   ├── arm_control.py         #   NERO 臂安全控制器 (pyAgxArm)
│   ├── camera.py              #   Orbbec 相机 (时域滤波 + 深度对齐)
│   ├── detector.py            #   StepFun VLM 物体检测器
│   ├── transforms.py          #   眼在手上坐标变换
│   ├── calib_full.py          #   全关节手眼标定 (40姿态)
│   ├── set_base.py            #   观测基准姿态设置
│   ├── teach_mid.py           #   中间位置示教 (抓取后过渡位)
│   ├── calibrate.py           #   手眼标定工具
│   └── calibration/           #   标定数据 + 姿态文件
│       ├── base_pose.json     #   观测姿态关节角
│       └── mid_pose.json      #   中间位置关节角 (示教)
├── blanket_guardian/          # 🛏️ 盖被子机器人 (开发中)
│   ├── blanket_guardian.py    #   主控制程序
│   ├── vlm_detector.py        #   VLM 踢被子检测
│   └── teach_and_test.py      #   位姿示教工具
├── safe_arm_skill/            # 🛡️ 机械臂安全验证
├── tracer_test.py             #   底盘运动测试
├── tracer_keyboard.py         #   底盘键盘遥控
├── nanobot_config.json        #   nanobot AI 配置
├── setup_nero_x5.sh           #   NERO 环境一键安装
├── setup_nanobot_x5.sh        #   nanobot 环境安装
└── LICENSE
```

---

## nanobot 智能体

### 什么是 nanobot

**nanobot** 是运行在 RDK X5 上的 AI agent 框架，作为整个系统的"大脑"：

- 接收自然语言指令 → 拆解为具体操作 → 调用硬件/云端资源 → 反馈结果
- 统一管理 NERO 臂、相机、底盘、VLM API 等所有资源
- 通过 `skills/` 目录下的技能文件扩展能力

### nanobot 在全流程中的角色

```
用户: "把桌上的饮料瓶放到黄色胶带旁边"
         │
    ┌────▼────────────────────────────────────┐
    │           nanobot AI Agent               │
    │                                          │
    │  1. 解析指令: 目标="饮料瓶", 放置="黄色胶带" │
    │  2. 调用 grab_skill 编排完整流程:          │
    │     ├── 启动 ROS2 相机 (launch_orbbec.sh) │
    │     ├── 连接 NERO 臂 (arm_control.py)     │
    │     ├── 移动到观测姿态                      │
    │     ├── 采图 → 云端 VLM 检测               │
    │     ├── 深度3D定位 → 手眼变换              │
    │     ├── 执行抓取序列                        │
    │     └── 放置到目标位置                      │
    │  3. 反馈: "✅ 已完成"                      │
    └──────────────────────────────────────────┘
```

### nanobot 配置

`nanobot_config.json` 配置了 AI 模型和 API：

```json
{
  "providers": {
    "stepfun": {
      "apiKey": "<YOUR_API_KEY>"
    }
  },
  "modelPresets": {
    "primary": {
      "provider": "stepfun",
      "model": "step-3.7-flash",
      "maxTokens": 8192
    }
  }
}
```

### nanobot 安装

```bash
# 在 RDK X5 上
bash setup_nanobot_x5.sh
```

---

## 🎯 视觉抓取：完整流程

### 一次性标定（首次使用）

```bash
# 1. 设置观测姿态 (相机能看到桌面, 物体在视野内)
cd grab_skill
python3 set_base.py

# 2. 全关节手眼标定 (40姿态, 自动更新 transforms.py)
python3 calib_full.py

# 3. 示教中间位置 (抓取后的安全过渡位姿)
python3 teach_mid.py
#    点动: 1+ / 2- / 3++ / Enter=保存  q=退出
```

### 单次抓取+放置

```bash
ssh root@RDKX5
source /opt/ros/humble/setup.bash
cd /root/grab_skill

# 手动交互模式 (带 XYZ 微调 + Enter 确认)
python3 grab_main.py --object "饮料瓶" --place "黄色胶带" --enable-depth

# 自动模式 (跳过确认, 直接执行)
python3 grab_main.py --object "饮料瓶" --place "黄色胶带" --enable-depth --yes
```

### 完整抓取流程详解

```
Step 0 ─ 去观测姿态 + 张开夹爪
         arm.move_joints(observe)
         记录观测 flange 位姿

Step 1 ─ RGB-D 捕获
         Orbbec 相机: 时域滤波 N帧 → per-pixel median
         depth_registration:=true 对齐 RGB 和深度
         保存 /tmp/depth_alignment.png 诊断图

Step 2 ─ 云端 VLM 检测
         StepFun step-3.7-flash:
           输入: RGB图片 + "请找到: 饮料瓶"
           输出: 边界框 + 中心点坐标
         支持多种坐标格式解析 (pipe / JSON / NL / 兜底)

Step 2b─ 放置目标检测 (--place 时)
         同上, 检测放置参考物 (如 "黄色胶带")

Step 3 ─ 3D 定位 (眼在手上)
         p_cam  = 像素 + 深度 + 内参 → 相机系坐标
         p_base = T_base_flange × T_flange_cam × p_cam
         T_flange_cam: 手眼标定结果 (transforms.py CAM_MOUNT)
         T_base_flange: arm.get_flange_pose() 采图瞬间实时读

Step 4 ─ 抓取规划
         compute_grasp_pose():
           grasp_z  = 物体_z + TOOL_LEN + GRASP_OFFSET[2]
           approach_z = grasp_z + DESCEND
           应用 GRASP_OFFSET[0,1] (斜抓几何补偿)

Step 5 ─ 执行抓取
  5.1  到物体上方 (XY到位, z+10cm)   ← Cartesian move_to_pose
  5.2  交互 XYZ 微调 (可选)            ← x+/y-/z+/Enter确认
  5.3  Z下降至抓取高度                ← move_to_pose + 关节回退
  5.4  🤏 夹爪闭合 + hold线程         ← 持续夹紧防止松动
  5.5  去中间位置 (夹持物体)           ← move_joints(mid_pose)
                                          ↑ 你示教的关节角, 比观测姿态高

Step 6 ─ 放置或松爪
  6a 放置模式:
      到放置点上方(z=DROP_Z) → (微调) → 松爪投放 → 回中间位置
  6b 普通模式:
      已在中间位置 → Enter松爪
```

### 坐标变换链

```
相机光学系 (+X右 +Y下 +Z前)
    │  pixel_to_camera_3d(u, v, depth, K)
    ▼
相机系 p_cam [x, y, z]
    │  eye_in_hand_to_base(p_cam, flange_pose, cam_mount)
    ▼
基座系 p_base [x, y, z]  ← 机械臂基座坐标系 (+Y前 +Z上)
    │  compute_grasp_pose(p_base, rpy) + GRASP_OFFSET
    ▼
Flange 目标 [x, y, z, r, p, y]  ← 固件 IK 解算为关节角
```

### 偏置体系

| 常量 | 值 | 用途 |
|---|---|---|
| `GRASP_OFFSET` | [-0.06, 0.01, -0.06] | 斜抓几何补偿 (夹爪与光轴偏差) |
| `PLACE_OFFSET` | [-0.05, -0.03, 0.0] | 放置点偏置 |
| `GRIPPER_TOOL_LEN` | 0.13m | 夹爪尖端在 flange 下方距离 |
| `GRASP_DESCEND` | 0.10m | 预抓取→抓取下抓行程 |
| `DROP_Z` | 0.35m | 投放高度 |
| `HIGH_LIFT` | 0.12m | 中间位置抬升量 (在观测flange之上) |

### 关键文件说明

| 文件 | 职责 |
|---|---|
| `grab_main.py` | 主入口，编排完整抓取+放置流程 |
| `arm_control.py` | NERO 臂安全控制器 (碰撞保护0级, 关节限位, move_p/move_j/move_l) |
| `camera.py` | Orbbec ROS2 相机 (时域滤波 `capture_filtered`, RGB-D 对齐检查) |
| `detector.py` | StepFun VLM 检测 (base64 编码图片, 6种坐标格式解析) |
| `transforms.py` | 眼在手上变换 (CAM_MOUNT 标定结果, RPY 矩阵) |
| `teach_mid.py` | 中间位置示教 (使能状态关节点动, Enter保存) |
| `calib_full.py` | 全关节手眼标定 (40姿态, Tsai初值+非线性优化) |

## 🚗 底盘控制

Tracer 1.0 差速底盘，通过 candleLight USB-CAN 直控：

```bash
# 启动 ROS2 驱动
ros2 launch tracer_base tracer_base.launch.py port_name:=can2

# 简单运动测试
python3 tracer_test.py 0.05 0 4    # 前进: 速度0.05m/s, 4秒

# 键盘遥控 (WASD)
python3 tracer_keyboard.py
```

CAN 协议 (500kbps)：
- `0x111` — 运动控制 (线速度+角速度)
- `0x421` — 模式切换
- `0x441` — 清除急停

> ⚠️ 遥控器 SWB 必须拨到最下方 CAN 才通；H/L 接反收不到数据

---

## 🛏️ 盖被子机器人 (开发中)

`blanket_guardian/` — 监测踢被子并自动盖回：

```
摄像头拍照 → VLM检测踢被子 → Tracer靠近床边 → NERO拉被子 → Tracer后退
```

---

## 🛡️ 安全机制

- NERO 碰撞保护 0 级（最灵敏），关节限位开启
- 速度限制 15-20%
- `disable_arm.py` 手动下使能（必须人工操作）
- `safe_arm_skill/verify_safety.py` 安全验证
- 遥控器始终可接管

---

## 环境安装

### RDK X5 初始化

```bash
# 一键安装 ROS2 + pyAgxArm + MoveIt
bash setup_nero_x5.sh

# 安装 nanobot AI agent
bash setup_nanobot_x5.sh

# 部署抓取代码
scp -r grab_skill/* root@RDKX5:/root/grab_skill/
```

### 运行时依赖

```bash
# 每新开终端
source /opt/ros/humble/setup.bash

# 相机启动 (终端1, 保持运行)
bash launch_orbbec.sh
```

---

## License

MIT License. See [LICENSE](LICENSE).
