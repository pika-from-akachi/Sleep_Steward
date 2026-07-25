"""
手眼标定工具 (Eye-to-Hand)
相机固定安装，标定相机→机械臂基座的变换矩阵

方法: ArUco 标记板
1. 打印 ArUco 标记贴在机械臂末端/夹爪上
2. 手动把臂摆到 4~6 个不同姿态
3. 每个姿态: 读关节角 + 拍照 → 检测标记在相机中的位姿
4. 解算 T_camera_to_base

用法:
    python3 calibrate.py --setup     # 第1步: 在零位拍标记，建立初始参考
    python3 calibrate.py --collect   # 第2步: 采集多组数据
    python3 calibrate.py --solve     # 第3步: 求解变换矩阵
    python3 calibrate.py --test      # 第4步: 验证精度

需安装: pip3 install opencv-contrib-python
"""

import argparse
import json
import time
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

# ─── 本模块 ──────────────────────────────────────────────────
from camera import StereoCamera
from arm_control import NeroArm

# ─── 配置 ────────────────────────────────────────────────────
CALIB_DIR = Path("/root/grab_skill/calibration")
CALIB_DIR.mkdir(parents=True, exist_ok=True)

# ArUco 字典 (4x4 标记, 50 个 ID)
ARUCO_DICT = cv2.aruco.DICT_4X4_50
MARKER_LENGTH = 0.05   # 标记实际边长 (米)
MARKER_ID = 0          # 使用的标记 ID

# 标记贴在夹爪上时，标记到 TCP 的偏移 (米)
# ⚠️ 需要手动测量！
MARKER_TO_TCP = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
}


def activate_can():
    subprocess.run("ip link set can1 up type can bitrate 1000000 2>/dev/null", shell=True)
    time.sleep(0.5)


def detect_aruco_marker(rgb: np.ndarray, K: np.ndarray, dist_coeffs=None):
    """
    检测 ArUco 标记，返回标记在相机坐标系下的位姿

    Returns:
        rvec, tvec: 旋转向量和平移向量 (相机→标记)
        或 (None, None)
    """
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, params)

    corners, ids, _ = detector.detectMarkers(rgb)

    if ids is None or MARKER_ID not in ids.flatten():
        return None, None, None

    idx = list(ids.flatten()).index(MARKER_ID)
    marker_corners = corners[idx][0]

    # 估计位姿
    rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
        [marker_corners], MARKER_LENGTH, K, dist_coeffs
    )

    # 画图
    cv2.aruco.drawDetectedMarkers(rgb, corners, ids)
    cv2.drawFrameAxes(rgb, K, dist_coeffs, rvecs[0], tvecs[0], 0.03)

    return rvecs[0].flatten(), tvecs[0].flatten(), marker_corners


def rvec_tvec_to_matrix(rvec, tvec):
    """旋转向量 + 平移 → 4x4 齐次矩阵"""
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.flatten()
    return T


def solve_hand_eye(data_points: list):
    """
    求解 Eye-to-Hand 标定: T_camera_to_base

    data_points: [(joint_angles, rvec, tvec), ...]

    原理:
    - 对于每组数据: T_base_to_marker = FK(joint_angles)
    - 相机观察到: T_camera_to_marker (从 ArUco 检测得到)
    - 关系: T_camera_to_base @ T_base_to_marker = T_camera_to_marker
    - → T_camera_to_marker = T_camera_to_base @ FK(joints)
    - 通过多组数据求解 T_camera_to_base

    简化版 (无 FK): 假设标记贴在固定位置
    使用最小二乘法估计相机位置
    """
    if len(data_points) < 4:
        print(f"❌ 至少需要 4 组数据，当前 {len(data_points)}")
        return None

    # 简化为：标记在零位时，相机到标记的变换即相机到基座的近似
    # 完整版需要正运动学 FK，见 TODO

    print(f"⚠️  完整标定需要正运动学模块 (FK)")
    print(f"  当前版本: 取标记在零位的相机→标记变换作为近似")

    # 找到关节角最接近零的数据点
    best_idx = 0
    best_dist = float("inf")
    for i, (joints, rvec, tvec) in enumerate(data_points):
        dist = sum(abs(j) for j in joints)
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    joints, rvec, tvec = data_points[best_idx]
    T_cam_to_marker = rvec_tvec_to_matrix(rvec, tvec)

    print(f"\n  使用数据点 {best_idx}: joints={[round(j,3) for j in joints]}")
    print(f"  T_camera_to_marker (4x4):")
    print(f"  {np.array2string(T_cam_to_marker, precision=4, suppress_small=True)}")

    return T_cam_to_marker.tolist()


