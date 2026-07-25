<div align="center">

# Sleep Steward

**NERO 机械臂视觉抓取 + Tracer 移动底盘 CAN 控制** | NERO Arm Visual Grasping + Tracer Mobile Base CAN Control

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ROS2](https://img.shields.io/badge/ROS2-Humble-22314E?logo=ros)](https://docs.ros.org/en/humble/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-RDK%20X5-E60012?)](https://developer.horizon.ai/)

</div>

---

## 📖 项目简介 | Introduction

**中文**：基于 RDK X5 的 NERO 7-DOF 机械臂**眼在手上**全关节手眼标定、时域滤波深度对齐、云端 VLM 视觉检测、交互式 XYZ 微调抓取，以及 Tracer 1.0 移动底盘 CAN 总线控制。

**English**: Eye-in-hand full-joint hand-eye calibration, temporally filtered depth alignment, cloud-based VLM visual detection, interactive XYZ fine-tuned grasping for the NERO 7-DOF arm, and CAN bus control for the Tracer 1.0 mobile base — all on the RDK X5 platform.

---

## ✨ 功能特性 | Features

| 模块 | 功能 |
|---|---|
| 🎯 手眼标定 | 40 姿态全关节覆盖 (J1~J7)、Tsai 初值 + 多初值非线性优化、自动更新 transforms.py |
| 📸 深度对齐 | 5 帧 per-pixel median 时域滤波、`depth_registration:=true` RGB-D 对齐、对齐质量叠加图 |
| 🤖 视觉抓取 | VLM 检测 → 鲁棒深度采样 → 眼在手上变换 → 两段式到位 (XY上方+Z下降) → 交互 XYZ 微调 |
| 🚗 底盘控制 | Tracer CAN 协议直控 + 键盘遥控 (WASD) |
| 🔍 VLM 检测 | StepFun step-3.7-flash 云端多模态，支持中文自然语言坐标解析 |

---

## 🛠️ 技术栈 | Tech Stack

| 类别 | 技术 |
|---|---|
| **平台** | RDK X5 (Horizon Robotics, ARM Ubuntu 22.04) |
| **中间件** | ROS 2 Humble |
| **语言** | Python 3.10+ |
| **机械臂 SDK** | pyAgxArm (AgileX NERO, socketcan, CAN1@1Mbps) |
| **相机驱动** | OrbbecSDK ROS 2 v1.5.15 (DaBai DC1) |
| **数值优化** | SciPy (least_squares), Tsai-Lenz hand-eye |
| **计算机视觉** | OpenCV (ArUco DICT_4X4_50, PnP) |
| **AI 检测** | StepFun step-3.7-flash (云端 VLM) |

---

## 🔧 硬件 | Hardware

| 设备 | 接口 | 说明 |
|---|---|---|
| **RDK X5** | — | 主控板 |
| **NERO 机械臂** | CAN1 @1Mbps | 7-DOF, pyAgxArm 直连 |
| **Orbbec DaBai DC1** | USB 2.0 | 眼在手上 RGB-D |
| **Tracer 1.0** | CAN @500kbps | 松灵差速底盘, candleLight USB-CAN |
| **ArUco 标定板** | — | DICT_4X4_50 ID=0, 10cm |

---

## 📁 目录结构 | Project Structure

```
grab_skill/
├── calib_full.py            # 全关节手眼标定 (40姿态, 自动更新transforms.py)
├── calib_auto.py            # 自动标定 (18姿态)
├── verify_auto.py           # 独立随机姿态验证
├── set_base.py              # 观测基准姿态交互设置
├── grab_main.py             # 视觉抓取主入口
├── transforms.py            # 眼在手上坐标变换 (CAM_MOUNT)
├── arm_control.py           # NERO 臂安全控制器
├── camera.py                # Orbbec 相机接口 (时域滤波 + 深度对齐)
├── detector.py              # VLM 物体检测 (中文NL解析)
├── generate_marker.py       # ArUco 标记生成
├── parse_calib_result.py    # 标定结果解析
└── calibration/             # 标定数据 + 基座姿态
tracer_test.py               # 底盘运动测试
tracer_keyboard.py           # 底盘键盘遥控
```

---

## 🚀 快速开始 | Quick Start

### 环境准备

```bash
# RDK X5 上
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
```

### 1. 启动相机 (终端1, 保持运行)

```bash
ros2 launch orbbec_camera dabai.launch.py \
    camera_name:=camera enable_color:=true enable_depth:=true \
    enable_point_cloud:=false enable_ir:=false enable_ldp:=false \
    depth_registration:=true
```

### 2. 手眼标定

```bash
cd grab_skill
python3 set_base.py            # 设定观测姿态 (标记可见, J5远离限位)
python3 calib_full.py          # 全关节标定 (40姿态, 自动更新transforms.py)
```

### 3. 视觉抓取

```bash
cd grab_skill
python3 grab_main.py --object "士力架巧克力" --enable-depth

# 选项:
#   --object "目标物体"    检测目标 (中文)
#   --enable-depth         启用深度3D定位
#   --filter-frames 5      时域滤波帧数 (默认5)
#   --grasp-rpy "r,p,y"    手动指定抓取朝向
#   --dry-run              仅规划不执行
#   --yes                  跳过确认
```

### 抓取流程

1. 臂去观测姿态 → 采图 → VLM 检测
2. 深度定位 → 手眼变换 → 规划抓取位姿
3. **XY 到位**：臂到物体上方 (z+10cm)
4. **交互微调**：`x+0.01` / `y-0.005` / `z+0.02` 实时移动
5. **Z 下降**：确认后降到夹取高度
6. **夹取** → 关节回观测 → Enter 松爪

### 4. 底盘控制

```bash
python3 tracer_test.py 0.05 0 4    # 前进 20cm
python3 tracer_keyboard.py          # 键盘遥控
```

---

## 📐 关键技术 | Technical Details

### 坐标变换 (眼在手上)

```
p_base = T_base_flange · T_flange_cam · p_cam
```

- `p_cam`: 深度 + 内参 → 相机光学系
- `T_flange_cam`: 40 姿态标定 (transforms.py CAM_MOUNT)
- `T_base_flange`: `arm.get_flange_pose()` 实时读取

### NERO IK 约束

- pitch 接近 **±π/2 (≈1.57 rad)** 时 IK 奇异，代码自动将 pitch 压至 1.4
- 抓取朝向默认跟随观测姿态 flange rpy
- 下降优先 `move_p`，失败自动关节插值 (J2)

### 深度对齐

- `depth_registration:=true` 将 640×400 深度 warp 到 640×480 彩色
- `capture_filtered()` 采集 N 帧逐像素 median 滤波 (~50% 噪声降低)
- `/tmp/depth_alignment.png` RGB-D 叠加图用于诊断对齐质量

### VLM 检测

- StepFun step-3.7-flash 多模态模型
- 支持中文自然语言坐标解析 (格式 3b + 兜底格式 6)
- 自动过滤过大 bbox (疑似背景误检)

---

## ⚠️ 已知限制

- NERO 固件 IK pitch 接近 ±π/2 时被拒 (自动压至 1.4)
- DaBai DC1 视野窄 (~60°)，标定需 10cm 以上 ArUco 标记
- VLM 对黑色/低对比度物体可能误检
- Tracer 遥控器 SWB 影响 CAN 通信

---

## 📄 License

MIT License. See [LICENSE](LICENSE).
