# ring_sound_SDK

NERO 7-DOF 机械臂视觉抓取 + Tracer 移动底盘 CAN 控制，运行在 RDK X5 上。

## 硬件

| 设备 | 说明 |
|---|---|
| RDK X5 | 主控（地平线，Ubuntu 22.04 + ROS2 Humble），IP 192.168.128.10 |
| NERO 机械臂 | 松灵 7-DOF，pyAgxArm 直连（CAN1 @1Mbps），不用 MoveIt |
| Orbbec DaBai DC1 | 眼在手上相机（装 flange/link7），USB2，深度需 `enable_ldp:=false` |
| Tracer 1.0 | 移动底盘，candleLight USB-CAN（can0 @500kbps） |

## 功能模块

### 1. 手眼标定（眼在手上）`grab_skill/`

相机装在 flange（link7），标定 `T_flange_cam`（相机相对 flange 的变换）。

| 脚本 | 用途 |
|---|---|
| `set_base.py` | 设观测基准姿态（点动+实时标记反馈） |
| `calib_auto.py` | **全自动标定**（18姿态采集 + Tsai初值 + scipy非线性优化 + 多初值+物理bounds） |
| `verify_auto.py` | 独立随机姿态验证（σx/σy/σz） |
| `parse_calib_result.py` | 标定结果 → transforms.py 的 CAM_MOUNT |
| `generate_marker.py` | 生成 ArUco 标记（15cm，DICT_5X5_50 ID0） |

**标定结果**：`transforms.py` 的 `CAM_MOUNT`（σ<1.5cm）。

**关键经验（深度病态）**：眼在手上窄视野下，标记距离变化必须 >18cm，否则光轴方向欠定（σy 爆 40cm）。三件套：①15cm 标记 ②基准拉远 0.50~0.55m ③姿态集 J2/J3 距离扫描为主。

### 2. 视觉抓取 `grab_skill/`

| 脚本 | 用途 |
|---|---|
| `grab_main.py` | **主入口**：观测姿态 → RGB-D → VLM检测 → 3D定位 → 手眼变换 → 抓取 |
| `camera.py` | Orbbec ROS2 相机接口 |
| `detector.py` | StepFun 云端 VLM 物体检测 |
| `arm_control.py` | NERO 臂安全控制（pyAgxArm，get_flange_pose） |
| `transforms.py` | 眼在手上坐标变换 `p_base = T_base_flange · T_flange_cam · p_cam` |

**流程**：观测姿态 → 采图+读flange位姿 → VLM检测物体 → 像素+深度→相机系→基座系 → approach（高空对准→竖直下降）→ 微调 → 夹取 → 回观测松开。

**关键参数**（grab_main.py）：
- `GRASP_RPY=[1.094, 1.0, 1.402]`：固件 IK 接受的朝向（pitch=1.0，垂直朝下 pitch=π/2 被拒）
- `GRASP_OFFSET=[0,-0.03,-0.12]`：斜抓几何补偿（实测微调）
- 高空微调 xy（安全）+ Enter 竖直下降

**已知限制**：
- NERO 固件 IK 挑剔朝向（pitch 接近 ±π/2 → REACH_TARGET_POS_FAILED）
- DaBai RGB(640×480)/深度(640×400)不对齐 → z 方向噪声 ±8cm
- VLM bbox 中心噪声 ±4cm（黑色物体易误检夹爪/地面，加白条标记区分）

### 3. Tracer 底盘 CAN 控制

| 脚本 | 用途 |
|---|---|
| `tracer_test.py` | 底盘测试（自动检测接口 + 清急停 + 切模式 + 前进/转弯） |
| `tracer_keyboard.py` | **键盘遥控**（WASD/方向键，速度限制 v≤0.3m/s w≤0.5rad/s） |

**CAN 协议**（手册 V2.0.3，CAN2.0B 500K，**MOTOROLA 大端**）：
- `0x111` 运动控制：byte0-1 线速度(int16 **mm/s** ±1800, 大端), byte2-3 角速度(int16 **0.001rad/s** ±1000), 无CRC
- `0x421 [0x01]` 切 CAN 指令模式（默认待机，必须先发）
- `0x441 [0x00]` 清急停/错误
- 反馈：0x211 系统状态(20ms), 0x221 运动反馈, 0x311 里程计

**关键**：
- 遥控器 **SWB 拨最底** CAN 才通（手册写最上方，实测最底；固件差异）
- CAN_H/L 接反收不到（终端电阻 54Ω 正常也收不到）
- 板子重启要 `modprobe gs_usb`
- 控制周期 ≤500ms（否则超时停）

## 环境依赖

```bash
# RDK X5 (板子)
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash   # 相机
source /root/handeye_ws/install/setup.bash         # (可选) 官方手眼标定包

pip3 install python-can opencv-contrib-python scipy numpy
# pyAgxArm (机械臂)
```

## 快速开始

```bash
# 1. 手眼标定 (首次)
python3 grab_skill/set_base.py           # 设基准姿态
python3 grab_skill/calib_auto.py         # 全自动标定
python3 grab_skill/verify_auto.py        # 验证
python3 grab_skill/parse_calib_result.py # 写入 transforms.py

# 2. 视觉抓取
python3 grab_skill/grab_main.py --object "带白条的黑色盒子" --enable-depth

# 3. Tracer 底盘
python3 tracer_test.py 0.05 0 4          # 前进20cm
python3 tracer_keyboard.py               # 键盘遥控
```

## 目录结构

```
ring_sound_SDK/
├── grab_skill/          # 手眼标定 + 视觉抓取 (主工程)
│   ├── calib_auto.py    # 全自动标定
│   ├── verify_auto.py   # 独立验证
│   ├── grab_main.py     # 视觉抓取主入口
│   ├── transforms.py    # 坐标变换 (CAM_MOUNT)
│   ├── arm_control.py   # NERO 臂控制
│   ├── camera.py        # Orbbec 相机
│   ├── detector.py      # VLM 检测
│   └── ...
├── tracer_test.py       # Tracer 底盘测试
├── tracer_keyboard.py   # 底盘键盘遥控
└── calibration/         # 标定数据 (base_pose.json 等)
```
