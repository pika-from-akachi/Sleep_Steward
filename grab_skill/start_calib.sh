#!/bin/bash
# ===========================================================================
# NERO 手眼标定一键启动 (Eye-in-Hand)
#
# 前置准备:
#   1. 打印 ArUco 标记 (python3 /root/grab_skill/generate_marker.py)
#   2. 标记板平放在桌面上 (摄像头视野内)
#   3. 摄像头 (Orbbec Gemini 335) 已通过 USB 连接
#   4. 机械臂上电, CAN 已连接
#
# 用法:
#   bash start_calib.sh
#
# 需要 4 个终端分别运行:
#   T1: 摄像头驱动
#   T2: ArUco 标记检测
#   T3: 机械臂点动 + 位姿发布
#   T4: 手眼标定采集
# ===========================================================================

set -e

SCRIPT_DIR="/root/grab_skill"
ORBBEC_WS="/root/OrbbecSDK_ROS2"
HANDEYE_WS="/root/handeye_ws"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  NERO 手眼标定 (Eye-in-Hand)${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ─── 依赖检查 ──────────────────────────────────────────────
echo -e "${YELLOW}[1/4] 检查依赖...${NC}"

if [ ! -d "$ORBBEC_WS" ]; then
    echo -e "${RED}❌ OrbbecSDK_ROS2 未安装 ($ORBBEC_WS)${NC}"
    exit 1
fi

if [ ! -d "$HANDEYE_WS" ]; then
    echo -e "${RED}❌ handeye_ws 未安装 ($HANDEYE_WS)${NC}"
    exit 1
fi

echo "  ✅ OrbbecSDK_ROS2"
echo "  ✅ handeye_calibration_ros"
echo "  ✅ aruco_ros"

# ─── 激活 CAN ───────────────────────────────────────────────
echo -e "${YELLOW}[2/4] 激活 CAN 接口...${NC}"
sudo ip link set can1 up type can bitrate 1000000 2>/dev/null || true
sleep 0.5
if ip link show can1 2>/dev/null | grep -q "UP"; then
    echo "  ✅ can1 UP @ 1Mbps"
else
    echo -e "${RED}  ❌ can1 启动失败${NC}"
    exit 1
fi

# ─── 打印标定步骤 ────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  标定流程 (需要 4 个终端)${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}终端 1 — 启动相机:${NC}"
echo "  source /opt/ros/humble/setup.bash"
echo "  source $ORBBEC_WS/install/setup.bash"
echo "  ros2 launch orbbec_camera gemini_330_series.launch.py"
echo ""
echo -e "${YELLOW}终端 2 — ArUco 检测:${NC}"
echo "  source /opt/ros/humble/setup.bash"
echo "  python3 $SCRIPT_DIR/aruco_detect.py"
echo ""
echo -e "${YELLOW}终端 3 — 机械臂点动:${NC}"
echo "  source /opt/ros/humble/setup.bash"
echo "  python3 $SCRIPT_DIR/nero_calib_jog.py"
echo ""
echo -e "${YELLOW}终端 4 — 手眼标定:${NC}"
echo "  source /opt/ros/humble/setup.bash"
echo "  source $HANDEYE_WS/install/setup.bash"
echo "  ros2 run handeye_calibration_ros handeye_calibration --ros-args \\"
echo "    -p piper_topic:=/nero/end_pose \\"
echo "    -p marker_topic:=/aruco_single/pose \\"
echo "    -p mode:=eye_in_hand \\"
echo "    -p min_num:=10 \\"
echo "    -p result_save_path:=$SCRIPT_DIR/calibration"
echo ""
echo -e "${GREEN}操作步骤:${NC}"
echo "  1. 依次打开上述 4 个终端"
echo "  2. 在终端 3 中, 用关节号+/- 点动机械臂到不同姿态"
echo "     (确保 ArUco 标记始终在相机视野内)"
echo "  3. 每调好一个姿态, 在终端 4 按 Enter 采集"
echo "  4. 至少采集 10 组数据"
echo "  5. 采集完成后, 在终端 4 按 q 计算并保存结果"
echo "  6. 运行解析脚本: python3 $SCRIPT_DIR/parse_calib_result.py"
echo ""
echo -e "${YELLOW}点动命令 (终端 3):${NC}"
echo "  1+ / 1-    关节1 ±0.05rad"
echo "  3++ / 3--  关节3 ±0.2rad"
echo "  q          退出"
echo ""

# ─── 可选: 生成 ArUco 标记 ──────────────────────────────────
echo -e "${YELLOW}[3/4] ArUco 标记...${NC}"
MARKER_FILE="$SCRIPT_DIR/calibration/aruco_marker_id0.png"
if [ -f "$MARKER_FILE" ]; then
    echo "  ✅ 标记已存在: $MARKER_FILE"
else
    echo "  生成 ArUco 标记图像..."
    python3 -c "
import cv2, numpy as np
import os
os.makedirs('$SCRIPT_DIR/calibration', exist_ok=True)
dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
img = cv2.aruco.generateImageMarker(dic, 0, 500, borderBits=2)
cv2.imwrite('$MARKER_FILE', img)
print(f'  标记 (500px, ID=0, 5x5_50) → $MARKER_FILE')
# 生成带白边的版本 (方便打印)
h, w = img.shape
padded = np.ones((h+80, w+80), dtype=np.uint8) * 255
padded[40:40+h, 40:40+w] = img
cv2.imwrite('${SCRIPT_DIR}/calibration/aruco_marker_id0_print.png', padded)
print(f'  打印版 → ${SCRIPT_DIR}/calibration/aruco_marker_id0_print.png')
print(f'  请打印, 标记实际边长应裁剪为 0.10m')
"
    echo "  ✅ 标记生成完成"
fi

# ─── 清理僵尸进程 ────────────────────────────────────────────
echo -e "${YELLOW}[4/4] 清理旧进程...${NC}"
killall -9 ros2 2>/dev/null || true
killall -9 component_container 2>/dev/null || true
sleep 1
echo "  ✅ 完成"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  环境就绪! 请按上述步骤打开 4 个终端${NC}"
echo -e "${GREEN}============================================${NC}"