def cmd_setup():
    """设置: 贴标记到夹爪，在零位采集初始参考"""
    print("=" * 60)
    print("  手眼标定 — 第 1 步: 初始设置")
    print("=" * 60)
    print()
    print("请准备:")
    print(f"  1. 打印 ArUco 标记 (ID={MARKER_ID}, 字典=4x4_50)")
    print(f"  2. 把标记贴在夹爪外侧平面")
    print(f"  3. 机械臂上电，确认 CAN 已连接")
    print(f"  4. ⚠️ 标记到 TCP 偏移: {MARKER_TO_TCP}")
    print()

    input("按 Enter 开始...")

    activate_can()

    # 归零
    with NeroArm() as arm:
        arm.go_home()
        joints = arm.get_joint_angles()
        print(f"零位关节角: {[round(j, 4) for j in joints]}")

    # 拍照检测标记
    print("\n拍照检测标记...")
    with StereoCamera(camera_model="gemini_335", enable_depth=True) as cam:
        time.sleep(1.0)
        rgb, depth, K = cam.capture(timeout=5.0)
        if rgb is None or K is None:
            print("❌ 拍照失败")
            return

    rvec, tvec, corners = detect_aruco_marker(rgb, K)
    if rvec is None:
        print("❌ 未检测到标记!")
        print("  请检查: 1) 标记在视野内  2) 光照充足  3) 标记未反光")
        # 保存图片供检查
        cv2.imwrite(str(CALIB_DIR / "setup_debug.jpg"), rgb)
        print(f"  调试图片: {CALIB_DIR}/setup_debug.jpg")
        return

    print(f"  ✅ 检测到标记 ID={MARKER_ID}")
    print(f"  旋转向量: {np.array2string(rvec, precision=4)}")
    print(f"  平移向量: {np.array2string(tvec, precision=4)}")

    # 保存
    cv2.imwrite(str(CALIB_DIR / "setup_marker.jpg"), rgb)
    setup_data = {
        "marker_id": MARKER_ID,
        "marker_length": MARKER_LENGTH,
        "marker_to_tcp": MARKER_TO_TCP,
        "home_joints": joints,
        "rvec": rvec.tolist(),
        "tvec": tvec.tolist(),
    }
    with open(CALIB_DIR / "setup.json", "w") as f:
        json.dump(setup_data, f, indent=2)

    print(f"\n✅ 初始设置完成，数据保存到 {CALIB_DIR}/setup.json")


def cmd_collect():
    """采集: 手动把臂摆到不同姿态，每姿态记录一次"""
    print("=" * 60)
    print("  手眼标定 — 第 2 步: 采集数据")
    print("=" * 60)
    print()
    print("将机械臂摆到 4~6 个不同姿态（标记始终在相机视野内）")
    print("每姿态按 Enter 记录一次，输入 q 结束")
    print()

    # 加载设置
    setup_file = CALIB_DIR / "setup.json"
    if not setup_file.exists():
        print("❌ 请先运行 --setup")
        return
    setup = json.loads(setup_file.read_text())

    activate_can()
    arm = NeroArm()
    arm.connect()
    arm.enable()
    joints = arm.get_joint_angles()
    print(f"当前关节角: {[round(j, 4) for j in joints]}")

    cam = StereoCamera(camera_model="gemini_335", enable_depth=True)
    cam.start()
    time.sleep(1.0)

    data_points = []

    try:
        for i in range(20):
            action = input(f"\n[{i+1}] 调好姿态后按 Enter (q=结束): ")
            if action.strip().lower() == "q":
                break

            # 读关节角
            joints = arm.get_joint_angles()
            print(f"  关节角: {[round(j, 4) for j in joints]}")

            # 拍照
            rgb, _, K = cam.capture(timeout=3.0)
            if rgb is None:
                print("  ❌ 拍照失败")
                continue

            # 检测标记
            rvec, tvec, _ = detect_aruco_marker(rgb, K)
            if rvec is None:
                print("  ❌ 未检测到标记，跳过")
                cv2.imwrite(str(CALIB_DIR / f"fail_{i}.jpg"), rgb)
                continue

            print(f"  ✅ rvec={np.array2string(rvec, precision=3)}")
            print(f"      tvec={np.array2string(tvec, precision=3)}")

            data_points.append({
                "joints": joints,
                "rvec": rvec.tolist(),
                "tvec": tvec.tolist(),
            })
            cv2.imwrite(str(CALIB_DIR / f"collect_{i}.jpg"), rgb)

    finally:
        cam.stop()
        arm.disable()
        arm.disconnect()

    # 保存
    collect_data = {
        "setup": str(setup_file),
        "num_points": len(data_points),
        "points": data_points,
    }
    with open(CALIB_DIR / "collect.json", "w") as f:
        json.dump(collect_data, f, indent=2)

    print(f"\n✅ 采集完成: {len(data_points)} 组数据")


