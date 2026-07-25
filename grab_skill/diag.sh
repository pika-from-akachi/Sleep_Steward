#!/bin/bash
# 干净启动 (和 camera.py 一模一样的参数) + 日志 + 探针
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
pkill -f 'ros2 launch orbbec_camera' 2>/dev/null
pkill -f component_container 2>/dev/null
sleep 2
rm -f /tmp/cam2.log
setsid bash -c 'source /opt/ros/humble/setup.bash && source /root/OrbbecSDK_ROS2/install/setup.bash && exec ros2 launch orbbec_camera dabai.launch.py camera_name:=camera enable_point_cloud:=false enable_color:=true enable_depth:=true enable_ldp:=false' >/tmp/cam2.log 2>&1 </dev/null &
sleep 16
echo "=== LDP/depth/laser/err ==="
grep -iE 'Setting LDP|stream depth|LDP to|laser|2035|unknown error|Failed' /tmp/cam2.log | head -12
echo "=== camera_info 发布? ==="
ros2 topic list 2>/dev/null | grep camera_info
timeout 4 ros2 topic hz /camera/depth/camera_info 2>&1 | tail -2
echo "=== 深度探针 (启动16s后) ==="
python3 /root/grab_skill/depth_probe.py /camera/depth/image_raw 2 2>&1 | tail -3
