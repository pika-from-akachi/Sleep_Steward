"""
Orbbec 相机接口 — 基于官方 OrbbecSDK_ROS2 v1.5.15
- DaBai DC1: RGB 走 ROS2 topic, 深度走 ROS2 topic (depth_registration=true 对齐)
- Gemini 335: RGB+深度均走 ROS2 topic

深度对齐说明:
  depth_registration:=true 使 DaBai DC1 将 640x400 深度 warp 到 640x480 彩色帧。
  对齐后的深度发布在 /camera/depth/image_raw (与 color topic 同分辨率)。
  本模块增加多帧时域滤波 (temporal median) 以降低结构光随机噪声 (~2-5mm RMS)。

参考: https://github.com/orbbec/OrbbecSDK_ROS2
"""

import os, time, signal, subprocess, threading
import numpy as np
import cv2

# ─── 根据官方 README 定义的话题 ─────────────────────────

# 官方支持的话题 (README_CN.MD §所有可用主题):
#   /camera/color/image_raw    彩色流
#   /camera/depth/image_raw    深度流 (depth_registration=true 时已对齐到彩色)
#   /camera/ir/image_raw       红外流
#   /camera/depth/camera_info  深度内参 (depth_registration=true 时 = 彩色内参)
#   /camera/color/camera_info  彩色内参

CAMERA_CONFIGS = {
    "dabai_dc1": {
        # DaBai DC1: USB2 结构光相机, launch 文件名是 dabai.launch.py
        "launch_file": "dabai.launch.py",
        "has_color_ros": True,           # 彩色走 ROS topic
        "color_topic": "/camera/color/image_raw",
        "depth_topic": "/camera/depth/image_raw",
        "depth_info_topic": "/camera/depth/camera_info",
        "color_info_topic": "/camera/color/camera_info",
    },
    "gemini_335": {
        "launch_file": "gemini_330_series.launch.py",
        "has_color_ros": True,           # RGB 走 ROS2
        "depth_topic": "/camera/aligned_depth_to_color/image_raw",
        "depth_info_topic": "/camera/aligned_depth_to_color/camera_info",
        "color_info_topic": "/camera/color/camera_info",
    },
}

ORBBEC_WS = "/root/OrbbecSDK_ROS2"

# 默认内参: 实测 DaBai DC1 depth_registration=true 时 /camera/depth/camera_info
# fx=489.82 fy=489.82 cx=322.91 cy=210.87  (640x480 彩色光学系)
DEFAULT_K_REGISTERED = np.array(
    [[489.82, 0, 322.91],
     [0, 489.82, 210.87],
     [0, 0, 1]], dtype=np.float32
)


