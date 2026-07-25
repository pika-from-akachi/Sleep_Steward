#!/bin/bash
# 盖被子机器人 - 一键安装脚本
# 在 RDK X5 上运行: bash install_blanket_guardian.sh

set -e
echo "===== 盖被子机器人 环境安装 ====="

# 1. 系统依赖
echo "[1/4] 安装系统依赖..."
apt install -y ffmpeg python3-pip python3-opencv 2>&1 | tail -3

# 2. Python 依赖
echo "[2/4] 安装 Python 依赖..."
pip3 install requests 2>&1 | tail -1

# 3. 确认摄像头
echo "[3/4] 检查摄像头..."
if [ -e /dev/video0 ]; then
    echo "  ✅ /dev/video0 可用"
elif [ -e /dev/video1 ]; then
    echo "  ⚠️ 发现 /dev/video1, 请修改 blanket_guardian.py 中的 CAMERA_DEVICE"
else
    echo "  ❌ 无摄像头设备! 请插入 USB 摄像头或检查 CSI 连接"
    ls /dev/video* 2>/dev/null || echo "  (无 video 设备)"
fi

# 4. 创建工作目录
echo "[4/4] 创建目录..."
mkdir -p /root/blanket_guardian/logs
mkdir -p /root/blanket_guardian/test_images

echo ""
echo "===== 安装完成 ====="
echo ""
echo "使用方法:"
echo "  cd /root/blanket_guardian"
echo "  python3 teach_and_test.py test_vlm <图片路径>   # 测试 VLM"
echo "  python3 blanket_guardian.py                      # 启动主程序"
