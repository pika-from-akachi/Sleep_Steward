"""解析 handeye_calibration_ros 标定结果, 更新 transforms.py 的 CAM_MOUNT。

标定输出格式:
{
    "position": [x, y, z],        # T_flange_cam 的平移 (相机在 flange/TCP 系下)
    "orientation": [x, y, z, w],  # quaternion (xyzw)
    "rpy": [[r, p, y]]            # 对应的 RPY
}

将结果写入 transforms.py, 更新 CAM_MOUNT 字典。

用法:
    python3 parse_calib_result.py                         # 查找最新的标定结果
    python3 parse_calib_result.py <calib_json_path>       # 指定 JSON 文件
"""
import json
import os
import sys
import glob
import numpy as np
np.float = float; np.int = int; np.bool = bool  # compat numpy>=1.24
import tf_transformations as tt
from pathlib import Path

CALIB_DIR = Path("/root/grab_skill/calibration")
TRANSFORMS_FILE = Path("/root/grab_skill/transforms.py")


def quaternion_to_rpy(q_xyzw):
    """四元数 [x,y,z,w] → [roll, pitch, yaw]
    使用 sxyz 约定: R = Rz(yaw)·Ry(pitch)·Rx(roll)"""
    return list(tt.euler_from_quaternion(q_xyzw, axes='sxyz'))


def rpy_to_quaternion(rpy):
    """[roll, pitch, yaw] → [x, y, z, w] (sxyz 约定)"""
    return list(tt.quaternion_from_euler(rpy[0], rpy[1], rpy[2], axes='sxyz'))


def find_latest_result():
    """查找最新的标定结果 JSON 文件"""
    pattern = str(CALIB_DIR / "*_calibration.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return files[-1]


def parse_and_convert(result_json_path):
    """解析标定 JSON, 返回 CAM_MOUNT 格式"""
    with open(result_json_path) as f:
        data = json.load(f)

    pos = data["position"]       # [x, y, z] — 相机在 flange 系下的位置
    quat = data["orientation"]   # [x, y, z, w] — 相机在 flange 系下的姿态
    rpy = quaternion_to_rpy(quat)

    cam_mount = {
        "xyz": [round(v, 4) for v in pos],
        "rpy": [round(v, 4) for v in rpy],
    }

    print("=" * 55)
    print("  手眼标定结果 → CAM_MOUNT")
    print("=" * 55)
    print(f"\n  来源: {os.path.basename(result_json_path)}")
    print(f"\n  T_flange_cam (相机在 flange/TCP 系下的安装变换):")
    print(f"    xyz (m):  {cam_mount['xyz']}")
    print(f"    rpy (rad): {cam_mount['rpy']}")

    # 额外打印四元数
    print(f"\n  quaternion (xyzw): {[round(v, 6) for v in quat]}")

    # 计算欧氏距离
    dist = np.linalg.norm(pos)
    print(f"\n  相机距 flange 原点: {dist:.4f} m")

    return cam_mount


def update_transforms_py(cam_mount):
    """更新 transforms.py 中的 CAM_MOUNT"""
    if not TRANSFORMS_FILE.exists():
        print(f"\n❌ 找不到 {TRANSFORMS_FILE}")
        return False

    content = TRANSFORMS_FILE.read_text()
    lines = content.splitlines()
    new_lines = []
    in_cam_mount = False
    xyz_done = False
    rpy_done = False

    for i, line in enumerate(lines):
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
        TRANSFORMS_FILE.write_text("\n".join(new_lines) + "\n")
        print(f"\n✅ 已更新 {TRANSFORMS_FILE}")
        return True
    else:
        print(f"\n❌ 未能在 transforms.py 中找到 CAM_MOUNT (xyz={xyz_done}, rpy={rpy_done})")
        print("   请手动更新 CAM_MOUNT:")
        print(f'   "xyz": {cam_mount["xyz"]},')
        print(f'   "rpy": {cam_mount["rpy"]},')
        return False


def main():
    result_path = None

    if len(sys.argv) > 1:
        result_path = sys.argv[1]
    else:
        result_path = find_latest_result()

    if result_path is None:
        print("❌ 未找到标定结果 JSON 文件")
        print(f"   请先运行 handeye_calibration, 结果保存在 {CALIB_DIR}/")
        print("   或手动指定: python3 parse_calib_result.py <path/to/calibration.json>")
        sys.exit(1)

    if not os.path.exists(result_path):
        print(f"❌ 文件不存在: {result_path}")
        sys.exit(1)

    cam_mount = parse_and_convert(result_path)
    update_transforms_py(cam_mount)

    print("\n" + "=" * 55)
    print("  下一步: 运行验证")
    print(f"  python3 {CALIB_DIR.parent}/calibrate.py --test")
    print("=" * 55)


if __name__ == "__main__":
    main()
