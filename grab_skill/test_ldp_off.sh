#!/bin/bash
# 关掉 LDP(激光保护) 重启驱动, 看深度是否恢复
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
pkill -f 'ros2 launch orbbec_camera' 2>/dev/null
pkill -f component_container 2>/dev/null
sleep 2
rm -f /tmp/orbbec.log
setsid bash -c 'source /opt/ros/humble/setup.bash && source /root/OrbbecSDK_ROS2/install/setup.bash && exec ros2 launch orbbec_camera dabai.launch.py camera_name:=camera enable_point_cloud:=false enable_color:=true enable_depth:=true enable_ldp:=false' >/tmp/orbbec.log 2>&1 </dev/null &
sleep 14
echo "=== LDP/laser 相关日志 ==="
grep -iE 'LDP|laser|2035|unknown error' /tmp/orbbec.log | head -8
