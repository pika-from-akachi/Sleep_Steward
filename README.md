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

**中文**：本项目实现了基于 RDK X5 的 NERO 7-DOF 机械臂眼在手上手眼标定、云端 VLM 视觉抓取，以及 Tracer 1.0 移动底盘的 CAN 总线控制。包含全自动标定工具链、端到端抓取流程和底盘键盘遥控。

**English**: This project implements eye-in-hand calibration, cloud-based VLM visual grasping for the NERO 7-DOF robotic arm, and CAN bus control for the Tracer 1.0 mobile base on the RDK X5 platform. Includes a fully automated calibration toolchain, end-to-end grasping pipeline, and chassis keyboard teleoperation.

---

## ✨ 功能特性 | Features

| 模块 | 功能 | Module | Feature |
|---|---|---|---|
| 🎯 手眼标定 | 全自动采集+Tsai+非线性优化 | 🎯 Hand-Eye Calibration | Auto-collect + Tsai + Nonlinear optimization |
| 🤖 视觉抓取 | VLM检测→深度定位→手眼变换→笛卡尔抓取 | 🤖 Visual Grasping | VLM detect → depth localize → hand-eye transform → Cartesian grasp |
| 🚗 底盘控制 | Tracer CAN 协议直控+键盘遥控 | 🚗 Base Control | Tracer CAN protocol + keyboard teleop |
| 📊 独立验证 | 随机姿态重投影误差评估 | 📊 Validation | Random-pose reprojection evaluation |

---

## 🛠️ 技术栈 | Tech Stack

| 类别 | 技术 |
|---|---|
| **平台** | RDK X5 (Horizon Robotics, ARM Ubuntu 22.04) |
| **中间件** | ROS 2 Humble |
| **语言** | Python 3.10+ |
| **机械臂 SDK** | pyAgxArm (AgileX NERO, socketcan) |
| **相机驱动** | OrbbecSDK ROS 2 (DaBai DC1) |
| **CAN 通信** | python-can + socketcan + gs_usb (candleLight) |
| **计算机视觉** | OpenCV 5.x (ArUco 检测, PnP) |
| **数值优化** | SciPy (least_squares, Tsai-Lenz hand-eye) |
| **AI 检测** | StepFun step-3.7-flash (云端 VLM 多模态检测) |

---

## 🔧 硬件清单 | Hardware

| 设备 | 接口 | 说明 |
|---|---|---|
| **RDK X5** | — | 主控板，Ubuntu 22.04 + ROS2 Humble |
| **NERO 机械臂** | CAN1 @1Mbps | 松灵 7-DOF，pyAgxArm 直连（不使用 MoveIt） |
| **Orbbec DaBai DC1** | USB 2.0 | 眼在手上 RGB-D 相机，装在 flange/link7 |
| **Tracer 1.0** | CAN @500kbps | 松灵差速移动底盘，candleLight USB-CAN |
| **ArUco 标定板** | — | DICT_5X5_50 ID0，边长 15cm |

---

## 📁 目录结构 | Project Structure

```
Sleep_Steward/
├── grab_skill/              # 手眼标定 + 视觉抓取 (主工程)
│   ├── calib_auto.py        # 全自动标定 (Tsai + 非线性优化)
│   ├── verify_auto.py       # 独立随机姿态验证
│   ├── grab_main.py         # 视觉抓取主入口
│   ├── transforms.py        # 眼在手上坐标变换 (CAM_MOUNT)
│   ├── arm_control.py       # NERO 臂安全控制
│   ├── camera.py            # Orbbec 相机接口
│   ├── detector.py          # VLM 物体检测
│   ├── set_base.py          # 观测基准姿态设置
│   ├── generate_marker.py   # ArUco 标记生成
│   └── parse_calib_result.py# 标定结果解析
├── tracer_test.py           # Tracer 底盘运动测试
├── tracer_keyboard.py       # 底盘键盘遥控 (WASD)
├── README.md
└── LICENSE
```

---

## 🚀 快速开始 | Quick Start

### 环境准备 | Prerequisites

```bash
# RDK X5 上
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash

pip3 install python-can opencv-contrib-python scipy numpy
```

### 1. 手眼标定 | Hand-Eye Calibration

```bash
cd grab_skill
python3 set_base.py            # 设置观测基准姿态
python3 calib_auto.py          # 全自动标定 (18姿态 + 非线性优化)
python3 verify_auto.py         # 独立验证 (σ < 1.5cm)
python3 parse_calib_result.py  # 写入 transforms.py
```

### 2. 视觉抓取 | Visual Grasping

```bash
cd grab_skill
# 相机节点需在另一终端运行
python3 grab_main.py --object "带白条的黑色盒子" --enable-depth
```

### 3. 底盘控制 | Tracer Base Control

```bash
# 底盘运动测试
python3 tracer_test.py 0.05 0 4    # 前进 20cm

# 键盘遥控 (WASD / 方向键)
python3 tracer_keyboard.py
```

---

## 📐 关键技术细节 | Technical Details

### 坐标变换链 | Coordinate Transform Chain

```
p_base = T_base_flange · T_flange_cam · p_cam
```

- `p_cam`: 物体在相机光学系的坐标（深度+内参）
- `T_flange_cam`: 手眼标定结果（transforms.py 的 `CAM_MOUNT`）
- `T_base_flange`: 实时读取 `arm.get_flange_pose()`

### NERO 固件 IK 约束 | Firmware IK Constraints

- 固件对 pitch 接近 ±π/2 的位姿返回 `REACH_TARGET_POS_FAILED`
- 抓取朝向 `GRASP_RPY=[1.094, 1.0, 1.402]`（pitch=1.0，斜 ~57°）
- `move_p` 大位移后关节解常远离当前 → `move_joints` 自动分步插值

### Tracer CAN 协议 | CAN Protocol

| 帧 ID | 方向 | 说明 |
|---|---|---|
| `0x111` | host→base | 运动控制 (线速度 mm/s, 角速度 0.001rad/s, **大端**) |
| `0x421` | host→base | 切换 CAN 指令模式 `[0x01]` |
| `0x441` | host→base | 清除急停/错误 `[0x00]` |
| `0x211` | base→host | 系统状态 (20ms 周期) |
| `0x221` | base→host | 运动反馈 (20ms) |
| `0x311` | base→host | 里程计 (500ms) |

> ⚠️ 报文格式为 **MOTOROLA 大端**；控制周期 ≤500ms 否则超时停。

---

## ⚠️ 已知限制 | Known Limitations

- NERO 固件 IK 挑剔朝向（pitch 接近 ±π/2 被拒）
- DaBai DC1 RGB(640×480) 与深度(640×400)不对齐 → z 方向噪声 ±8cm
- VLM 对黑色物体易误检（夹爪/地面），需加白条标记区分
- Tracer 遥控器 SWB 位置影响 CAN 通信（实测最底位，因固件版本而异）

---

## 📄 开源协议 | License

本项目采用 [MIT License](LICENSE) 开源协议。

This project is licensed under the [MIT License](LICENSE).
