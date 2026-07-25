"""全自动手眼标定 (eye-in-hand) — 一个脚本搞定采集+求解+验证。

流程:
  1. 自动遍历 18 个姿态, 每姿态采 (flange位姿, marker位姿) 多帧中位数
  2. Tsai 线性解作为初值
  3. scipy 非线性最小二乘精修 (直接最小化 "标记在基座系位置" 的一致性误差)
  4. 自动验证 (重投影离散度) + 输出 json (兼容 parse_calib_result.py)

相比 handeye_calibration_ros 交互节点:
  - 杜绝重复采集 (每姿态自动采一组)
  - 非线性优化, 精度远高于纯 Tsai

用法: python3 calib_auto.py
依赖: 终端1相机在跑; base_pose.json 已设置
"""
import subprocess, time, sys, glob, os, json
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
import tf_transformations as tt
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW

CALIB_DIR = "/root/grab_skill/calibration"
MARKER_ID, MARKER_SIZE = 0, 0.15   # ⚠️ 必须与打印的实际黑方块边长一致 (现 15cm)
_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_DET = cv2.aruco.ArucoDetector(_DIC, cv2.aruco.DetectorParameters())
_OBJ = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                 [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)


# ─── 基准 + 姿态集 (同 verify_auto) ─────────────────────────
def load_base():
    f = f"{CALIB_DIR}/base_pose.json"
    if os.path.exists(f):
        return list(json.loads(open(f).read())["joints"])
    print("⚠️  无 base_pose.json, 用默认"); return [1.51, -0.20, -2.757, 1.67, 2.757, 0.363, -0.773]

BASE = load_base()
def pose(o):
    p = list(BASE)
    for k, v in o.items(): p[k] += v
    return p
# 距离扫描为主的姿态集 (配 15cm 标记 + 远基准, 破深度病态)
# 索引: 0=J1底座 1=J2肩 2=J3肘 3=J4肘转 4=J5腕俯 5=J6腕转 6=J7末端roll
# J2/J3 (idx1,2) 改 flange 前后 → 标记距离大幅变化 (破深度病态, 占一半姿态)
# J5/J6/J7 (idx4,5,6) 改相机朝向 → 旋转激励
POSES = [
    pose({}),
    # —— 距离大幅扫描 (最关键, 占 8/20) ——
    pose({1: 0.30}), pose({1: -0.30}),
    pose({1: 0.20, 2: 0.12}), pose({1: -0.20, 2: -0.12}),
    pose({2: 0.20}), pose({2: -0.20}),
    pose({1: 0.15}), pose({1: -0.15}),
    # —— 朝向适度变化 (避免出视野) ——
    pose({4: 0.15}), pose({4: -0.15}),
    pose({5: 0.15}), pose({5: -0.15}),
    pose({4: 0.10, 5: 0.10}), pose({4: -0.10, 5: -0.10}),
    # —— 左右 + roll + 组合 ——
    pose({0: 0.15, 4: 0.08}), pose({0: -0.15, 5: 0.08}),
    pose({6: 0.12}), pose({6: -0.12, 4: 0.06}),
    pose({0: 0.10, 1: 0.10, 5: -0.08}),
]

# ─── CAN + 臂 ───────────────────────────────────────────────
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
arm.set_speed_percent(8)
arm.set_crash_protection_rating(joint_index=255, rating=0)
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_flange_xyzrpy():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None

def xyzrpy_to_T(xyzrpy):
    """[x,y,z,r,p,y] → 4x4, R=Rz(yaw)·Ry(p)·Rx(r) (sxyz)"""
    x, y, z, r, p, yaw = xyzrpy
    T = np.eye(4)
    T[:3, :3] = tt.euler_matrix(r, p, yaw, axes='sxyz')[:3, :3]
    T[:3, 3] = [x, y, z]
    return T

# ─── ROS2 + 相机 ────────────────────────────────────────────
rclpy.init()
node = Node("calib_auto")
_latest = {"img": None, "K": None, "dist": None}
_q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)

