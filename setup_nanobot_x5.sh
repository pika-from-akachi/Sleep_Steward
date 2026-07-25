#!/bin/bash
set -e

echo "=== 1/4 安装 Python 3.11 ==="
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip 2>&1 | tail -3

echo ""
echo "=== 2/4 创建虚拟环境 ==="
python3.11 -m venv /root/nanobot_venv
source /root/nanobot_venv/bin/activate
pip install --upgrade pip -q

echo ""
echo "=== 3/4 安装 nanobot ==="
pip install nanobot-ai 2>&1 | tail -3

echo ""
echo "=== 4/4 克隆 OpenClawPi ==="
cd /root
[ -d OpenClawPi ] || git clone https://github.com/vanstrong12138/OpenClawPi.git 2>&1 | tail -1

echo ""
echo "=== Skills 列表 ==="
ls /root/OpenClawPi/skills/ 2>/dev/null

echo ""
echo "=== 完成 ==="
/root/nanobot_venv/bin/python3 --version
