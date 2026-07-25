"""
盖被子机器人 - 主控制程序
自动检测踢被子 → TRACER 导航 → NERO 盖被子

运行: python3 blanket_guardian.py
"""
import time
import json
import os
import subprocess
import signal
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread, Event

# 项目模块
from vlm_detector import BlanketDetector

# ============================================================
#  配置区 - 根据实际情况修改
# ============================================================

# StepFun API
STEPFUN_API_KEY = "42bzP32Fu4tI7lQlQPUU22jdfYiPvr2qSVVP7Mzmmfa5yjLfD4rwFjgrW5ST2Jl47"

# 摄像头设备 (Linux: /dev/video0, 可以是 USB 摄像头或 RDK X5 的 MIPI CSI)
CAMERA_DEVICE = "/dev/video0"
CAMERA_RESOLUTION = "640x480"

# 监测配置
CHECK_INTERVAL = 30          # 每 30 秒检查一次
MAX_CONSECUTIVE_ALERTS = 3   # 连续 3 次确认踢被子才行动
LOG_DIR = Path(__file__).parent / "logs"

# 机器人预设位姿 - 根据你床的位置手动示教后填入
# NERO 关节角 (7 个关节, 弧度)
NERO_HOME = [1.736, -0.073, -0.025, -0.031, 1.541, 0.013, 0.134]  # 收纳位
NERO_OBSERVE = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]   # 观察位姿 (需要示教!)
NERO_GRAB_BLANKET = [0.0] * 7                           # 抓被子位姿 (需要示教!)
NERO_PULL_UP = [0.0] * 7                                # 拉被子位姿 (需要示教!)

# TRACER 导航 - 简化版: 用线速度和角速度
TRACER_APPROACH_SPEED = 0.2     # 靠近速度 m/s
TRACER_APPROACH_TIME = 3.0      # 靠近时间 秒
TRACER_BACK_SPEED = -0.15       # 后退速度
TRACER_BACK_TIME = 3.0          # 后退时间

# ============================================================
#  CAN 接口配置
# ============================================================

# NERO 用 can1 (1Mbps), TRACER 用 can1 (但需要切换波特率!)
#  简化方案: 只用一个 USB-CAN，切换使用
#  生产方案: 两个 USB-CAN 分别接 can1(NERO@1M) 和 can2(TRACER@500k)
NERO_CAN = "can1"
NERO_BITRATE = 1000000
TRACER_CAN = "can1"          # 如果只有一个 CAN 模块，和 NERO 共用
TRACER_BITRATE = 500000


def setup_can(interface: str, bitrate: int):
    """设置 CAN 接口波特率"""
    subprocess.run(
        f"sudo ip link set {interface} down 2>/dev/null; "
        f"sudo ip link set {interface} up type can bitrate {bitrate}",
        shell=True, capture_output=True,
    )


