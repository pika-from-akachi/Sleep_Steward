#!/bin/bash
# 重启 Orbbec 驱动并把日志留到 /tmp/orbbec.log
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
pkill -f 'ros2 launch orbbec_camera' 2>/dev/null
pkill -f component_container 2>/dev/null
sleep 2
rm -f /tmp/orbbec.log
setsid bash -c 'source /opt/ros/humble/setup.bash && source /root/OrbbecSDK_ROS2/install/setup.bash && exec ros2 launch orbbec_camera dabai.launch.py camera_name:=camera enable_point_cloud:=false enable_color:=true enable_depth:=true' >/tmp/orbbec.log 2>&1 </dev/null &
sleep 14
echo "started pid: $(pgrep -f 'ros2 launch orbbec' | head -1)"
echo "log lines: $(wc -l < /tmp/orbbec.log)"
