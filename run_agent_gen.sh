#!/bin/bash
export PATH=/root/nanobot_venv/bin:$PATH
/root/nanobot_venv/bin/nanobot agent \
  -w /root/nanobot_workspace \
  -c /root/.nanobot/config.json \
  -m "使用 safe-arm-executor 技能，生成让 NERO 第7关节动 0.03 弧度然后回原位的安全 Python 代码。只输出代码，不要解释。"