class BlanketGuardian:
    """盖被子机器人主控"""

    def __init__(self):
        self.log_dir = LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 初始化 VLM 检测器
        print("[INIT] 初始化 VLM 检测器...")
        self.detector = BlanketDetector(STEPFUN_API_KEY)

        # 状态
        self.uncovered_count = 0
        self.covered_count = 0
        self.is_mission_active = False
        self.stop_event = Event()

        # 日志
        self.event_log = []

    def capture_image(self) -> str:
        """用摄像头拍照, 返回图片路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(self.log_dir / f"capture_{timestamp}.jpg")
        cmd = (
            f"ffmpeg -f v4l2 -video_size {CAMERA_RESOLUTION} -i {CAMERA_DEVICE} "
            f"-vframes 1 -y {path} -loglevel quiet"
        )
        subprocess.run(cmd, shell=True, capture_output=True)
        return path if os.path.exists(path) else None

    def move_tracer(self, speed: float, angular: float = 0.0, duration: float = 1.0):
        """
        控制 TRACER 底盘运动
        通过 ROS2 topic 直接发布 /cmd_vel
        """
        cmd = (
            f"source /opt/ros/humble/setup.bash && "
            f"source /root/tracer_ws/install/setup.bash && "
            f"ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "
            f"\"{{linear: {{x: {speed}}}, angular: {{z: {angular}}}}}\""
        )
        # 每秒发一次, 持续 duration 秒
        start = time.time()
        while time.time() - start < duration:
            subprocess.run(cmd, shell=True, capture_output=True)
            time.sleep(1.0)
        # 停止
        stop_cmd = cmd.replace(f"x: {speed}", "x: 0.0").replace(f"z: {angular}", "z: 0.0")
        subprocess.run(stop_cmd, shell=True, capture_output=True)

    def move_nero_to(self, target_joints: list, speed_pct: int = 20):
        """控制 NERO 机械臂运动到目标关节角"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        # 通过子进程调用 pyAgxArm
        script = f"""
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.DEFAULT,
                            interface="socketcan", channel="{NERO_CAN}")
arm = AgxArmFactory.create_arm(cfg)
arm.connect()
arm.set_speed_percent({speed_pct})
arm.set_crash_protection_rating(joint_index=255, rating=2)
while not arm.enable():
    time.sleep(0.01)
arm.move_j({target_joints})
# 等待完成
for _ in range(50):
    status = arm.get_arm_status()
    if status and status.msg.motion_status == 0:
        break
    time.sleep(0.2)
arm.disable()
arm.disconnect()
print("NERO_MOVE_DONE")
"""
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=30,
        )
        return "NERO_MOVE_DONE" in result.stdout

    def cover_blanket_routine(self):
        """
        盖被子序列:
        1. NERO 到观察位 → 确认被子位置
        2. TRACER 靠近床边
        3. NERO 抓被子边缘 → 拉上来
        4. TRACER 后退 → NERO 回原位
        """
        print("\n" + "=" * 50)
        print("[MISSION] 执行盖被子任务!")
        print("=" * 50)
        self.is_mission_active = True

        # Step 1: NERO 展开到观察位
        print("[STEP 1] NERO 展开到观察位...")
        self.move_nero_to(NERO_OBSERVE, speed_pct=20)
        time.sleep(1)

        # Step 2: TRACER 靠近
        print("[STEP 2] TRACER 靠近床边...")
        setup_can(TRACER_CAN, TRACER_BITRATE)
        self.move_tracer(TRACER_APPROACH_SPEED, 0, TRACER_APPROACH_TIME)
        time.sleep(0.5)

        # Step 3: NERO 抓被子并上拉
        print("[STEP 3] NERO 抓被子...")
        setup_can(NERO_CAN, NERO_BITRATE)
        self.move_nero_to(NERO_GRAB_BLANKET, speed_pct=15)
        time.sleep(0.5)
        # 夹爪闭合抓住被子
        self._gripper_close()
        time.sleep(0.5)
        # 拉被子
        print("[STEP 3b] NERO 拉被子...")
        self.move_nero_to(NERO_PULL_UP, speed_pct=15)
        time.sleep(1)
        # 夹爪松开
        self._gripper_open()
        time.sleep(0.3)

        # Step 4: TRACER 后退
        print("[STEP 4] TRACER 后退...")
        setup_can(TRACER_CAN, TRACER_BITRATE)
        self.move_tracer(TRACER_BACK_SPEED, 0, TRACER_BACK_TIME)

        # Step 5: NERO 回原位
        print("[STEP 5] NERO 回收...")
        setup_can(NERO_CAN, NERO_BITRATE)
        self.move_nero_to(NERO_HOME, speed_pct=30)

        self.is_mission_active = False
        self.uncovered_count = 0
        print("[MISSION] 盖被子任务完成!")

    def _gripper_close(self):
        """夹爪闭合"""
        script = f"""
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO,firmeware_version=NeroFW.DEFAULT,
                            interface="socketcan",channel="{NERO_CAN}")
arm=AgxArmFactory.create_arm(cfg);arm.connect()
g=arm.init_effector(arm.OPTIONS.EFFECTOR.AGX_GRIPPER)
arm.set_motion_mode(arm.OPTIONS.MOTION_MODE.P)
g.move_gripper_deg(0)
time.sleep(0.5);arm.disconnect()
"""
        subprocess.run(["python3", "-c", script], capture_output=True, timeout=10)

    def _gripper_open(self):
        """夹爪张开"""
        script = f"""
import time
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
cfg = create_agx_arm_config(robot=ArmModel.NERO,firmeware_version=NeroFW.DEFAULT,
                            interface="socketcan",channel="{NERO_CAN}")
arm=AgxArmFactory.create_arm(cfg);arm.connect()
g=arm.init_effector(arm.OPTIONS.EFFECTOR.AGX_GRIPPER)
arm.set_motion_mode(arm.OPTIONS.MOTION_MODE.P)
g.move_gripper_m(0.07)
time.sleep(0.5);arm.disconnect()
"""
        subprocess.run(["python3", "-c", script], capture_output=True, timeout=10)

    def log_event(self, event_type: str, details: str):
        """记录事件"""
        entry = {
            "time": datetime.now().isoformat(),
            "type": event_type,
            "details": details,
        }
        self.event_log.append(entry)
        log_file = self.log_dir / f"guardian_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def run(self):
        """主循环"""
        print("=" * 50)
        print("  🤖 盖被子机器人启动!")
        print(f"  检测间隔: {CHECK_INTERVAL}s")
        print(f"  确认次数: {MAX_CONSECUTIVE_ALERTS}")
        print("  Ctrl+C 停止")
        print("=" * 50)

        # 初始化: 设置 NERO CAN
        setup_can(NERO_CAN, NERO_BITRATE)

        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)

        while not self.stop_event.is_set():
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始检测...")

                # 1. 拍照
                img_path = self.capture_image()
                if img_path is None:
                    print("[WARN] 拍照失败, 跳过")
                    time.sleep(CHECK_INTERVAL)
                    continue

                # 2. VLM 分析
                is_uncovered, description = self.detector.is_uncovered(img_path)

                # 3. 决策
                if is_uncovered:
                    self.uncovered_count += 1
                    self.covered_count = 0
                    print(f"[ALERT] 可能踢被子! ({self.uncovered_count}/{MAX_CONSECUTIVE_ALERTS})")
                    self.log_event("uncovered", description)

                    if self.uncovered_count >= MAX_CONSECUTIVE_ALERTS:
                        self.cover_blanket_routine()
                else:
                    self.covered_count += 1
                    self.uncovered_count = max(0, self.uncovered_count - 1)
                    if self.covered_count % 10 == 0:
                        print(f"[OK] 一切正常 (连续 {self.covered_count} 次确认)")

                # 4. 等待下一次
                time.sleep(CHECK_INTERVAL)

            except Exception as e:
                print(f"[ERROR] {e}")
                self.log_event("error", str(e))
                time.sleep(CHECK_INTERVAL)

    def _handle_sigint(self, signum, frame):
        print("\n[STOP] 收到停止信号, 安全退出...")
        self.stop_event.set()


# ============================================================
#  主入口
# ============================================================

if __name__ == "__main__":
    guardian = BlanketGuardian()
    guardian.run()
