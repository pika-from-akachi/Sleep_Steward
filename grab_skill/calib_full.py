#!/usr/bin/env python3
"""手眼标定 (eye-in-hand) — 全关节多样性姿态 + 自动采集 + 多初值非线性优化

核心改进:
  1. 25 个姿态覆盖全部 7 关节 (特别是之前被忽略的 J4 肘滚转 和 J7 腕滚转)
  2. 大幅扰动 (J2±0.35 rad, J3±0.30 rad) 破深度病态
  3. 标记不可见时自动缩小扰动重试 (progressive fallback)
  4. Tsai 初值 → 多初值非线性最小二乘 (物理约束: 相机距flange<0.30m)
  5. 自动独立验证 (12 个随机姿态, 统计 σx/σy/σz)
  6. 自动更新 transforms.py 的 CAM_MOUNT

用法:
    # 前置: 确保 ArUco 标记 (DICT_4X4_50 ID=0, 边长=0.15m) 放在桌面上
    # 确保相机 ROS2 驱动已在另一个终端运行
    python3 calib_full.py

依赖:
    pip3 install scipy opencv-contrib-python
    pyAgxArm (RDK X5 自带)
    ROS2 + OrbbecSDK_ROS2 (相机驱动)
"""

import subprocess, time, sys, glob, os, json
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24 (必须在 import tf_transformations 之前!)
cv2_available = True
try:
    import cv2
except ImportError:
    cv2_available = False
    print("⚠️ opencv-python 未安装, 请运行: pip3 install opencv-contrib-python")
    sys.exit(1)

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo

try:
    from scipy.spatial.transform import Rotation
    from scipy.optimize import least_squares
except ImportError:
    print("⚠️ scipy 未安装, 请运行: pip3 install scipy")
    sys.exit(1)

import tf_transformations as tt
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

# ─── 配置 ───────────────────────────────────────────────────────
CALIB_DIR = "/root/grab_skill/calibration"
TRANSFORMS_FILE = "/root/grab_skill/transforms.py"
MARKER_ID, MARKER_SIZE = 0, 0.15   # ArUco 标记边长 (米)

# ─── 加载基准姿态 ───────────────────────────────────────────────
_BASE_FILE = f"{CALIB_DIR}/base_pose.json"
_DEFAULT_BASE = [1.51, -0.20, -2.757, 1.67, 2.757, 0.363, -0.773]

def load_base():
    if os.path.exists(_BASE_FILE):
        d = json.loads(open(_BASE_FILE).read())
        return list(d["joints"])
    print(f"⚠️ 无 {_BASE_FILE}, 用默认 BASE")
    return list(_DEFAULT_BASE)

BASE = load_base()

# ─── 姿态生成 ───────────────────────────────────────────────────
# 索引: 0=J1底座旋转  1=J2肩俯仰  2=J3肘俯仰  3=J4肘滚转
#       4=J5腕俯仰    5=J6腕偏航  6=J7腕滚转
#
# 关键: 之前 J4/J7 几乎没用到 → 这里单独加旋转组
#       J2/J3 大幅扰动破深度病态
#       所有偏移单位: rad

def pose(offsets):
    """offsets: {关节索引: 偏移量(rad)} → 完整 7 关节姿态"""
    p = list(BASE)
    for jidx, delta in offsets.items():
        p[jidx] += delta
    return p

