"""任意图像话题探针 — 自动按编码解析, 报告非零率/均值/max。
用法: python3 img_probe.py <topic> [帧数]
"""
import sys
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image

topic = sys.argv[1] if len(sys.argv) > 1 else "/camera/ir/image_raw"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3


class P(Node):
    def __init__(self):
        super().__init__("img_probe")
        q = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                       history=HistoryPolicy.KEEP_LAST, depth=5)
        self.latest = None
        self.create_subscription(Image, topic, self.cb, q)

    def cb(self, m):
        self.latest = m


rclpy.init()
n = P()
print(f"订阅 {topic}, 抓 {N} 帧 (15s 超时)...")
got, last, t0 = 0, None, time.time()
while got < N and time.time() - t0 < 15:
    rclpy.spin_once(n, timeout_sec=0.1)
    m = n.latest
    if m is None or m is last:
        continue
    last = m
    enc = m.encoding
    if enc in ("16UC1", "mono16", "16UC3"):
        a = np.frombuffer(m.data, np.uint16)
        if getattr(m, "is_bigendian", 0):
            a = a.byteswap()
        try:
            a = a.reshape((m.height, m.width))
        except Exception:
            row = m.step // 2
            a = a.reshape((m.height, row))[:, :m.width]
        nz = int((a > 0).sum())
        print(f"  帧{got+1}: {m.width}x{m.height} {enc} 非零={nz}/{a.size}({nz/a.size*100:.1f}%) "
              f"均值={a.mean():.0f} max={int(a.max())}")
    else:
        a = np.frombuffer(m.data, np.uint8)
        print(f"  帧{got+1}: {m.width}x{m.height} {enc} step={m.step} len={len(m.data)} "
              f"均值={a.mean():.1f} 非零={int((a>0).sum())}/{a.size}({(a>0).mean()*100:.1f}%) max={int(a.max())}")
    got += 1
    time.sleep(0.3)

rclpy.shutdown()
print(f"抓到 {got}/{N}")
