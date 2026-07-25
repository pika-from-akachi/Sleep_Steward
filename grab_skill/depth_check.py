"""深度相机自检 — 直接打印驱动发布的深度帧统计, 用于排查"深度全是 0"。

修复后这脚本能区分四种情况:
  - depth = None            → 驱动根本没发布深度话题 (launch/USB/enable_depth 问题)
  - 有效像素 0% 连续多帧    → 相机硬件/场景问题 (镜头遮挡、太近太远、IR 故障)
  - 首帧 0% 后续正常        → 预热帧 (已被 camera.py 跳过, 正常)
  - 有效像素 >5% 且范围合理 → 已修复, 深度可用

用法 (在 RDK X5 上):
    source /opt/ros/humble/setup.bash
    source /root/OrbbecSDK_ROS2/install/setup.bash
    python3 depth_check.py                       # 默认 dabai_dc1
    python3 depth_check.py --camera gemini_335   # Gemini 335
"""
import argparse
import time

import numpy as np

from camera import StereoCamera


def main():
    parser = argparse.ArgumentParser(description="深度相机自检")
    parser.add_argument("--camera", "-c", default="dabai_dc1")
    parser.add_argument("--frames", "-n", type=int, default=5)
    parser.add_argument("--no-launch", action="store_true",
                        help="不启动 ros2 launch (假设你已手动在跑)")
    args = parser.parse_args()

    cam = StereoCamera(camera_model=args.camera, enable_depth=True)
    if args.no_launch:
        # 跳过相机自身拉起的 launch, 只做订阅 (用于排查已手动启动的驱动)
        cam._start_depth_ros = lambda: None
        cam.enable_depth = True

    print("=" * 60)
    print(f"  深度自检 | 相机={args.camera} | {args.frames} 帧")
    print("=" * 60)

    cam.start()
    time.sleep(1.0)
    try:
        for i in range(args.frames):
            rgb, depth, K = cam.capture(timeout=5.0)
            print(f"--- 第 {i + 1}/{args.frames} 帧 ---")
            if depth is None:
                print("  ❌ depth = None → 驱动没发深度话题")
                print("     检查: ros2 topic list 里有没有 /camera/depth/image_raw")
                print("     检查: USB 连接、dabai_d1.launch.py 是否 enable_depth")
                continue
            valid = depth > 0.0
            n_valid = int(valid.sum())
            ratio = valid.mean()
            print(f"  shape={depth.shape} dtype={depth.dtype}")
            print(f"  有效像素={n_valid}/{depth.size} ({ratio * 100:.1f}%)")
            if n_valid > 0:
                print(f"  非零范围={depth[valid].min():.3f}~{depth[valid].max():.3f} m"
                      f"  中位={np.median(depth[valid]):.3f} m")
            else:
                print("  ⚠️ 全 0 帧 (TOF 没返回距离: 镜头遮挡/太近/IR 故障?)")
            if K is not None:
                print(f"  K: fx={K[0, 0]:.1f} fy={K[1, 1]:.1f} "
                      f"cx={K[0, 2]:.1f} cy={K[1, 2]:.1f}")
            time.sleep(0.5)
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