# 40 个姿态, 分 4 组: 激进扰动 + fallback 保证采集
POSES = [
    # ── Group A: 纯平移 (J1/J2/J3) — 破深度病态, 12 姿态 ──
    ("平移: 肩上抬+0.60",   pose({1: 0.60})),
    ("平移: 肩下压-0.55",   pose({1: -0.55})),
    ("平移: 肘伸展+0.55",   pose({2: 0.55})),
    ("平移: 肘回缩-0.55",   pose({2: -0.55})),
    ("平移: 底座右转+0.50", pose({0: 0.50})),
    ("平移: 底座左转-0.50", pose({0: -0.50})),
    ("平移: 肩+0.35 肘+0.35",   pose({1: 0.35, 2: 0.35})),
    ("平移: 肩-0.35 肘-0.35",   pose({1: -0.35, 2: -0.35})),
    ("平移: 底座+0.30 肩+0.30", pose({0: 0.30, 1: 0.30})),
    ("平移: 底座-0.30 肩-0.30", pose({0: -0.30, 1: -0.30})),
    ("平移: 底座+0.25 肘+0.25", pose({0: 0.25, 2: 0.25})),
    ("平移: 底座-0.25 肘-0.25", pose({0: -0.25, 2: -0.25})),

    # ── Group B: 纯旋转 (J4/J5/J6/J7) — 方向多样性, 10 姿态 ──
    ("旋转: 肘滚+0.40",     pose({3: 0.40})),
    ("旋转: 肘滚-0.40",     pose({3: -0.40})),
    ("旋转: 腕俯+0.30",     pose({4: 0.30})),
    ("旋转: 腕俯-0.30",     pose({4: -0.30})),
    ("旋转: 腕偏+0.30",     pose({5: 0.30})),
    ("旋转: 腕偏-0.30",     pose({5: -0.30})),
    ("旋转: 腕滚+0.40",     pose({6: 0.40})),
    ("旋转: 腕滚-0.40",     pose({6: -0.40})),
    ("旋转: 肘滚+0.25 腕滚+0.25", pose({3: 0.25, 6: 0.25})),
    ("旋转: 腕俯+0.20 腕偏+0.20", pose({4: 0.20, 5: 0.20})),

    # ── Group C: 混合平移+旋转, 14 姿态 ──
    ("混合: 肩+0.40 腕滚+0.30",       pose({1: 0.40, 6: 0.30})),
    ("混合: 肩-0.35 肘滚-0.30",       pose({1: -0.35, 3: -0.30})),
    ("混合: 肘+0.35 腕偏+0.25",       pose({2: 0.35, 5: 0.25})),
    ("混合: 肘-0.35 腕俯-0.25",       pose({2: -0.35, 4: -0.25})),
    ("混合: 底座+0.35 腕偏+0.25",     pose({0: 0.35, 5: 0.25})),
    ("混合: 底座-0.35 腕俯+0.25",     pose({0: -0.35, 4: 0.25})),
    ("混合: 肩+0.30 肘+0.25 腕滚-0.25", pose({1: 0.30, 2: 0.25, 6: -0.25})),
    ("混合: 肩-0.25 肘-0.25 肘滚+0.30", pose({1: -0.25, 2: -0.25, 3: 0.30})),
    ("混合: 底座+0.25 肘+0.25 腕偏-0.25", pose({0: 0.25, 2: 0.25, 5: -0.25})),
    ("混合: 底座-0.25 肩+0.25 腕滚+0.30", pose({0: -0.25, 1: 0.25, 6: 0.30})),
    ("混合: 底座+0.20 肩+0.25 肘滚+0.25", pose({0: 0.20, 1: 0.25, 3: 0.25})),
    ("混合: 底座-0.20 肘-0.20 腕俯+0.25", pose({0: -0.20, 2: -0.20, 4: 0.25})),
    ("混合: 肩+0.25 肘滚-0.25 腕偏+0.20", pose({1: 0.25, 3: -0.25, 5: 0.20})),
    ("混合: 肘+0.20 腕俯-0.20 腕滚+0.20", pose({2: 0.20, 4: -0.20, 6: 0.20})),

    # ── Group D: 极限 + 基准, 4 姿态 ──
    ("极限: 肩+0.60 肘+0.45",     pose({1: 0.60, 2: 0.45})),
    ("极限: 肩-0.45 肘-0.40",     pose({1: -0.45, 2: -0.40})),
    ("极限: 底座+0.40 肩+0.35 肘+0.25", pose({0: 0.40, 1: 0.35, 2: 0.25})),
    ("基准 (无扰动)",              pose({})),
]


def reduce_perturbation(offsets, factor=0.5):
    """缩小扰动 (标记不可见时渐进回退)"""
    return {k: v * factor for k, v in offsets.items()}


# ─── 手眼标定数学 ───────────────────────────────────────────────
def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])

