"""端到端测试: 用 grab_skill 自己的 StereoCamera 走完整路径 (自动拉驱动 + 采 RGB+深度)"""
import time
import numpy as np

from camera import StereoCamera

with StereoCamera(camera_model="dabai_dc1", enable_depth=True) as cam:
    time.sleep(2)
    rgb, depth, K = cam.capture(timeout=12.0)
    print("=== 结果 ===")
    print("rgb  :", None if rgb is None else f"{rgb.shape} {rgb.dtype} mean={rgb.mean():.1f}")
    if depth is not None:
        v = depth > 0
        if v.any():
            print(f"depth: {depth.shape} 有效={v.mean()*100:.1f}% 范围={depth[v].min():.3f}~{depth[v].max():.3f}m ✅")
        else:
            print(f"depth: {depth.shape} 全 0 ❌")
    else:
        print("depth: None ❌")
    print("K    :", None if K is None else f"fx={K[0,0]:.0f} fy={K[1,1]:.0f} cx={K[0,2]:.0f} cy={K[1,2]:.0f}")
