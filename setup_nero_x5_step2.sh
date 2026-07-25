#!/bin/bash
set -e

# Fix GPG key for Tsinghua ROS2 mirror
echo '=== 修复 GPG 密钥 ==='
apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys F42ED6FBAB17C654 2>/dev/null || \
  curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | apt-key add -

# Use Tsinghua mirror
echo "deb [arch=arm64] https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu jammy main" > /etc/apt/sources.list.d/ros2.list
apt update

echo '=== 安装 ROS2 Humble Base ==='
apt install -y ros-humble-ros-base python3-colcon-common-extensions python3-rosdep

echo '=== 系统依赖 ==='
apt install -y ros-humble-moveit* ros-humble-control* \
    ros-humble-joint-trajectory-controller ros-humble-gripper-controllers \
    ros-humble-trajectory-msgs can-utils ethtool python3-pip \
    ros-humble-ros2-control ros-humble-ros2-controllers ros-humble-controller-manager \
    ros-humble-robot-state-publisher ros-humble-joint-state-publisher-gui ros-humble-xacro

rosdep init 2>/dev/null || true

echo '=== pyAgxArm ==='
pip3 install python-can scipy numpy
cd /root
git clone https://github.com/agilexrobotics/pyAgxArm.git 2>&1 | tail -2
cd pyAgxArm && pip3 install .

echo '=== agx_arm_ros ==='
source /opt/ros/humble/setup.bash
mkdir -p /root/agx_arm_ws/src
cd /root/agx_arm_ws/src
git clone -b ros2 --recurse-submodules https://github.com/agilexrobotics/agx_arm_ros.git 2>&1 | tail -2
cd /root/agx_arm_ws
rosdep update
rosdep install -i --from-path src --rosdistro humble -y || true
colcon build --symlink-install 2>&1 | tail -10

echo '=== ~/.bashrc ==='
grep -q 'ROS2 Humble' /root/.bashrc 2>/dev/null || cat >> /root/.bashrc << 'EOF'

# === ROS2 Humble + NERO ===
source /opt/ros/humble/setup.bash
source /root/agx_arm_ws/install/setup.bash 2>/dev/null
export LC_NUMERIC=en_US.UTF-8
EOF

echo '=== 全部完成 ==='
source /opt/ros/humble/setup.bash && ros2 --version
