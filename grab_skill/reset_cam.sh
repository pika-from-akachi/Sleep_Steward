#!/bin/bash
# 软复位: 停驱动 → usbreset 相机 → 重启驱动 → 报告 2035 是否还报错
source /opt/ros/humble/setup.bash
source /root/OrbbecSDK_ROS2/install/setup.bash
pkill -f 'ros2 launch orbbec_camera' 2>/dev/null
pkill -f component_container 2>/dev/null
sleep 2
LINE=$(lsusb | grep '2bc5:0657' | head -1)
BUS=$(echo "$LINE" | awk '{print $2}')
DEV=$(echo "$LINE" | awk '{print $4}' | tr -d ':')
echo "usbreset /dev/bus/usb/$BUS/$DEV"
usbreset "/dev/bus/usb/$BUS/$DEV" 2>&1 || echo "usbreset FAILED"
sleep 3
rm -f /tmp/orbbec.log
setsid bash -c 'source /opt/ros/humble/setup.bash && source /root/OrbbecSDK_ROS2/install/setup.bash && exec ros2 launch orbbec_camera dabai.launch.py camera_name:=camera enable_point_cloud:=false enable_color:=true enable_depth:=true' >/tmp/orbbec.log 2>&1 </dev/null &
sleep 14
echo "=== 2035 error after reset? ==="
grep -iE '2035|unknown error' /tmp/orbbec.log | head -3
