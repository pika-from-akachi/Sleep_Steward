"""示教拖拽手眼标定 (eye-in-hand) — 拖动臂自动采集。

工作流:
  1. 进入零力拖拽模式 (set_leader_mode): 抓住臂随意拖
  2. 每当臂停住 ~1 秒 → 自动采一组 (flange 位姿 + marker 位姿)
  3. 拖到下一个姿态停住 → 自动采下一组 (拖动期间不采, 杜绝重复)
  4. 实时显示距离范围, 提醒多采不同距离 (破深度病态)
  5. 采够或按 q → 切回正常模式 → Tsai+非线性求解 → 验证

⚠️ 重点: 主动拖到「近/中/远」不同距离 + 不同朝向, 否则深度方向会错!

用法: python3 calib_teach.py
"""
import subprocess, time, sys, glob, os, json, threading, termios, tty
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
TARGET_N = 20                  # 目标采集组数 (可继续多采)
MARKER_ID, MARKER_SIZE = 0, 0.10
_DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
_DET = cv2.aruco.ArucoDetector(_DIC, cv2.aruco.DetectorParameters())
_OBJ = np.array([[0, 0, 0], [MARKER_SIZE, 0, 0],
                 [MARKER_SIZE, MARKER_SIZE, 0], [0, MARKER_SIZE, 0]], dtype=np.float32)

# ─── CAN + 臂 ───────────────────────────────────────────────
subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
time.sleep(0.3)
cfg = create_agx_arm_config(robot=ArmModel.NERO, firmeware_version=NeroFW.V112,
                            interface="socketcan", channel="can1")
arm = AgxArmFactory.create_arm(cfg); arm.connect()
try: arm.clear_joint_error()
except Exception: pass
t0 = time.time()
while not arm.enable() and time.time() - t0 < 10:
    time.sleep(0.2)

def get_flange_xyzrpy():
    fp = arm.get_flange_pose()
    return list(fp.msg) if fp and fp.msg else None

def xyzrpy_to_T(xyzrpy):
    x, y, z, r, p, yaw = xyzrpy
    T = np.eye(4); T[:3, :3] = tt.euler_matrix(r, p, yaw, axes='sxyz')[:3, :3]; T[:3, 3] = [x, y, z]
    return T

# ─── ROS2 + 相机 ────────────────────────────────────────────
rclpy.init()
node = Node("calib_teach")
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
    Rs, ts = [], []
    for _ in range(n * 5):
        rclpy.spin_once(node, timeout_sec=0.05)
        img = _latest["img"]
        if img is None or _latest["K"] is None: continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = _DET.detectMarkers(gray)
        if ids is not None and MARKER_ID in ids.flatten():
            idx = list(ids.flatten()).index(MARKER_ID)
            ok, rvec, tvec = cv2.solvePnP(_OBJ, corners[idx], _latest["K"], _latest["dist"])
            if ok:
                R, _ = cv2.Rodrigues(rvec); Rs.append(R); ts.append(tvec.flatten())
                if len(Rs) >= n: break
    if len(Rs) < 2: return None
    T = np.eye(4)
    T[:3, :3] = Rotation.from_matrix(Rs).mean().as_matrix()
    T[:3, 3] = np.median(ts, axis=0)
    return T

def wait_camera():
    print("[teach] 等相机...", end="", flush=True)
    for _ in range(60):
        rclpy.spin_once(node, timeout_sec=0.1)
        if _latest["K"] is not None and _latest["img"] is not None:
            print(f" OK"); return True
    print(" ❌"); return False

# ─── 求解 (同 calib_auto) ───────────────────────────────────
def skew(v): return np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
def tsai(gR, gt, cR, ct):
    n = len(gR); AR,At,BR,Bt=[],[],[],[]
    for i in range(n-1):
        dRg=gR[i+1]@gR[i].T; dtg=gt[i+1]-dRg@gt[i]
        dRc=cR[i+1]@cR[i].T; dtc=ct[i+1]-dRc@ct[i]
        AR.append(dRg);At.append(dtg);BR.append(dRc);Bt.append(dtc)
    M=np.zeros((3*(n-1),3));v=np.zeros(3*(n-1))
    for i in range(n-1):
        a=Rotation.from_matrix(AR[i]).as_rotvec(); b=Rotation.from_matrix(BR[i]).as_rotvec()
        M[3*i:3*(i+1)]=skew(a+b); v[3*i:3*(i+1)]=b-a
    Rx=Rotation.from_rotvec(np.linalg.lstsq(M,v,rcond=None)[0]).as_matrix()
    C=np.zeros((3*(n-1),3));d=np.zeros(3*(n-1))
    for i in range(n-1):
        C[3*i:3*(i+1)]=np.eye(3)-AR[i]; d[3*i:3*(i+1)]=Rx@Bt[i]-At[i]
    T=np.eye(4);T[:3,:3]=Rx;T[:3,3]=np.linalg.lstsq(C,d,rcond=None)[0]
    return T

