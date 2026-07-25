#!/bin/bash
export PATH=/root/nanobot_venv/bin:$PATH
cd /root/nanobot_workspace

echo "=== 测试 agx-arm-codegen skill ==="
echo ""

timeout 60 nanobot agent \
  -w /root/nanobot_workspace \
  -c /root/.nanobot/config.json \
  -m "请使用 agx-arm-codegen 技能，生成让 NERO 7轴机械臂的第2关节转到 0.3 弧度的 pyAgxArm Python 代码。只输出代码。"
