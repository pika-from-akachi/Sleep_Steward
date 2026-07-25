"""移动到已保存的观测姿态。⚠️ 若离当前位姿 >2rad 会被拒(用 step_home 摆近或分步)。"""
import json
from pathlib import Path
from arm_control import NeroArm

OBS = Path("/root/grab_skill/observation_pose.json")
if not OBS.exists():
    print("没有 observation_pose.json, 先 python3 jog_to_observe.py 存一个"); raise SystemExit(1)
target = json.loads(OBS.read_text())

with NeroArm() as arm:
    print(f"目标观测姿态: {[round(t,3) for t in target]}")
    arm.move_joints(target, speed_pct=12)   # 内含 2rad 安全检查
print("✅ 已到观测姿态 (保持使能)")