def reprojection_spread(T_fc, gR, gt, ct):
    pts=[]
    for i in range(len(gR)):
        Tbf=np.eye(4);Tbf[:3,:3]=gR[i];Tbf[:3,3]=gt[i]
        pts.append((Tbf@T_fc@np.array([ct[i][0],ct[i][1],ct[i][2],1.0]))[:3])
    pts=np.array(pts); return float(np.linalg.norm(pts.std(0)))*100

def nonlinear_refine(T0, gR, gt, ct, prior_t=None):
    def residuals(params):
        rpy,t=params[:3],params[3:]
        R=Rotation.from_euler('xyz',rpy).as_matrix(); X=np.eye(4);X[:3,:3]=R;X[:3,3]=t
        pts=[]
        for i in range(len(gR)):
            Tbf=np.eye(4);Tbf[:3,:3]=gR[i];Tbf[:3,3]=gt[i]
            pts.append((Tbf@X@np.array([ct[i][0],ct[i][1],ct[i][2],1.0]))[:3])
        pts=np.array(pts); return (pts-pts.mean(0)).flatten()
    lb=[-2*np.pi]*3+[-0.25]*3; ub=[2*np.pi]*3+[0.25]*3
    inits=[("Tsai",np.concatenate([Rotation.from_matrix(T0[:3,:3]).as_euler('xyz'),np.clip(T0[:3,3],-0.25,0.25)]))]
    for tg in ([0,0,0.1],[-0.1,-0.1,-0.1],[0.05,0,0.1]):
        inits.append((f"guess{tg}",np.array([0,0,0]+tg)))
    if prior_t is not None: inits.append(("prior",np.array([0,0,0]+list(np.clip(prior_t,-0.25,0.25)))))
    results=[]
    for nm,x0 in inits:
        try:
            res=least_squares(residuals,x0,bounds=(lb,ub),method='trf',max_nfev=2000)
            rpy,t=res.x[:3],res.x[3:]; R=Rotation.from_euler('xyz',rpy).as_matrix()
            X=np.eye(4);X[:3,:3]=R;X[:3,3]=t
            results.append((nm,reprojection_spread(X,gR,gt,ct),float(np.linalg.norm(t)),X))
        except Exception: pass
    valid=[r for r in results if r[2]<0.30] or results
    return min(valid,key=lambda r:r[1])[3]

# ─── 示教采集 ───────────────────────────────────────────────
collecting = True
gR, gt, cR, ct = [], [], [], []
last_sample_flange = None

def clear_buf():
    fd=sys.stdin.fileno(); old=termios.tcgetattr(fd)
    try: tty.setraw(fd)
    finally: termios.tcsetattr(fd,termios.TCSADRAIN,old)

def collect_loop():
    """拖拽采集: 移动→停住~1s→自动采→必须再移动才能采下一组"""
    global last_sample_flange
    last_pose = None
    stable_cnt = 0
    armed = True   # 等待静止触发
    while collecting and len(ct) < 40:
        fp = get_flange_xyzrpy()
        if fp is None:
            time.sleep(0.05); continue
        rclpy.spin_once(node, timeout_sec=0.0)  # 推进图像回调
        moved = last_pose is not None and np.linalg.norm(np.array(fp[:3]) - np.array(last_pose[:3])) > 0.01
        if moved:
            armed = True; stable_cnt = 0
        elif armed:
            stable_cnt += 1
            if stable_cnt >= 18:   # ~1s 静止 (55ms*18)
                # 采样
                T_cm = grab_marker_rt(5)
                if T_cm is not None:
                    d = float(T_cm[2, 3])
                    # 更新显示
                    dists = [c[2] for c in ct] + [d]
                    sys.stdout.write(
                        f"\r  已采 {len(ct):2d}/{TARGET_N} | "
                        f"标记距离 {min(dists):.2f}~{max(dists):.2f}m "
                        f"(变化{(max(dists)-min(dists))*100:.0f}cm) | "
                        f"本次 flange y={fp[1]:.2f} 距={d:.2f}m   ")
                    sys.stdout.flush()
                    T_bf = xyzrpy_to_T(fp)
                    gR.append(T_bf[:3,:3]); gt.append(T_bf[:3,3])
                    cR.append(T_cm[:3,:3]); ct.append(T_cm[:3,3])
                    last_sample_flange = fp
                else:
                    sys.stdout.write(f"\r  ⚠️ 停住了但没看到标记, 拖到能看到的位置再停        "); sys.stdout.flush()
                armed = False; stable_cnt = 0
        last_pose = fp
        time.sleep(0.055)