def _on_image(msg):
    nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
    img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
    _latest["img"] = img if msg.encoding == 'bgr8' else \
        cv2.cvtColor(img, cv2.COLOR_RGB2BGR if msg.encoding.startswith('rgb') else cv2.COLOR_GRAY2BGR)

def _on_info(msg):
    if _latest["K"] is None:
        _latest["K"] = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        _latest["dist"] = np.array(msg.d, dtype=np.float64).reshape(-1)

node.create_subscription(Image, "/camera/color/image_raw", _on_image, _q)
node.create_subscription(CameraInfo, "/camera/color/camera_info", _on_info, _q)


def grab_marker_rt(n=5):
    """连续抓 n 帧, 返回 (T_cam_marker 4x4, 帧数) 或 (None, 0)"""
    Rs, ts = [], []
    for _ in range(n * 5):
        rclpy.spin_once(node, timeout_sec=0.05)
        img = _latest["img"]
        if img is None or _latest["K"] is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = _DET.detectMarkers(gray)
        if ids is not None and MARKER_ID in ids.flatten():
            idx = list(ids.flatten()).index(MARKER_ID)
            ok, rvec, tvec = cv2.solvePnP(_OBJ, corners[idx], _latest["K"], _latest["dist"])
            if ok:
                R, _ = cv2.Rodrigues(rvec)
                Rs.append(R); ts.append(tvec.flatten())
                if len(Rs) >= n:
                    break
    if len(Rs) < 2:
        return None, 0
    # 旋转平均 + 平移中位数
    R_avg = Rotation.from_matrix(Rs).mean().as_matrix()
    t_med = np.median(ts, axis=0)
    T = np.eye(4); T[:3, :3] = R_avg; T[:3, 3] = t_med
    return T, len(Rs)


def wait_camera():
    print("[calib] 等相机就绪...", end="", flush=True)
    for _ in range(60):
        rclpy.spin_once(node, timeout_sec=0.1)
        if _latest["K"] is not None and _latest["img"] is not None:
            print(f" OK (fx={_latest['K'][0,0]:.0f})"); return True
    print("\n❌ 相机没数据"); return False


# ─── Hand-eye 求解 ──────────────────────────────────────────
def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])

def tsai(gR, gt, cR, ct):
    """Tsai-Lenz: 输入 gripper2base / target2cam, 返回 T_flange_cam (4x4)"""
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
    """标记中心投到 base 系, 返回各点到均值的综合标准差 (cm)"""
    pts = []
    for i in range(len(gR)):
        Tbf = np.eye(4); Tbf[:3, :3] = gR[i]; Tbf[:3, 3] = gt[i]
        p = (Tbf @ T_fc @ np.array([ct[i][0], ct[i][1], ct[i][2], 1.0]))[:3]
        pts.append(p)
    pts = np.array(pts)
    return float(np.linalg.norm(pts.std(axis=0))) * 100, pts


