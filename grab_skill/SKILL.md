# Cloud Grab Skill — 云端视觉抓取

基于云端 VLM + Orbbec 深度相机的物体检测与 NERO 机械臂自动抓取。

## 架构

```
相机(RGB+深度) → 云端StepFun VLM检测 → 深度图3D定位 → 机械臂抓取
     │                  │                    │              │
  Orbbec           物体在哪?            物体有多远?    移动到目标
 Gemini 335      返回边界框           像素+深度→xyz    (需IK模块)
```

## 文件结构

| 文件 | 功能 |
|---|---|
| `grab_main.py` | 主入口，编排完整流程 |
| `camera.py` | Orbbec ROS2 相机接口 |
| `detector.py` | StepFun 云端 VLM 物体检测 |
| `arm_control.py` | NERO 机械臂 + 夹爪安全控制 |
| `calibrate.py` | 手眼标定工具 |

## 依赖

### 硬件
- RDK X5 + NERO 机械臂 + Orbbec Gemini 335 / Dabai DC1
- CAN 总线连接 (can1 @ 1Mbps)

### 软件 (已在 RDK X5 上安装)
- ROS2 Humble + OrbbecSDK_ROS2 (已编译)
- pyAgxArm + python-can
- opencv-python, numpy

### 云端服务
- **StepFun step-3.7-flash** — 物体检测 (已配置 API Key)
  - 输入: RGB 图片 + 中文描述
  - 输出: 边界框 + 中心点

### 缺失模块 (待补充)
- **逆运动学 (IK) 求解器** — 将 3D 坐标转为 7 个关节角
  - 可选: PyKDL、trac_ik、或云端 IK 服务
- **完整手眼标定** — 需要 IK 模块配合

## 安装

```bash
# 1. 拷贝到 RDK X5
scp -r grab_skill/* root@RDKX5:/root/grab_skill/

# 2. 安装 Python 依赖
ssh root@RDKX5 "pip3 install opencv-contrib-python"

# 3. 验证
ssh root@RDKX5 "python3 -c 'from camera import StereoCamera; print(\"OK\")'"
```

## 使用方法

### 仅视觉检测 (不动机器人)
```bash
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
python3 grab_main.py --object "红色饮料瓶" --detect-only
```

### 完整抓取 (需 IK 模块)
```bash
python3 grab_main.py --object "饮料瓶"
```

### 手眼标定 (首次使用)
```bash
# 步骤 1: 贴 ArUco 标记到夹爪，归零后拍照
python3 calibrate.py --setup

# 步骤 2: 手动摆臂到 4-6 个姿态，逐个记录
python3 calibrate.py --collect

# 步骤 3: 求解变换矩阵
python3 calibrate.py --solve

# 步骤 4: 验证
python3 calibrate.py --test
```

## 云端模型清单

| # | 模型 | 用途 | 状态 |
|---|---|---|---|
| 1 | StepFun step-3.7-flash (多模态) | **物体检测**: 从图像中找到目标物体，返回边界框 | ✅ 已配置 |
| 2 | StepFun step-3.7-flash (多模态) | **场景理解**: 可选，识别场景中的多个物体及关系 | ✅ 可用同一API |
| 3 | **逆运动学求解器** (IK) | 将 3D 坐标 x,y,z + 姿态 → 7 个关节角 | ❌ 待补充 |
| 4 | **抓取姿态生成** (可选) | 根据物体形状生成最优抓取姿态 (roll/pitch/yaw) | ❌ 待补充 |

## 当前能力 vs 目标

| 能力 | 状态 |
|---|---|
| 相机采集 RGB+深度 | ✅ |
| 云端识别"视野中有没有饮料瓶" | ✅ |
| 估算物体的 3D 位置 (x,y,z) | ✅ |
| 机械臂归零/运动 | ✅ |
| 夹爪开合 | ✅ |
| 手眼标定(简化版) | ✅ |
| **从 3D 坐标到关节角的 IK 解算** | ❌ 核心缺失 |
| **自动运动到抓取点并夹取** | ❌ 取决于 IK |
