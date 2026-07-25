"""
盖被子机器人 - 配置 + 示教工具
运行这个脚本可以:
1. 测试 VLM 检测 (随便拍张照片)
2. 记录 NERO 关键位姿 (手动示教后保存)
3. 测试 VLM 检测 + 手动确认

用法:
  python3 teach_and_test.py test_vlm    # 测试VLM (给图片路径)
  python3 teach_and_test.py record_pose # 记录当前 NERO 位姿
  python3 teach_and_test.py test_full   # 完整模拟测试(不动机器人)
"""
import time
import json
import sys
import os
from pathlib import Path

# 加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from vlm_detector import BlanketDetector

# ============================================================
#  API 密钥
# ============================================================
API_KEY = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"

# 预设位姿文件
POSE_FILE = Path(__file__).parent / "nero_poses.json"

DEFAULT_POSES = {
    "home": [1.736, -0.073, -0.025, -0.031, 1.541, 0.013, 0.134],
    "observe": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "grab_blanket": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "pull_up": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}


def test_vlm(image_path: str):
    """测试 VLM 检测"""
    print(f"分析图片: {image_path}")
    detector = BlanketDetector(API_KEY)
    uncovered, desc = detector.is_uncovered(image_path)
    print(f"\n{'='*40}")
    print(f"踢被子: {'是 ❌' if uncovered else '否 ✅'}")
    print(f"详情: {desc}")


def record_pose(pose_name: str):
    """读取当前 NERO 关节角并保存"""
    try:
        # 通过 pyAgxArm 读取
        script = f"""
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO,firmeware_version=NeroFW.DEFAULT,
                            interface="socketcan",channel="can1")
arm=AgxArmFactory.create_arm(cfg)
arm.connect()
arm.enable()
time.sleep(0.5)
ja=arm.get_joint_angles()
if ja:
    print("JOINTS:"+str(list(ja.msg)))
arm.disable()
arm.disconnect()
"""
        import subprocess
        result = subprocess.run(["python3", "-c", script], capture_output=True, text=True, timeout=15)
        for line in result.stdout.split("\n"):
            if line.startswith("JOINTS:"):
                joints = eval(line.split("JOINTS:")[1])
                # 加载已有位姿
                if POSE_FILE.exists():
                    poses = json.loads(POSE_FILE.read_text())
                else:
                    poses = DEFAULT_POSES.copy()
                poses[pose_name] = [round(j, 4) for j in joints]
                POSE_FILE.write_text(json.dumps(poses, indent=2, ensure_ascii=False))
                print(f"✅ 位姿 '{pose_name}' 已保存: {[round(j, 4) for j in joints]}")
                return
        print("❌ 无法读取关节角, 检查 CAN 连接")
    except Exception as e:
        print(f"❌ 错误: {e}")


def test_blanket_scenario():
    """模拟测试: 用示例图片测试检测逻辑 (不动机器人)"""
    print("=" * 50)
    print("盖被子场景模拟测试")
    print("=" * 50)

    detector = BlanketDetector(API_KEY)

    # 你可以放几张测试图片在 test_images/ 目录下
    test_dir = Path(__file__).parent / "test_images"
    if not test_dir.exists():
        test_dir.mkdir()
        print(f"\n请把测试图片放到 {test_dir}/ 目录下")
        print("例如: covered_ok.jpg (盖好的), uncovered_bad.jpg (踢掉的)")
        return

    images = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
    if not images:
        print(f"没有找到测试图片在 {test_dir}/")
        return

    for img in sorted(images):
        print(f"\n--- {img.name} ---")
        uncovered, desc = detector.is_uncovered(str(img))

    print("\n" + "=" * 50)
    print("测试完成! 查看上面的检测结果判断准确率")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test_vlm":
        img = sys.argv[2] if len(sys.argv) > 2 else input("图片路径: ")
        test_vlm(img)

    elif cmd == "record_pose":
        name = sys.argv[2] if len(sys.argv) > 2 else input("位姿名称 (home/observe/grab_blanket/pull_up): ")
        record_pose(name)

    elif cmd == "test_full":
        test_blanket_scenario()

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