def nonlinear_refine(T0, gR, gt, ct, prior_t=None):
    """多初值 + 物理约束的非线性精修。
    相机装在末端 → 距 flange 应 < 0.25m, 用 bounds 约束 + 物理筛选,
    避免 Tsai 初值不准时优化跳到 "一致但错误" 的局部解。"""
    def residuals(params):
        rpy, t = params[:3], params[3:]
        R = Rotation.from_euler('xyz', rpy).as_matrix()  # extrinsic xyz == sxyz
        X = np.eye(4); X[:3, :3] = R; X[:3, 3] = t
        pts = []
        for i in range(len(gR)):
            Tbf = np.eye(4); Tbf[:3, :3] = gR[i]; Tbf[:3, 3] = gt[i]
            pts.append((Tbf @ X @ np.array([ct[i][0], ct[i][1], ct[i][2], 1.0]))[:3])
        pts = np.array(pts)
        return (pts - pts.mean(axis=0)).flatten()

    # 物理约束: t 每分量 ∈ [-0.25, 0.25] → 总距离 < 0.43m
    lb = [-2*np.pi, -2*np.pi, -2*np.pi, -0.25, -0.25, -0.25]
    ub = [ 2*np.pi,  2*np.pi,  2*np.pi,  0.25,  0.25,  0.25]

    # 多个初值
    inits = []
    rpy_tsai = Rotation.from_matrix(T0[:3, :3]).as_euler('xyz')
    inits.append(("Tsai", np.concatenate([rpy_tsai, np.clip(T0[:3, 3], -0.25, 0.25)])))
    for t_guess in ([0, 0, 0.10], [-0.10, -0.10, -0.10], [0.05, 0, 0.10], [-0.05, -0.05, 0.05]):
        inits.append((f"guess{t_guess}", np.array([0, 0, 0] + t_guess)))
    if prior_t is not None:
        inits.append(("prior", np.array([0, 0, 0] + list(np.clip(prior_t, -0.25, 0.25)))))

    results = []
    for name, x0 in inits:
        try:
            res = least_squares(residuals, x0, bounds=(lb, ub), method='trf', max_nfev=2000)
            rpy, t = res.x[:3], res.x[3:]
            R = Rotation.from_euler('xyz', rpy).as_matrix()
            X = np.eye(4); X[:3, :3] = R; X[:3, 3] = t
            sp, _ = reprojection_spread(X, gR, gt, ct)
            results.append((name, sp, float(np.linalg.norm(t)), X))
        except Exception as e:
            print(f"    初值 {name}: 失败 ({e})")

    # 打印所有候选
    print("    候选解 (初值/离散度/距flange):")
    for name, sp, dist, _ in sorted(results, key=lambda r: r[1]):
        flag = "✓" if dist < 0.30 else "✗(物理不合理)"
        print(f"      {name:8s} 离散度={sp:5.2f}cm  距flange={dist:.3f}m {flag}")

    # 在物理合理解里选离散度最小
    valid = [r for r in results if r[2] < 0.30]
    if not valid:
        print("    ⚠️  无物理合理解, 取离散度最小者(可能不准)")
        valid = results
    best = min(valid, key=lambda r: r[1])
    print(f"    → 采用初值 '{best[0]}' 的解")
    return best[3]