class StereoCamera:
    """RGB+深度相机：RGB 用 ROS2，深度用 ROS2 (depth_registration 对齐)"""

    def __init__(self, camera_model="dabai_dc1", camera_ns="camera",
                 enable_depth=False):
        self.model = camera_model
        self.cfg = CAMERA_CONFIGS.get(camera_model, CAMERA_CONFIGS["dabai_dc1"])
        self.camera_ns = camera_ns
        self.enable_depth = enable_depth
        self._launch_proc = None
        self._rgb_cap = None
        self._depth_node = None
        self._executor = None

    # ─── 启动 ────────────────────────────────────────────

    def start(self):
        """打开 RGB + 启动深度 ROS2 驱动"""
        subprocess.run("killall -9 ros2 component_container 2>/dev/null", shell=True)
        time.sleep(0.5)

        # RGB: UVC (旧版 DaBai) 或 ROS2 (当前 DaBai/Gemini)
        if not self.cfg["has_color_ros"]:
            self._start_rgb_uvc()
        else:
            self._start_rgb_ros()

        # ROS 驱动: 只要用了深度 或 ROS彩色, 就得拉起 orbbec 驱动 (它同时发 color/depth/ir)
        if self.enable_depth or self.cfg["has_color_ros"]:
            self._start_depth_ros()

    def _start_rgb_uvc(self):
        """DaBai 的 UVC RGB: OpenCV 直读 (旧方式, 不推荐)"""
        self._rgb_cap = cv2.VideoCapture(0)
        self._rgb_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._rgb_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self._rgb_cap.isOpened():
            raise RuntimeError("无法打开 /dev/video0")
        # 丢弃预热帧
        for _ in range(5):
            self._rgb_cap.read()
        ret, _ = self._rgb_cap.read()
        if not ret:
            raise RuntimeError("UVC RGB 读取失败，请重新插拔 USB")
        print(f"[Camera] RGB: UVC /dev/video0 640x480 ✅")

    def _start_rgb_ros(self):
        """RGB 走 ROS2 topic，在 capture 时订阅"""
        print("[Camera] RGB: 将通过 ROS2 topic 获取")

    def _start_depth_ros(self):
        """启动 Orbbec ROS2 驱动"""
        setup = os.path.join(ORBBEC_WS, "install", "setup.bash")
        if not os.path.isfile(setup):
            print(f"[Depth] {setup} 不存在，跳过")
            self.enable_depth = False
            return

        enable_color = "true" if self.cfg["has_color_ros"] else "false"
        enable_depth = "true" if self.enable_depth else "false"
        cmd = (
            f"bash -c 'source {setup} && "
            f"ros2 launch orbbec_camera {self.cfg['launch_file']} "
            f"camera_name:={self.camera_ns} "
            f"enable_point_cloud:=false "
            f"enable_color:={enable_color} "
            f"enable_depth:={enable_depth} "
            f"enable_ldp:=false "   # 关 LDP(激光保护): 近距场景它会关激光 → 深度全 0
            f"depth_registration:=true'"   # 深度注册到彩色 (DaBai用此参数对齐)
        )
        self._launch_proc = subprocess.Popen(
            cmd, shell=True, executable="/bin/bash",
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        time.sleep(15)   # DC1 从启动到稳定出有效深度帧约需 14~16s, 留足预热
        print(f"[Depth] ROS2 驱动已启动: {self.cfg['launch_file']} (depth_registration=true)")

    # ─── 捕获 (单帧) ─────────────────────────────────────

    def capture(self, timeout=3.0):
        """捕获一帧 RGB + 深度 (单帧, 不滤波)

        Returns:
            (rgb_bgr, depth_meters, K_3x3)
            rgb: BGR uint8 (H,W,3)
            depth: float32米 或 None
            K: 3x3 内参矩阵
        """
        rgb = self._capture_rgb()
        if rgb is None:
            return None, None, None

        depth, K = None, None
        if self.enable_depth:
            depth, K = self._capture_depth(timeout)

        if K is None:
            # 使用实测的注册后内参 (depth_registration=true, 640x480 彩色光学系)
            print("[Camera] K 使用实测默认值 (depth_registration 640x480)")
            K = DEFAULT_K_REGISTERED.copy()

        return rgb, depth, K

    # ─── 捕获 (多帧时域滤波) ──────────────────────────────

    def capture_filtered(self, num_frames=5, timeout=5.0):
        """捕获 RGB + 多帧时域滤波深度 (减少结构光随机噪声)

        采集 num_frames 帧深度, 逐像素取 median → 有效降低 2-5mm 的时域噪声。
        RGB 取第一帧, 深度取多帧 median。

        Args:
            num_frames: 用于时域滤波的深度帧数 (3~7 推荐, 越大噪声越低但延迟越高)
            timeout: 总超时时间 (秒)

        Returns:
            (rgb_bgr, depth_meters_filtered, K_3x3)
        """
        import rclpy
        from sensor_msgs.msg import Image, CameraInfo
        if not rclpy.ok():
            rclpy.init(args=[])

        # ── 同时订阅 color + depth + info ──
        color_node = _QuickSub(self.cfg["color_topic"], msg_type="Image",
                               timeout=timeout)
        depth_node = _QuickSub(self.cfg["depth_topic"], msg_type="Image",
                               timeout=timeout)
        info_node = _QuickSub(self.cfg["depth_info_topic"], msg_type="CameraInfo",
                              timeout=min(timeout, 4.0))

        # 内参: 拿到一条即可
        info_msg = info_node.get()
        if info_msg is not None:
            K = np.array(info_msg.k).reshape(3, 3)
            print(f"[Depth] K from camera_info: fx={K[0,0]:.1f} fy={K[1,1]:.1f} "
                  f"cx={K[0,2]:.1f} cy={K[1,2]:.1f}")
        else:
            print("[Depth] ⚠️ 未收到 camera_info, K 使用实测默认值")
            K = DEFAULT_K_REGISTERED.copy()

        # 收集多帧深度用于时域滤波
        depth_frames = []
        depth_meta = None
        deadline = time.time() + timeout

        print(f"[Depth] 收集 {num_frames} 帧用于时域滤波...")
        while len(depth_frames) < num_frames and time.time() < deadline:
            depth_node.spin_for(0.1)
            msg = depth_node.latest
            if msg is None:
                continue
            depth = _depth_msg_to_meters(msg)
            if depth is None:
                continue
            valid_ratio = (depth > 0.0).sum() / depth.size
            if valid_ratio < 0.05:
                continue  # 跳过全 0 / 预热帧
            depth_frames.append(depth)
            if depth_meta is None:
                depth_meta = (msg.width, msg.height, msg.encoding)
            print(f"  [{len(depth_frames)}/{num_frames}] "
                  f"{msg.width}x{msg.height} 有效={valid_ratio*100:.1f}%", end="")
            if len(depth_frames) >= num_frames:
                print()
                break
            print()

        # ── 获取 RGB (取最新一帧, 与最后帧深度接近同步) ──
        color_node.spin_for(0.3)
        ros_img = color_node.latest
        rgb = _ros_img_to_cv2(ros_img) if ros_img is not None else None

        # 清理
        color_node.destroy_node()
        depth_node.destroy_node()
        info_node.destroy_node()

        # ── 时域 median 滤波 ──
        if len(depth_frames) >= 2:
            stack = np.stack(depth_frames, axis=0)      # (N, H, W)
            depth_filtered = np.median(stack, axis=0).astype(np.float32)
            # 保留原始的有效性: 超过半数帧有值的像素才保留
            valid_mask = (stack > 0.0).sum(axis=0) > len(depth_frames) // 2
            depth_filtered[~valid_mask] = 0.0
            print(f"[Depth] 时域滤波完成: {len(depth_frames)} 帧 → per-pixel median")
            print(f"        有效像素: {(depth_filtered > 0).sum()}/{depth_filtered.size}")
        elif len(depth_frames) == 1:
            depth_filtered = depth_frames[0]
            print(f"[Depth] ⚠️ 只收集到 1 帧, 无法滤波 (尝试增加 timeout)")
        else:
            depth_filtered = None
            print("[Depth] ❌ 未收集到有效深度帧!")

        # 打印诊断
        if depth_filtered is not None and (depth_filtered > 0).sum() > 0:
            valid = depth_filtered[depth_filtered > 0]
            print(f"[Depth] 范围={valid.min():.3f}~{valid.max():.3f}m "
                  f"中位={np.median(valid):.3f}m")

        return rgb, depth_filtered, K

    # ─── 内部方法 ────────────────────────────────────────

    def _capture_rgb(self):
        """获取 RGB 帧"""
        if self._rgb_cap is not None:
            # UVC 模式
            ret, frame = self._rgb_cap.read()
            if not ret:
                # 重连
                self._rgb_cap.release()
                time.sleep(0.3)
                self._rgb_cap = cv2.VideoCapture(0)
                self._rgb_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self._rgb_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                for _ in range(3):
                    self._rgb_cap.read()
                ret, frame = self._rgb_cap.read()
            if not ret or frame is None:
                print("[Camera] RGB 读取失败")
                return None
            return frame

        # ROS2 模式: 从 topic 读
        import rclpy
        from sensor_msgs.msg import Image
        if not rclpy.ok():
            rclpy.init(args=[])
        node = _QuickSub(self.cfg.get("color_topic", "/camera/color/image_raw"), timeout=3.0)
        ros_img = node.get()
        node.destroy_node()
        if ros_img is not None:
            return _ros_img_to_cv2(ros_img)
        return None

    def _capture_depth(self, timeout):
        """获取深度帧 + 内参

        在 timeout 内持续自旋取最新帧, 跳过全 0 预热帧。
        """
        import rclpy
        from sensor_msgs.msg import Image, CameraInfo
        if not rclpy.ok():
            rclpy.init(args=[])

        depth_node = _QuickSub(self.cfg["depth_topic"], msg_type="Image", timeout=timeout)
        info_node = _QuickSub(self.cfg["depth_info_topic"], msg_type="CameraInfo",
                              timeout=min(timeout, 4.0))

        # 内参: 拿到一条即可
        info_msg = info_node.get()

        # 深度: 在 timeout 内持续取最新帧, 跳过全 0 预热帧
        deadline = time.time() + timeout
        depth = None
        while time.time() < deadline:
            depth_node.spin_for(0.2)
            msg = depth_node.latest
            if msg is None:
                continue
            depth = _depth_msg_to_meters(msg)
            if depth is None:                 # 编码/尺寸无法解析, 不死循环
                break
            valid = int(np.count_nonzero(depth > 0.0))
            ratio = valid / depth.size
            vmin = float(depth[depth > 0.0].min()) if valid else 0.0
            vmax = float(depth.max())
            print(f"[Depth] {msg.width}x{msg.height} enc={msg.encoding} "
                  f"有效={ratio*100:.1f}% ({valid}/{depth.size}) "
                  f"范围={vmin:.3f}~{vmax:.3f}m")
            if ratio >= 0.05:                 # ≥5% 像素有效 → 认为是真深度帧
                break

        depth_node.destroy_node()
        info_node.destroy_node()

        K = None
        if info_msg is not None:
            K = np.array(info_msg.k).reshape(3, 3)
        else:
            print("[Depth] ⚠️ 未收到 camera_info, K 使用实测默认值")

        return depth, K

    # ─── 诊断: 保存 RGB-D 叠加图 (检查对齐质量) ────────────

    def save_alignment_check(self, rgb, depth, filepath="/tmp/depth_alignment.png"):
        """将深度叠加到 RGB 上, 保存为彩色叠加图, 用于目视检查对齐质量。

        红=近, 蓝=远, 黑色=无深度。在 RGB 物体边缘区域如果出现大量红色
        (深度缺失) 说明对齐有问题。
        """
        if rgb is None or depth is None:
            print("[AlignCheck] rgb/depth 不可用, 跳过")
            return

        h, w = rgb.shape[:2]
        dh, dw = depth.shape[:2]

        # 如果尺寸不一致, 缩放到一致
        if (dh, dw) != (h, w):
            depth_resized = cv2.resize(depth, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            depth_resized = depth

        # 归一化深度到 0-255
        valid = depth_resized > 0
        d_norm = np.zeros_like(depth_resized)
        if valid.sum() > 0:
            d_min, d_max = depth_resized[valid].min(), depth_resized[valid].max()
            if d_max > d_min:
                d_norm[valid] = (depth_resized[valid] - d_min) / (d_max - d_min) * 255

        # JET colormap on depth
        depth_color = cv2.applyColorMap(d_norm.astype(np.uint8), cv2.COLORMAP_JET)
        depth_color[~valid] = 0

        # 50% 叠加
        overlay = cv2.addWeighted(rgb, 0.5, depth_color, 0.5, 0)
        cv2.imwrite(filepath, overlay)
        print(f"[AlignCheck] RGB-D 叠加图保存到 {filepath}")

    # ─── 停止 ────────────────────────────────────────────

    def stop(self):
        if self._rgb_cap:
            self._rgb_cap.release()
        if self._launch_proc and self._launch_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._launch_proc.pid), signal.SIGTERM)
                self._launch_proc.wait(timeout=3)
            except Exception:
                self._launch_proc.kill()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


