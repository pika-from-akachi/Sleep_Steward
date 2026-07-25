"""cv2.aruco 标记检测节点: 订阅 /camera/color/image_raw + camera_info,
检测 DICT_5X5_50 / ID0 (size=0.1m), 估计位姿, 发 /aruco_single/pose (PoseStamped, 相机光学系)。
供 handeye_calibration 读。opencv 5.x 用 ArucoDetector API。"""
import numpy as np
np.float = float  # 兼容 tf_transformations 等老库 (np.float 在 numpy>=1.24 移除)
np.int = int
np.bool = bool
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion
import cv2
import tf_transformations as tt

MARKER_ID = 0
MARKER_SIZE = 0.15                         # 米 (黑方块边长, 与打印一致)
DICT = cv2.aruco.DICT_5X5_50


def _to4x4(R):
    M = np.eye(4); M[:3, :3] = R; return M


class ArucoDet(Node):
    def __init__(self):
        super().__init__("aruco_detect")
        self.K = None; self.dist = None
        dic = cv2.aruco.getPredefinedDictionary(DICT)
        self.detector = cv2.aruco.ArucoDetector(dic, cv2.aruco.DetectorParameters())
        s = MARKER_SIZE
        self.obj = np.array([[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0]], dtype=np.float32)
        self.pub = self.create_publisher(PoseStamped, "/aruco_single/pose", 10)
        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                         history=HistoryPolicy.KEEP_LAST, depth=1)
        self.create_subscription(Image, "/camera/color/image_raw", self.on_image, qos)
        self.create_subscription(CameraInfo, "/camera/color/camera_info", self.on_info, qos)
        self.get_logger().info(f"aruco_detect 待命: DICT_5X5_50 ID={MARKER_ID} size={MARKER_SIZE}m")

    def on_info(self, msg):
        if self.K is None:
            self.K = np.array(msg.k, dtype=np.float64).reshape(3, 3)
            self.dist = np.array(msg.d, dtype=np.float64).reshape(-1)
            self.get_logger().info(f"内参已读 fx={self.K[0,0]:.0f} fy={self.K[1,1]:.0f}")

    def on_image(self, msg):
        if self.K is None:
            return
        nch = 1 if msg.encoding in ('mono8', '8UC1') else 3
        img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, nch)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if msg.encoding.startswith('rgb') else \
               (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if msg.encoding == 'bgr8' else img)
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is None:
            return
        for i, mid in enumerate(ids.flatten()):
            if mid == MARKER_ID:
                ok, rvec, tvec = cv2.solvePnP(self.obj, corners[i], self.K, self.dist)
                if ok:
                    R, _ = cv2.Rodrigues(rvec)
                    q = tt.quaternion_from_matrix(_to4x4(R))
                    t = tvec.flatten()
                    ps = PoseStamped()
                    ps.header.stamp = self.get_clock().now().to_msg()
                    ps.header.frame_id = "camera_color_optical_frame"
                    ps.pose = Pose(position=Point(x=float(t[0]), y=float(t[1]), z=float(t[2])),
                                   orientation=Quaternion(x=float(q[0]), y=float(q[1]),
                                                          z=float(q[2]), w=float(q[3])))
                    self.pub.publish(ps)
                    self.get_logger().info(
                        f"看到 ID{MARKER_ID} t=[{t[0]:.3f},{t[1]:.3f},{t[2]:.3f}]",
                        throttle_duration_sec=1.0)
                break


def main():
    rclpy.init()
    rclpy.spin(ArucoDet())


if __name__ == "__main__":
    main()