def tsai(gR, gt, cR, ct):
    """Tsai-Lenz 手眼标定: 输入 flange2base / marker2cam, 返回 T_flange_cam (4x4)"""
    n = len(gR)
    AR, At, BR, Bt = [], [], [], []
    for i in range(n - 1):
        dRg = gR[i+1] @ gR[i].T;  dtg = gt[i+1] - dRg @ gt[i]
        dRc = cR[i+1] @ cR[i].T;  dtc = ct[i+1] - dRc @ ct[i]
        AR.append(dRg); At.append(dtg); BR.append(dRc); Bt.append(dtc)
    M = np.zeros((3*(n-1), 3)); v = np.zeros(3*(n-1))
    for i in range(n-1):
        a = Rotation.from_matrix(AR[i]).as_rotvec()
        b = Rotation.from_matrix(BR[i]).as_rotvec()
        M[3*i:3*(i+1)] = skew(a + b); v[3*i:3*(i+1)] = b - a
    peg = np.linalg.lstsq(M, v, rcond=None)[0]
    Rx = Rotation.from_rotvec(peg).as_matrix()
    C = np.zeros((3*(n-1), 3)); d = np.zeros(3*(n-1))
    for i in range(n-1):
        C[3*i:3*(i+1)] = np.eye(3) - AR[i]; d[3*i:3*(i+1)] = Rx @ Bt[i] - At[i]
    tx = np.linalg.lstsq(C, d, rcond=None)[0]
    T = np.eye(4); T[:3, :3] = Rx; T[:3, 3] = tx
    return T


def reprojection_spread(T_fc, gR, gt, ct):
    """标记中心投影到 base 系, 返回各点标准差 (cm) + 点集"""
    pts = []
    for i in range(len(gR)):
        Tbf = np.eye(4); Tbf[:3, :3] = gR[i]; Tbf[:3, 3] = gt[i]
        p = (Tbf @ T_fc @ np.array([ct[i][0], ct[i][1], ct[i][2], 1.0]))[:3]
        pts.append(p)
    pts = np.array(pts)
    return float(np.linalg.norm(pts.std(axis=0))) * 100, pts


def nonlinear_refine(T0, gR, gt, ct):
    """多初值 + 物理约束的非线性精修。
    相机装在末端 → 距 flange 应 < 0.30m (物理合理), 用 bounds 约束。
    多初值启动, 在物理合理解里选离散度最小的。
    """
    def residuals(params):
        rpy, t = params[:3], params[3:]
        R = Rotation.from_euler('xyz', rpy).as_matrix()
        X = np.eye(4); X[:3, :3] = R; X[:3, 3] = t
        pts = []
        for i in range(len(gR)):
            Tbf = np.eye(4); Tbf[:3, :3] = gR[i]; Tbf[:3, 3] = gt[i]
            pts.append((Tbf @ X @ np.array([ct[i][0], ct[i][1], ct[i][2], 1.0]))[:3])
        pts = np.array(pts)
        return (pts - pts.mean(axis=0)).flatten()

    lb = [-2*np.pi, -2*np.pi, -2*np.pi, -0.25, -0.25, -0.25]
    ub = [ 2*np.pi,  2*np.pi,  2*np.pi,  0.25,  0.25,  0.25]

    # 多个初值
    rpy_tsai = Rotation.from_matrix(T0[:3, :3]).as_euler('xyz')
    inits = [
        ("Tsai", np.concatenate([rpy_tsai, np.clip(T0[:3, 3], -0.25, 0.25)])),
    ]
    for t_guess in ([0, 0, 0.10], [-0.05, 0, 0.12], [0.05, 0.05, 0.08],
                    [-0.08, -0.05, 0.10], [0, 0.08, 0.06]):
        inits.append((f"t={t_guess}", np.array([0, 0, 0] + t_guess)))

    results = []
    for name, x0 in inits:
        try:
            res = least_squares(residuals, x0, bounds=(lb, ub), method='trf', max_nfev=3000)
            rpy, t = res.x[:3], res.x[3:]
            R = Rotation.from_euler('xyz', rpy).as_matrix()
            X = np.eye(4); X[:3, :3] = R; X[:3, 3] = t
            sp, _ = reprojection_spread(X, gR, gt, ct)
            d = float(np.linalg.norm(t))
            results.append((name, sp, d, X))
        except Exception:
            pass

    if not results:
        return T0  # 所有初值都失败, 退回 Tsai

    # 在物理合理解 (d<0.30m) 里选离散度最小
    valid = [r for r in results if r[2] < 0.30]
    if not valid:
        print("    ⚠️  所有解物理不合理, 取离散度最小者")
        valid = results
    best = min(valid, key=lambda r: r[1])
    print(f"    候选: ", end="")
    for name, sp, d, _ in sorted(results, key=lambda r: r[1]):
        flag = "✓" if d < 0.30 else "✗"
        print(f"{name}({sp:.1f}cm/{d:.3f}m{flag})", end=" ")
    print(f"\n    → 采用: {best[0]} (离散度={best[1]:.2f}cm, 距flange={best[2]:.3f}m)")
    return best[3]


