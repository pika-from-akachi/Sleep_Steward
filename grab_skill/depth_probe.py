"""独立深度探针 — 直接订阅"已在运行"的驱动发的深度话题, 打印每帧真实统计。
不依赖 camera.py、不启动/重启任何驱动、不碰 UVC。用于定位:
  - 驱动到底发的是不是 0
  - 编码/字节序/step 是否如预期

用法: python3 depth_probe.py [/camera/depth/image_raw] [帧数]
"""
import sys
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image

topic = sys.argv[1] if len(sys.argv) > 1 else "/camera/depth/image_raw"
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 6


class Probe(Node):
    def __init__(self):
        super().__init__("depth_probe")
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self.latest = None
        self.create_subscription(Image, topic, self._cb, qos)

    def _cb(self, m):
        self.latest = m


rclpy.init()
n = Probe()
print(f"订阅 {topic}, 最多抓 {frames} 帧 (30s 超时)...")
got = 0
t0 = time.time()
last = None
while got < frames and time.time() - t0 < 30:
    rclpy.spin_once(n, timeout_sec=0.1)
    m = n.latest
    if m is None or m is last:
        print(".", end="", flush=True)
        time.sleep(0.05)
        continue
    last = m
    raw = np.frombuffer(m.data, dtype=np.uint16)
    if getattr(m, "is_bigendian", 0):
        raw = raw.byteswap()
    row = m.step // 2
    try:
        img = raw.reshape((m.height, row))[:, :m.width] if row != m.width else raw.reshape((m.height, m.width))
    except Exception as e:
        print(f"\n帧{got+1}: reshape 失败 h={m.height} w={m.width} step={m.step} len={len(m.data)}: {e}")
        got += 1
        continue
    nz = int((img > 0).sum())
    extra = f" 非零范围={int(img[img>0].min())}~{int(img[img>0].max())}mm" if nz else ""
    print(f"\n帧{got+1}: {m.width}x{m.height} enc={m.encoding} bigendian={m.is_bigendian} "
          f"step={m.step} len={len(m.data)} -> 非零={nz}/{img.size}({nz/img.size*100:.1f}%) "
          f"max={int(img.max())}mm{extra}")
    got += 1
    time.sleep(0.3)

rclpy.shutdown()
print(f"\n抓到 {got}/{frames} 帧")