# ─── 辅助: 快速订阅者 ──────────────────────────────────

class _QuickSub:
    """订阅一个 topic, 始终保留"最新"一条消息 (而非第一条)。

    传感器首帧常为预热全 0 帧, 锁定首帧会一直拿到 0; 改为保留最新, 配合
    _capture_depth 的有效性校验即可跳过预热帧。
    """

    def __init__(self, topic, msg_type="Image", timeout=3.0, transient_local=False):
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import Image, CameraInfo
        try:
            from rclpy.qos import (QoSProfile, ReliabilityPolicy,
                                   HistoryPolicy, DurabilityPolicy)
            qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=5,
                durability=(DurabilityPolicy.TRANSIENT_LOCAL if transient_local
                            else DurabilityPolicy.VOLATILE),
            )
        except Exception:
            qos = 10

        self._msg = None
        self._lock = threading.Lock()
        self._timeout = timeout

        node_cls = type("_N", (Node,), {})
        self._node = node_cls(f"_qs_{topic.replace('/', '_')}")

        MsgType = Image if msg_type == "Image" else CameraInfo
        self._node.create_subscription(MsgType, topic, self._cb, qos)

    def _cb(self, msg):
        with self._lock:
            self._msg = msg          # 覆盖 → 始终保留最新

    @property
    def latest(self):
        with self._lock:
            return self._msg

    def spin_for(self, seconds):
        """自旋 seconds 秒, 期间 callback 持续刷新 self._msg"""
        import rclpy
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self._node, timeout_sec=0.05)

    def get(self):
        """阻塞等到第一条消息到达 (或超时), 返回最新消息"""
        import rclpy
        start = time.time()
        while time.time() - start < self._timeout:
            rclpy.spin_once(self._node, timeout_sec=0.1)
            with self._lock:
                if self._msg is not None:
                    return self._msg
        return None

    def destroy_node(self):
        self._node.destroy_node()