# ─── 机器人 + 相机初始化 ────────────────────────────────────────
class CalibSystem:
    def __init__(self):
        # CAN + 臂
        subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
        time.sleep(0.3)
        cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                                    interface="socketcan", channel="can1")
        self.arm = AgxArmFactory.create_arm(cfg)
        self.arm.connect()
        try: self.arm.clear_joint_error()
        except Exception: pass
        self.arm.set_speed_percent(8)
        self.arm.set_crash_protection_rating(joint_index=255, rating=0)
        t0 = time.time()
        while not self.arm.enable() and time.time() - t0 < 10:
            time.sleep(0.2)
        print("[臂] 已使能, 速度=8%\n")

        # ArUco
        self.dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.det = cv2.aruco.ArucoDetector(self.dic, cv2.aruco.DetectorParameters())
        self.obj_pts = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                                 [MARKER_SIZE, MARKER_SIZE, 0],
                                 [0, MARKER_SIZE, 0]], dtype=np.float32)

        # ROS2
        rclpy.init()
        self.node = Node("calib_full")
        self._latest = {"img": None, "K": None, "dist": None}
        q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                       history=HistoryPolicy.KEEP_LAST, depth=1)
        def _img(msg):
            nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
            img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
            self._latest["img"] = img if msg.encoding == 'bgr8' else \
                cv2.cvtColor(img, cv2.COLOR_RGB2BGR if msg.encoding.startswith('rgb') else cv2.COLOR_GRAY2BGR)
        def _info(msg):
            if self._latest["K"] is None:
                self._latest["K"] = np.array(msg.k, dtype=np.float64).reshape(3, 3)
                self._latest["dist"] = np.array(msg.d, dtype=np.float64).reshape(-1)
        self.node.create_subscription(Image, "/camera/color/image_raw", _img, q)
        self.node.create_subscription(CameraInfo, "/camera/color/camera_info", _info, q)

    def wait_camera(self, timeout=8.0):
        print("[相机] 等待数据...", end="", flush=True)
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            if self._latest["K"] is not None and self._latest["img"] is not None:
                print(f" OK (fx={self._latest['K'][0,0]:.0f})\n")
                return True
        print(" ❌ 无数据!"); return False

    def get_flange(self):
        fp = self.arm.get_flange_pose()
        return list(fp.msg) if fp and fp.msg else None

    def xyzrpy_to_T(self, xyzrpy):
        x, y, z, r, p, yaw = xyzrpy
        T = np.eye(4)
        T[:3, :3] = tt.euler_matrix(r, p, yaw, axes='sxyz')[:3, :3]
        T[:3, 3] = [x, y, z]
        return T

    def grab_marker(self, n_frames=5):
        """连续抓 n 帧标记位姿, 返回 T_cam_marker 4x4 (中位数) 或 None"""
        Rs, ts = [], []
        for _ in range(n_frames * 6):
            rclpy.spin_once(self.node, timeout_sec=0.05)
            img = self._latest["img"]
            if img is None or self._latest["K"] is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = self.det.detectMarkers(gray)
            if ids is not None and MARKER_ID in ids.flatten():
                idx = list(ids.flatten()).index(MARKER_ID)
                ok, rvec, tvec = cv2.solvePnP(
                    self.obj_pts, corners[idx], self._latest["K"], self._latest["dist"])
                if ok:
                    R, _ = cv2.Rodrigues(rvec)
                    Rs.append(R); ts.append(tvec.flatten())
                    if len(Rs) >= n_frames:
                        break
        if len(Rs) < 3:
            return None
        R_avg = Rotation.from_matrix(Rs).mean().as_matrix()
        t_med = np.median(ts, axis=0)
        T = np.eye(4); T[:3, :3] = R_avg; T[:3, 3] = t_med
        return T

    def disconnect(self):
        self.arm.disconnect()
        print("[臂] 已断开")

    def move_to(self, joints_target):
        self.arm.move_j(joints_target)
        time.sleep(1.2)  # 等臂停稳 + 相机曝光稳定