def cmd_solve():
    """求解变换矩阵"""
    print("=" * 60)
    print("  手眼标定 — 第 3 步: 求解 T_camera_to_base")
    print("=" * 60)

    collect_file = CALIB_DIR / "collect.json"
    if not collect_file.exists():
        print("❌ 请先运行 --collect")
        return

    collect = json.loads(collect_file.read_text())
    data = [(p["joints"], np.array(p["rvec"]), np.array(p["tvec"]))
            for p in collect["points"]]

    result = solve_hand_eye(data)
    if result is None:
        return

    calib_result = {
        "description": "T_camera_to_base (camera in robot base frame)",
        "matrix_4x4": result,
        "num_points": collect["num_points"],
    }

    with open(CALIB_DIR / "result.json", "w") as f:
        json.dump(calib_result, f, indent=2)

    print(f"\n✅ 标定完成: {CALIB_DIR}/result.json")

    # 提取简单参数
    T = np.array(result)
    pos = T[:3, 3]
    print(f"\n📐 相机在基座坐标系中的近似位置:")
    print(f"   x={pos[0]:.4f} m")
    print(f"   y={pos[1]:.4f} m")
    print(f"   z={pos[2]:.4f} m")
    print(f"\n⚠️  这是简化结果，建议手动验证")
    print(f"  更新 grab_main.py 中的 HAND_EYE_TRANSFORM")


def cmd_test():
    """验证标定精度"""
    print("=" * 60)
    print("  手眼标定 — 第 4 步: 验证")
    print("=" * 60)

    result_file = CALIB_DIR / "result.json"
    if not result_file.exists():
        print("❌ 请先运行 --solve")
        return

    result = json.loads(result_file.read_text())
    T_cam_to_base = np.array(result["matrix_4x4"])

    activate_can()

    # 拍照 + 检测标记
    with StereoCamera(camera_model="gemini_335", enable_depth=True) as cam:
        time.sleep(1.0)
        rgb, depth, K = cam.capture(timeout=5.0)

    if rgb is None or K is None:
        print("❌ 拍照失败")
        return

    rvec, tvec, _ = detect_aruco_marker(rgb, K)
    if rvec is None:
        print("❌ 未检测到标记")
        return

    T_cam_to_marker = rvec_tvec_to_matrix(rvec, tvec)

    # 验证: T_cam_to_base @ T_base_to_marker = T_cam_to_marker
    # 简化: 标记应在的基座位置 ≈ T_cam_to_base.inv @ T_cam_to_marker
    T_marker_in_base = np.linalg.inv(T_cam_to_base) @ T_cam_to_marker

    print(f"\n标记在基座坐标系下的位置:")
    print(f"  x={T_marker_in_base[0,3]:.3f} m")
    print(f"  y={T_marker_in_base[1,3]:.3f} m")
    print(f"  z={T_marker_in_base[2,3]:.3f} m")
    print(f"\n  目测是否合理? (提示: NERO 基座原点在底板上方约 0.05m)")
    print(f"  ✅ 完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="手眼标定")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--solve", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.setup:
        cmd_setup()
    elif args.collect:
        cmd_collect()
    elif args.solve:
        cmd_solve()
    elif args.test:
        cmd_test()
    else:
        parser.print_help()
        print("\n推荐流程: --setup → --collect → --solve → --test")
