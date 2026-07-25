"""
NERO 机械臂 + 夹爪安全控制器
所有运动都带安全检查：碰撞保护 0 级、关节限位、速度限制

用法:
    from arm_control import NeroArm
    arm = NeroArm()
    arm.connect()
    arm.go_home()
    arm.move_to_grasp_pose(x, y, z, roll, pitch, yaw)
    arm.gripper_close()
    arm.disconnect()
"""

import math
import time
import json
import sys
import numpy as np
from pathlib import Path
from typing import Optional, List

from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW


# ─── 配置 ───────────────────────────────────────────────────
HOME_FILE = Path("/root/nero_home_position.json")
CAN_CHANNEL = "can1"
SPEED_PERCENT = 20
GRIPPER_MAX_OPEN = 0.07   # 夹爪最大开口 (m)
GRIPPER_FORCE = 2.0       # 夹持力 (N)

# 出厂零位 (安全收纳姿态)
FACTORY_ZERO = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class NeroArm:
    """NERO 机械臂安全控制器"""

    def __init__(self):
        self._arm = None
        self._gripper = None
        self._connected = False
        self._enabled = False

    # ─── 连接 ────────────────────────────────────────────────

    def connect(self, speed_pct: int = 20):
        """连接并配置机械臂"""
        print("[Arm] 连接 NERO...")
        cfg = create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=NeroFW.V112,
            interface="socketcan",
            channel=CAN_CHANNEL,
        )
        self._arm = AgxArmFactory.create_arm(cfg)
        self._arm.connect()
        self._connected = True
        print(f"[Arm] CAN ({CAN_CHANNEL}) 连接成功")

        # 安全配置
        self._arm.set_speed_percent(speed_pct)
        self._arm.set_crash_protection_rating(joint_index=255, rating=0)
        self._arm.set_joint_limits_enabled(True)
        print(f"[Arm] 速度={speed_pct}% 碰撞保护=0级 关节限位=开启")

    def disconnect(self):
        """断开 CAN 连接 (⚠️ 不再自动下使能 —— 按要求, 下使能必须人工操作)。
        断开后臂保持当前使能状态; 如需下使能请手动运行 disable_arm.py。"""
        if self._arm and self._connected:
            self._arm.disconnect()
            self._connected = False
            print("[Arm] 已断开 (保持使能状态, 未下使能)")

    def _all_joints_enabled(self):
        """查 7 个关节是否都已使能 (driver_enable_status)"""
        try:
            for i in range(1, 8):
                d = self._arm.get_driver_states(i)
                if d is None or not d.msg.foc_status.driver_enable_status:
                    return False
            return True
        except Exception:
            return False

    def enable(self, timeout=3.0):
        """使能机械臂 (已使能则跳过, 不冲突)"""
        if not self._connected:
            raise RuntimeError("未连接，请先调用 connect()")
        if self._all_joints_enabled():
            self._enabled = True
            print("[Arm] 已处于使能状态, 跳过 enable")
            return
        print("[Arm] 使能中...")
        start = time.time()
        while not self._arm.enable():
            if time.time() - start > timeout:
                raise TimeoutError("使能超时")
            time.sleep(0.01)
        self._enabled = True
        print("[Arm] 已使能")

    def disable(self):
        """下使能"""
        if self._arm and self._enabled:
            self._arm.disable()
            self._enabled = False
            print("[Arm] 已下使能")

    # ─── 关节控制 ────────────────────────────────────────────

    def get_joint_angles(self) -> Optional[List[float]]:
        """读取当前关节角"""
        ja = self._arm.get_joint_angles()
        if ja:
            return list(ja.msg)
        return None

    def get_home_position(self) -> List[float]:
        """获取记录的零位"""
        if HOME_FILE.exists():
            return json.loads(HOME_FILE.read_text())
        print("[Arm] 未记录零位，使用出厂零位")
        return FACTORY_ZERO

    def go_home(self, speed_pct: int = 20):
        """归零"""
        target = self.get_home_position()
        current = self.get_joint_angles()
        if current is None:
            raise RuntimeError("无法读取关节角")

        max_delta = max(abs(target[i] - current[i]) for i in range(7))
        print(f"[Arm] 归零: 当前偏差 max={max_delta:.3f} rad, 目标={[round(t,3) for t in target]}")

        if max_delta > 2.0:
            raise RuntimeError(f"偏差 {max_delta:.2f} rad 过大，请手动摆近零位!")

        self._arm.set_speed_percent(speed_pct)
        self._arm.move_j(target)

        # 等待完成
        for _ in range(150):
            s = self._arm.get_arm_status()
            if s and s.msg.motion_status == 0:
                break
            time.sleep(0.2)

        # 验证
        final = self.get_joint_angles()
        if final:
            err = max(abs(final[i] - target[i]) for i in range(7))
            print(f"[Arm] 归零完成, 误差={err:.4f} rad")
        else:
            print("[Arm] 归零完成 (无法验证)")

    def move_joints(self, target: List[float], speed_pct: int = 20, timeout: float = 30.0):
        """关节空间运动（安全包装）。大位移(>2rad)自动分小步插值, 防关节巨跳。"""
        current = self.get_joint_angles()
        if current is None:
            raise RuntimeError("无法读取关节角")

        max_delta = max(abs(target[i] - current[i]) for i in range(7))
        if max_delta < 0.001:
            print("[Arm] 目标与当前位置相同，跳过运动")
            return

        self._arm.set_speed_percent(speed_pct)
        if max_delta <= 2.0:
            print(f"[Arm] 关节运动: delta_max={max_delta:.3f} rad, speed={speed_pct}%")
            self._arm.move_j(target)
            self._wait_motion_done(timeout)
            return

        # 大位移 (>2rad): 分步插值, 每步 ≤1rad, 安全过渡 (避免 move_p 后关节解远离当前)
        n = int(np.ceil(max_delta / 1.0))
        print(f"[Arm] 大位移 {max_delta:.2f}rad, 分 {n} 步过渡 (每步≤1rad, speed={speed_pct}%)")
        for s in range(1, n + 1):
            mid = [current[i] + (target[i] - current[i]) * s / n for i in range(7)]
            self._arm.move_j(mid)
            self._wait_motion_done(timeout)
            time.sleep(0.2)

    # ─── 笛卡尔运动 (pyAgxArm 内置 IK) ────────────────────────

    def get_tcp_pose(self) -> Optional[List[float]]:
        """获取当前 TCP 位姿 [x, y, z, roll, pitch, yaw]"""
        result = self._arm.get_tcp_pose()
        if result:
            return list(result.msg) if hasattr(result, 'msg') else list(result)
        return None

    def get_flange_pose(self) -> Optional[List[float]]:
        """flange(link7) 位姿 [x, y, z, roll, pitch, yaw] 基座系。
        ⚠️ 眼在手上手眼标定用的是 flange (不是 TCP), 坐标变换必须用这个,
        和 calib_auto.py / transforms.py 的约定一致。"""
        result = self._arm.get_flange_pose()
        if result:
            return list(result.msg) if hasattr(result, 'msg') else list(result)
        return None

    def _clamp_orientation(self, pose: List[float]) -> List[float]:
        """把 roll/pitch/yaw 归一化到 [-pi,pi) 并避开端点 ±pi
        (固件对恰好等于 ±pi 的姿态会 warning 并拒绝运动)"""
        if len(pose) >= 6:
            lim = math.pi - 0.01
            for i in range(3, 6):
                a = (pose[i] + math.pi) % (2 * math.pi) - math.pi
                pose[i] = max(-lim, min(lim, a))
        return pose

    def move_to_pose(
        self, pose: List[float], speed_pct: int = 15, timeout: float = 15.0,
        safe_z_first: bool = True,
    ):
        """
        笛卡尔空间运动到目标位姿 (pyAgxArm 内部求解 IK)

        Args:
            pose: [x, y, z, roll, pitch, yaw] 基座坐标系
            speed_pct: 速度百分比
            timeout: 超时 (秒)
            safe_z_first: True 则先上升到安全高度再平移
        """
        if len(pose) < 6:
            raise ValueError(f"pose 需要 6 个值 [x,y,z,roll,pitch,yaw], 当前 {len(pose)}")
        pose = self._clamp_orientation(list(pose[:6]))

        current = self.get_tcp_pose()
        if current is None:
            raise RuntimeError("无法获取当前 TCP 位姿")

        # 安全检查
        dist = np.linalg.norm(np.array(pose[:3]) - np.array(current[:3]))
        print(f"[Arm] 笛卡尔运动: {[round(v,4) for v in pose]}")
        print(f"[Arm]   → 距离={dist:.3f}m 速度={speed_pct}%")

        if safe_z_first and dist > 0.05:
            # 先升到安全高度 (比目标和当前位置都高)
            safe_z = max(current[2], pose[2]) + 0.08
            safe_pose = current.copy()
            safe_pose[2] = safe_z
            safe_pose = self._clamp_orientation(safe_pose)
            print(f"[Arm]   先升到安全高度 z={safe_z:.3f}m")
            self._arm.set_speed_percent(min(speed_pct + 10, 50))
            self._arm.move_l(safe_pose)
            self._wait_motion_done(timeout)
            time.sleep(0.3)

        # 运动到目标
        self._arm.set_speed_percent(speed_pct)
        self._arm.move_p(pose)
        self._wait_motion_done(timeout)

    def move_linear(self, pose: List[float], speed_pct: int = 10, timeout: float = 15.0):
        """直线运动到目标位姿"""
        pose = self._clamp_orientation(list(pose))
        self._arm.set_speed_percent(speed_pct)
        self._arm.move_l(pose)
        self._wait_motion_done(timeout)

    def _wait_motion_done(self, timeout: float):
        """等待运动完成"""
        for _ in range(int(timeout / 0.2)):
            s = self._arm.get_arm_status()
            if s and s.msg.motion_status == 0:
                return
            time.sleep(0.2)
        raise RuntimeError(f"运动超时 ({timeout}s) — 目标不可达或被固件拒绝")

    # ─── IK 查询 ────────────────────────────────────────────

    def solve_ik(self, pose: List[float]) -> Optional[List[float]]:
        """给定 TCP 位姿，返回关节角 (不运动)"""
        result = self._arm.get_ik_joint_angles()
        if result:
            return list(result.msg) if hasattr(result, 'msg') else list(result)
        return None

    # ─── 夹爪控制 ────────────────────────────────────────────

    def init_gripper(self):
        """初始化夹爪"""
        self._gripper = self._arm.init_effector(
            self._arm.OPTIONS.EFFECTOR.AGX_GRIPPER
        )
        self._arm.set_motion_mode(self._arm.OPTIONS.MOTION_MODE.P)
        print("[Gripper] 夹爪已初始化")

    def gripper_open(self, width_m: float = 0.07):
        """张开夹爪"""
        if self._gripper is None:
            self.init_gripper()
        print(f"[Gripper] 张开 {width_m:.3f}m")
        self._gripper.move_gripper_m(min(width_m, GRIPPER_MAX_OPEN))
        time.sleep(0.5)

    def gripper_close(self):
        """闭合夹爪"""
        if self._gripper is None:
            self.init_gripper()
        print("[Gripper] 闭合")
        # 用 move_gripper_m(0) 闭合 (和 gripper_open 的 move_gripper_m 同 API, 更可靠)
        self._gripper.move_gripper_m(0.0)
        time.sleep(0.8)

    def gripper_set(self, width_m: float):
        """设定夹爪开度"""
        if self._gripper is None:
            self.init_gripper()
        target = max(0.0, min(width_m, GRIPPER_MAX_OPEN))
        print(f"[Gripper] 开度 {target:.3f}m")
        self._gripper.move_gripper_m(target)
        time.sleep(0.3)

    # ─── 上下文管理器 ─────────────────────────────────────────

    def __enter__(self):
        self.connect()
        self.enable()
        return self

    def __exit__(self, *args):
        # ⚠️ 不自动下使能 —— 下使能必须人工操作 (运行 disable_arm.py)
        self.disconnect()


# ─── 快速测试 ────────────────────────────────────────────────
if __name__ == "__main__":
    import subprocess
    subprocess.run("ip link set can1 up type can bitrate 1000000", shell=True)
    time.sleep(0.5)

    with NeroArm() as arm:
        joints = arm.get_joint_angles()
        print(f"当前关节角: {[round(j, 4) for j in joints]}")
        home = arm.get_home_position()
        print(f"记录零位: {[round(j, 4) for j in home]}")