# ─── 诊断: 关节利用度 ───────────────────────────────────────────
def joint_utilization(all_joints):
    """计算每个关节的行程范围 (rad→度), 用于诊断"""
    arr = np.array(all_joints)
    ranges = arr.max(axis=0) - arr.min(axis=0)
    print("\n  各关节行程 (rad / °):")
    names = ["J1底座", "J2肩", "J3肘", "J4肘滚", "J5腕俯", "J6腕偏", "J7腕滚"]
    stars = ["", "", "", " ⬅之前未用!", "", "", " ⬅未充分利用"]
    for i in range(7):
        deg = ranges[i] * 180 / np.pi
        status = "✅" if deg > 15 else ("🟡" if deg > 5 else "❌")
        print(f"    {names[i]:8s}  {ranges[i]:5.2f} rad = {deg:5.1f}°  {status}{stars[i]}")
    return ranges


# ─── 主流程 ─────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  手眼标定 (全关节) — Eye-in-Hand")
    print(f"  标记: DICT_4X4_50 ID={MARKER_ID} 边长={MARKER_SIZE}m")
    print(f"  基准: {[round(j,3) for j in BASE]}")
    print(f"  姿态: {len(POSES)} 个 (4组: 平移/旋转/混合/基准)")
    print("=" * 60)

    sys = CalibSystem()
    if not sys.wait_camera():
        return

    try:
        # ── Phase 1: 采集 ──
        print(f"\n{'='*55}")
        print(f"  Phase 1: 采集 {len(POSES)} 个姿态")
        print(f"{'='*55}\n")

        gR, gt, cR, ct = [], [], [], []
        all_joints = []
        collected, skipped, reduced = 0, 0, 0

        # 先走到基准确认可见
        sys.arm.move_j(BASE); time.sleep(1.5)
        if sys.grab_marker() is None:
            print("❌ 基准姿态看不到标记! 请用 set_base.py 重新设定 BASE")
            return
        print("✅ 基准姿态标记可见\n")

        for i, (desc, p) in enumerate(POSES):
            label = f"P{i+1:02d}"
            print(f"  [{label}/{len(POSES)}] {desc}")

            # 尝试原始扰动, 可见性失败则逐步回退
            current_pose = list(p)
            for retry in range(3):
                try:
                    sys.arm.move_j(current_pose); time.sleep(1.0)
                except Exception as e:
                    print(f"    ❌ 运动失败: {e}")
                    break

                T_cm = sys.grab_marker()
                fp = sys.get_flange()
                if T_cm is not None and fp is not None:
                    T_bf = sys.xyzrpy_to_T(fp)
                    gR.append(T_bf[:3, :3]); gt.append(T_bf[:3, 3])
                    cR.append(T_cm[:3, :3]); ct.append(T_cm[:3, 3])
                    joints = list(sys.arm.get_joint_angles().msg)
                    all_joints.append(joints)
                    print(f"    ✅ 采集 [{len(gR)}]  marker_t={np.round(T_cm[:3,3],3)}  "
                          f"d={np.linalg.norm(T_cm[:3,3]):.3f}m")
                    collected += 1
                    if retry > 0:
                        reduced += 1
                    break

                # 标记不可见 → 缩小扰动再试
                if retry < 2:
                    factor = 0.5 if retry == 0 else 0.3
                    # 缩小所有偏移
                    off = {j: (current_pose[j] - BASE[j]) * factor / (1.0 if retry==0 else 0.5)
                           for j in range(7) if abs(current_pose[j] - BASE[j]) > 0.01}
                    current_pose = list(BASE)
                    for j, d in off.items():
                        current_pose[j] += d
                    print(f"    ⚠️  不可见, 缩小扰动至 {factor*100:.0f}% 重试 ({retry+2}/3)...")
                else:
                    print(f"    ❌ 缩小后仍不可见, 跳过")
                    skipped += 1

        print(f"\n  采集完成: {collected} 组, 跳过 {skipped}, 回退 {reduced}")
        if collected < 8:
            print(f"  ❌ 有效样本不足 (<8), 退出。请调整标记位置后重试。")
            return

        # 关节利用度诊断
        joint_utilization(all_joints)

        # 距离变化诊断
        dists = np.array([c[2] for c in ct])
        print(f"\n  [诊断] 标记距离: {dists.min():.3f}~{dists.max():.3f}m "
              f"(变化 {np.ptp(dists)*100:.1f}cm, σ={dists.std()*100:.1f}cm)")
        if np.ptp(dists) < 0.10:
            print("  ❌ 距离变化 <10cm → 深度不可标定! 请增大 J2/J3 扰动或放远标记")
        elif np.ptp(dists) < 0.15:
            print("  ⚠️  距离变化偏小, 深度精度可能有限")
        else:
            print("  ✅ 距离变化充分")

        gpos = np.array(gt)
        pos_range = gpos.max(axis=0) - gpos.min(axis=0)
        print(f"  [诊断] flange 位置范围: x={pos_range[0]:.3f} y={pos_range[1]:.3f} z={pos_range[2]:.3f} (m)")

        # ── Phase 2: 求解 ──
        print(f"\n{'='*55}")
        print(f"  Phase 2: 手眼标定求解 ({collected} 组数据)")
        print(f"{'='*55}")

        # Tsai 初值
        T_tsai = tsai(gR, gt, cR, ct)
        sp_t, _ = reprojection_spread(T_tsai, gR, gt, ct)
        print(f"\n  [Tsai] 离散度={sp_t:.2f}cm  "
              f"距flange={np.linalg.norm(T_tsai[:3,3]):.3f}m  "
              f"t={np.round(T_tsai[:3,3],4)}")

        # 多初值非线性精修
        print("\n  [非线性精修] 多初值 + 物理约束:")
        T_best = nonlinear_refine(T_tsai, gR, gt, ct)
        sp_best, pts = reprojection_spread(T_best, gR, gt, ct)

        # ── Phase 3: 输出 ──
        print(f"\n{'='*55}")
        print(f"  Phase 3: 标定结果")
        print(f"{'='*55}")

        rpy = Rotation.from_matrix(T_best[:3, :3]).as_euler('xyz')
        quat = Rotation.from_matrix(T_best[:3, :3]).as_quat()  # xyzw

        # 保存 JSON
        result = {
            "position": [float(v) for v in T_best[:3, 3]],
            "orientation": [float(v) for v in quat],
            "rpy": [[float(v) for v in rpy]],
            "_meta": {
                "samples": collected, "skipped": skipped,
                "spread_cm": float(sp_best),
                "distance_range_cm": float(np.ptp(dists) * 100),
            }
        }
        # Fix: compute joint ranges separately
        arr_j = np.array(all_joints)
        result["_meta"]["joint_ranges_rad"] = [float(arr_j[:,i].max() - arr_j[:,i].min()) for i in range(7)]

        os.makedirs(CALIB_DIR, exist_ok=True)
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        json_out = f"{CALIB_DIR}/{ts}_calibration.json"
        with open(json_out, "w") as f:
            json.dump(result, f, indent=4)

        print(f"\n  T_flange_cam (相机在 flange/TCP 系):")
        print(f"    位置 xyz:  ({T_best[0,3]:.4f}, {T_best[1,3]:.4f}, {T_best[2,3]:.4f}) m")
        print(f"    姿态 rpy:  ({rpy[0]:.4f}, {rpy[1]:.4f}, {rpy[2]:.4f}) rad")
        print(f"    距 flange: {np.linalg.norm(T_best[:3,3]):.3f} m")
        print(f"  重投影离散度: {sp_best:.2f} cm")

        if   sp_best < 1.5: grade = "优秀 ✅"
        elif sp_best < 3.0: grade = "可用 🟡"
        else:               grade = "较差 ❌ (检查标记平整度/光照/姿态范围)"
        print(f"  评级: {grade}")
        print(f"  → 保存: {json_out}")

        # ── Phase 4: 更新 transforms.py ──
        print(f"\n{'='*55}")
        print(f"  Phase 4: 更新 CAM_MOUNT")
        print(f"{'='*55}")

        cam_mount = {
            "xyz": [round(float(T_best[0,3]), 4),
                    round(float(T_best[1,3]), 4),
                    round(float(T_best[2,3]), 4)],
            "rpy": [round(float(rpy[0]), 4),
                    round(float(rpy[1]), 4),
                    round(float(rpy[2]), 4)],
        }

        if os.path.exists(TRANSFORMS_FILE):
            content = open(TRANSFORMS_FILE).read()
            lines = content.splitlines()
            new_lines = []
            xyz_done, rpy_done = False, False
            for line in lines:
                if line.strip().startswith('"xyz":') and not xyz_done:
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(f'{indent}"xyz": {cam_mount["xyz"]},       # TCP 系: x,y,z (米)')
                    xyz_done = True
                elif line.strip().startswith('"rpy":') and not rpy_done:
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(f'{indent}"rpy": {cam_mount["rpy"]},             # [roll,pitch,yaw], R=Rz(yaw)·Ry(p)·Rx(r)')
                    rpy_done = True
                else:
                    new_lines.append(line)

            if xyz_done and rpy_done:
                open(TRANSFORMS_FILE, "w").write("\n".join(new_lines) + "\n")
                print(f"  ✅ 已更新 {TRANSFORMS_FILE}")
                print(f"     CAM_MOUNT xyz: {cam_mount['xyz']}")
                print(f"     CAM_MOUNT rpy: {cam_mount['rpy']}")
            else:
                print(f"  ❌ 自动更新失败, 请手动设置:")
                print(f'     "xyz": {cam_mount["xyz"]},')
                print(f'     "rpy": {cam_mount["rpy"]},')
        else:
            print(f"  ❌ 找不到 {TRANSFORMS_FILE}")

        # ── Phase 5: 独立验证 ──
        print(f"\n{'='*55}")
        print(f"  Phase 5: 独立验证 (12 个随机姿态)")
        print(f"{'='*55}\n")

        # 随机生成 12 个独立姿态 (不同于标定姿态, 用小扰动确保标记可见)
        rng = np.random.RandomState(int(time.time()) % 100000)
        JITTER = np.array([0.06, 0.08, 0.06, 0.05, 0.06, 0.06, 0.06])  # 4x4小marker用小扰动
        verify_samples = []
        v_skipped = 0

        for vi in range(12):
            vp = list(BASE) + rng.uniform(-1, 1, 7) * JITTER
            try:
                sys.arm.move_j(vp); time.sleep(1.0)
            except Exception:
                v_skipped += 1; continue
            p_cam_med = None
            # 中位数采样
            _ts = []
            for _ in range(8):
                T = sys.grab_marker()
                if T is not None:
                    _ts.append(T[:3, 3])
                    if len(_ts) >= 4:
                        break
            if len(_ts) < 2:
                v_skipped += 1; continue
            p_cam = np.median(_ts, axis=0)
            fp = sys.get_flange()
            if fp is None:
                v_skipped += 1; continue
            T_bf = sys.xyzrpy_to_T(fp)
            p_base = (T_bf @ T_best @ np.array([p_cam[0], p_cam[1], p_cam[2], 1.0]))[:3]
            verify_samples.append(p_base)
            print(f"  V{vi+1:2d}: ({p_base[0]:.4f}, {p_base[1]:.4f}, {p_base[2]:.4f}) m")

        print(f"\n  验证采集: {len(verify_samples)} 组, 跳过 {v_skipped}")

        if len(verify_samples) >= 6:
            arr = np.array(verify_samples)
            mean, std = arr.mean(axis=0), arr.std(axis=0)
            spread = float(np.linalg.norm(std))
            print(f"  标记基座系均值: ({mean[0]:.3f}, {mean[1]:.3f}, {mean[2]:.3f}) m")
            print(f"  σx={std[0]*100:.2f}cm  σy={std[1]*100:.2f}cm  σz={std[2]*100:.2f}cm")
            print(f"  综合离散度: {spread*100:.2f} cm")
            print("-" * 50)
            for ax, nm in [(0, "x(左右)"), (1, "y(深度·关键)"), (2, "z(高度)")]:
                if std[ax] < 0.015: g = "✅ 优秀"
                elif std[ax] < 0.030: g = "🟡 可用"
                else: g = "❌ 较差"
                print(f"  σ{nm}: {std[ax]*100:.2f}cm  {g}")
            print("-" * 50)
            if std[1] < 0.02 and std[0] < 0.03 and std[2] < 0.03:
                print("  🎉 标定成功! 可用于抓取。")
            else:
                print("  ⚠️  精度不理想, 建议检查标记平整度 / 增大扰动范围 / 重试")

    finally:
        sys.disconnect()
        print("\n完成 (保持使能状态)")


if __name__ == "__main__":
    main()