def solve_and_report():
    if len(gR) < 8:
        print(f"\n❌ 有效样本仅 {len(gR)} (<8), 退出"); return
    gpos = np.array(gt)
    dists = np.array([c[2] for c in ct])
    print(f"\n\n[teach] 采集 {len(gR)} 组, 开始求解")
    print(f"  [诊断] flange y 范围: {gpos[:,1].min():.3f}~{gpos[:,1].max():.3f}m")
    print(f"  [诊断] 标记距离范围: {dists.min():.3f}~{dists.max():.3f}m (变化{np.ptp(dists)*100:.1f}cm)")
    if np.ptp(dists) < 0.10:
        print("  ❌❌ 距离变化 <10cm! 深度方向仍会错。重新跑, 主动拖到近/中/远不同距离")
    T_tsai = tsai(gR,gt,cR,ct)
    sp_t = reprojection_spread(T_tsai,gR,gt,ct)
    print(f"  [Tsai]   离散度={sp_t:.2f}cm 距flange={np.linalg.norm(T_tsai[:3,3]):.3f}m")
    prior_t=None
    for jf in sorted(glob.glob(f"{CALIB_DIR}/*_calibration.json"))[:-1]:
        try:
            pt=np.array(json.loads(open(jf).read())["position"])
            if np.linalg.norm(pt)<0.30: prior_t=pt
        except Exception: pass
    print("  [精修] 多初值+物理约束:")
    T_ref = nonlinear_refine(T_tsai,gR,gt,ct,prior_t=prior_t)
    T_best = T_ref
    q=Rotation.from_matrix(T_best[:3,:3]).as_quat()
    rpy=Rotation.from_quat(q).as_euler('xyz')
    result={"position":list(T_best[:3,3]),"orientation":list(q),"rpy":[list(rpy)]}
    ts=time.strftime("%Y-%m-%d_%H-%M-%S"); os.makedirs(CALIB_DIR,exist_ok=True)
    out=f"{CALIB_DIR}/{ts}_calibration.json"
    json.dump(result,open(out,"w"),indent=4)
    sp=reprojection_spread(T_best,gR,gt,ct)
    print("\n"+"="*55)
    print("  示教标定结果")
    print("="*55)
    print(f"  T_flange_cam: ({T_best[0,3]:.4f}, {T_best[1,3]:.4f}, {T_best[2,3]:.4f})")
    print(f"  rpy(rad):     ({rpy[0]:.4f}, {rpy[1]:.4f}, {rpy[2]:.4f})")
    print(f"  距flange:     {np.linalg.norm(T_best[:3,3]):.3f}m")
    print(f"  训练离散度:   {sp:.2f}cm  (⚠️ 用 verify_calibration.py 独立姿态验证才算数)")
    print(f"  → {out}")
    print("="*55)
    print("\n应用: python3 /root/grab_skill/parse_calib_result.py")

# ─── 主流程 ─────────────────────────────────────────────────
def main():
    global collecting
    if not wait_camera(): return
    print("\n" + "="*55)
    print("  示教拖拽标定 — 即将进入零力拖拽模式")
    print("="*55)
    print("  操作:")
    print("    1. 抓住臂 (末端/连杆), 拖到目标姿态")
    print("    2. 松手或保持静止 ~1 秒 → 自动采集")
    print("    3. 拖到下一个姿态停住 → 自动采下一组")
    print("  ⚠️ 关键: 主动覆盖不同距离 (近0.3/中0.45/远0.6m) + 不同朝向")
    print("     距离变化 >10cm 才能解决深度方向!")
    print("  结束: 按 Enter (采够后) 或 Ctrl+C")
    print("="*55)
    input("\n  准备好按 Enter 进入拖拽模式...")
    arm.set_leader_mode()
    print("  ✅ 已进入零力拖拽模式 — 现在可以拖动臂了\n")

    th = threading.Thread(target=collect_loop, daemon=True)
    th.start()
    try:
        # 等用户按 Enter 结束
        while collecting:
            time.sleep(0.2)
            if len(ct) >= TARGET_N:
                sys.stdout.write(f"\r  ✅ 已采 {len(ct)} 组 (目标 {TARGET_N}). 按 Enter 结束并求解, 或继续拖动多采...   ")
                sys.stdout.flush()
                # 非阻塞检查 Enter
                import select
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    break
    except KeyboardInterrupt:
        print("\n  收到中断信号")
    collecting = False
    time.sleep(0.3)
    print("\n  切回正常模式...")
    arm.set_follower_mode()
    time.sleep(0.5)
    solve_and_report()

try:
    main()
finally:
    collecting = False
    try: arm.set_follower_mode()
    except Exception: pass
    arm.disconnect()
    print("[teach] 断开 (保持使能)")
