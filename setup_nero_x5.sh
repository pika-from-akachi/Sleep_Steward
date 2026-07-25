#!/bin/bash
set -e

# ===== ROS2 Humble =====
echo '=== 添加 ROS2 源 ==='
apt update -qq
apt install -y -qq curl software-properties-common gnupg lsb-release
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" > /etc/apt/sources.list.d/ros2.list
apt update -qq

echo '=== 安装 ROS2 Humble Base ==='
apt install -y ros-humble-ros-base python3-colcon-common-extensions python3-rosdep

echo '=== 系统依赖 ==='
apt install -y can-utils ethtool python3-pip \
    ros-humble-ros2-control ros-humble-ros2-controllers ros-humble-controller-manager \
    ros-humble-robot-state-publisher ros-humble-joint-state-publisher-gui ros-humble-xacro \
    ros-humble-moveit* ros-humble-control* \
    ros-humble-joint-trajectory-controller ros-humble-gripper-controllers ros-humble-trajectory-msgs

rosdep init 2>/dev/null || true

echo '=== pyAgxArm ==='
pip3 install python-can scipy numpy
cd /root
git clone https://github.com/agilexrobotics/pyAgxArm.git
cd pyAgxArm && pip3 install .

echo '=== agx_arm_ros ==='
source /opt/ros/humble/setup.bash
mkdir -p /root/agx_arm_ws/src
cd /root/agx_arm_ws/src
git clone -b ros2 --recurse-submodules https://github.com/agilexrobotics/agx_arm_ros.git
cd /root/agx_arm_ws
rosdep update
rosdep install -i --from-path src --rosdistro humble -y || true
colcon build --symlink-install

echo '=== ~/.bashrc ==='
grep -q 'ROS2 Humble' /root/.bashrc 2>/dev/null || cat >> /root/.bashrc << 'EOF'

# === ROS2 Humble + NERO ===
source /opt/ros/humble/setup.bash
source /root/agx_arm_ws/install/setup.bash 2>/dev/null
export LC_NUMERIC=en_US.UTF-8
EOF

echo '=== 部署完成 ==='