def _depth_msg_to_meters(msg):
    """sensor_msgs/Image (Orbbec 深度, 16UC1 / mono16, 单位 mm) → float32 米

    处理三个常见坑:
      1) 大端帧 (is_bigendian=1) 需要 byteswap, 否则深度错乱
      2) 行填充 (step > width*2), 直接 reshape 会报错, 需按 step 取前 width 列
      3) 编码非预期时给出提示而非崩溃
    """
    h, w = msg.height, msg.width
    enc = getattr(msg, "encoding", "")
    if enc not in ("16UC1", "mono16"):
        print(f"[Depth] ⚠️ 编码为 {enc!r} (预期 16UC1/mono16), 仍按 uint16 尝试")

    try:
        buf = np.frombuffer(msg.data, dtype=np.uint16)
        if getattr(msg, "is_bigendian", 0):
            buf = buf.byteswap()                    # 大端字节 → 正确数值
        row_u16 = msg.step // 2                     # 每行 uint16 个数 (含尾部填充)
        if row_u16 != w:
            buf = buf.reshape((h, row_u16))[:, :w]  # 去掉行尾填充
        else:
            buf = buf.reshape((h, w))
    except Exception as e:
        print(f"[Depth] 深度解析失败 (h={h} w={w} step={msg.step} len={len(msg.data)}): {e}")
        return None

    return np.ascontiguousarray(buf).astype(np.float32) * 0.001


def _ros_img_to_cv2(msg):
    """ROS2 Image → numpy BGR"""
    encoding = msg.encoding
    h, w = msg.height, msg.width
    if encoding in ("mono16", "16UC1"):
        return np.frombuffer(msg.data, dtype=np.uint16).reshape((h, w))
    if encoding in ("mono8", "8UC1"):
        return np.frombuffer(msg.data, dtype=np.uint8).reshape((h, w))
    if encoding == "bgr8":
        return np.frombuffer(msg.data, dtype=np.uint8).reshape((h, w, 3))
    if encoding == "rgb8":
        img = np.frombuffer(msg.data, dtype=np.uint8).reshape((h, w, 3))
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return np.frombuffer(msg.data, dtype=np.uint8).reshape((h, w))