# ─── 主流程 ─────────────────────────────────────────────────
def main():
    if not wait_camera():
        return

    print(f"\n[calib] 采集 {len(POSES)} 个姿态 (每姿态多帧中位数)...\n")
    gR, gt, cR, ct = [], [], [], []

    # 基准
    arm.move_j(BASE); time.sleep(1.5)
    for i, tgt in enumerate(POSES):
        try:
            arm.move_j(tgt); time.sleep(1.2)
        except Exception as e:
            print(f"  P{i+1:2d}: 运动失败 {e}"); continue
        T_cm, n = grab_marker_rt()
        fp = get_flange_xyzrpy()
        if T_cm is None or fp is None:
            print(f"  P{i+1:2d}/{len(POSES)}: ❌ 标记不可见, 跳过"); continue
        T_bf = xyzrpy_to_T(fp)
        gR.append(T_bf[:3, :3]); gt.append(T_bf[:3, 3])
        cR.append(T_cm[:3, :3]); ct.append(T_cm[:3, 3])
        print(f"  P{i+1:2d}/{len(POSES)}: ✅ 采集 [n={n}]  marker t={np.round(T_cm[:3,3],3)}")

    if len(gR) < 8:
        print(f"\n❌ 有效样本仅 {len(gR)} (<8), 退出"); return

    print(f"\n[calib] 采集完成 {len(gR)} 组, 开始求解...")
    # flange 位姿诊断
    gpos = np.array(gt)
    print(f"  [诊断] flange 位置范围: "
          f"x[{gpos[:,0].min():.3f}~{gpos[:,0].max():.3f}] "
          f"y[{gpos[:,1].min():.3f}~{gpos[:,1].max():.3f}] "
          f"z[{gpos[:,2].min():.3f}~{gpos[:,2].max():.3f}]")
    # 标记距离变化诊断 (深度病态检查 — 最关键!)
    dists = np.array([c[2] for c in ct])
    print(f"  [诊断] 标记距离范围: {dists.min():.3f}~{dists.max():.3f}m "
          f"(变化 {np.ptp(dists)*100:.1f}cm, σ={dists.std()*100:.1f}cm)")
    if np.ptp(dists) < 0.10:
        print("  ❌❌ 标记距离变化 <10cm! 深度方向不可标定 (上次 σy=40cm 就是这个原因)")
        print("       → 请把标记放远 (set_base 到相机距标记 0.50m 左右), 再加大姿态扰动重跑")
    elif np.ptp(dists) < 0.18:
        print("  ⚠️  距离变化偏小 (<18cm), 深度方向精度可能有限")
    else:
        print("  ✅ 距离变化充分, 深度方向可标定")
    if np.ptp(gpos[:, 0]) < 0.05 and np.ptp(gpos[:, 1]) < 0.05:
        print("  ⚠️  flange 位置变化太小 (<5cm), 标定会退化!")

    # 1) Tsai 初值
    T_tsai = tsai(gR, gt, cR, ct)
    sp_tsai, _ = reprojection_spread(T_tsai, gR, gt, ct)
    print(f"\n  [Tsai]    离散度={sp_tsai:.2f}cm  "
          f"距flange={np.linalg.norm(T_tsai[:3,3]):.3f}m  "
          f"t={np.round(T_tsai[:3,3],3)}")

    # 加载历史先验 (上次物理合理的标定结果)
    prior_t = None
    for jf in sorted(glob.glob(f"{CALIB_DIR}/*_calibration.json"))[:-1]:
        try:
            d = json.loads(open(jf).read())
            pt = np.array(d["position"])
            if np.linalg.norm(pt) < 0.30:
                prior_t = pt  # 取最近一个合理的
        except Exception:
            pass
    if prior_t is not None:
        print(f"  [先验] 使用历史合理标定 t={np.round(prior_t,3)} 作为初值之一")

    # 2) 多初值非线性精修
    print("\n  [非线性精修] 多初值 + 物理约束 (距flange<0.30m):")
    T_ref = nonlinear_refine(T_tsai, gR, gt, ct, prior_t=prior_t)
    sp_ref, pts = reprojection_spread(T_ref, gR, gt, ct)

    # 选最优 (物理合理前提下离散度最小)
    T_best = T_ref
    sp_best = sp_ref

    # 输出 (兼容 handeye_calibration_ros 的 json 格式)
    q = Rotation.from_matrix(T_best[:3, :3]).as_quat()   # xyzw
    rpy = Rotation.from_quat(q).as_euler('xyz')           # sxyz
    result = {
        "position": list(T_best[:3, 3]),
        "orientation": list(q),
        "rpy": [list(rpy)],
    }
    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(CALIB_DIR, exist_ok=True)
    out = f"{CALIB_DIR}/{ts}_calibration.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=4)

    # 评估
    print("\n" + "=" * 55)
    print("  全自动标定结果")
    print("=" * 55)
    print(f"  T_flange_cam pos: ({T_best[0,3]:.4f}, {T_best[1,3]:.4f}, {T_best[2,3]:.4f})")
    print(f"  rpy (rad):        ({rpy[0]:.4f}, {rpy[1]:.4f}, {rpy[2]:.4f})")
    print(f"  相机距 flange:    {np.linalg.norm(T_best[:3,3]):.3f} m")
    print(f"  重投影离散度:     {sp_best:.2f} cm  (基于 {len(gR)} 组训练数据)")
    if   sp_best < 1.5: grade = "优秀 ✅"
    elif sp_best < 3.0: grade = "可用 🟡"
    else:               grade = "较差 ❌ (检查标记平整度/光照/姿态范围)"
    print(f"  评级: {grade}")
    print(f"  → 已保存 {out}")
    print("=" * 55)
    print("\n应用: python3 /root/grab_skill/parse_calib_result.py")


try:
    main()
finally:
    arm.disconnect()
    print("[calib] 断开 (保持使能)")
