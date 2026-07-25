"""Tracer 底盘测试 (按官方手册 V2.0.3 协议, 准确版)。

协议:
  - 模式切换 0x421 [0x01] (必须先发, 否则底盘待机不响应)
  - 运动控制 0x111: byte0-1 线速度(int16 mm/s ±1800),
                    byte2-3 角速度(int16 0.001rad/s ±1000),
                    byte4-7 保留0, 无CRC
  - 控制周期 ≤500ms (否则底盘超时停, 建议 20ms=50Hz)

用法: python3 tracer_test.py [v_m/s] [w_rad/s] [duration秒]
      python3 tracer_test.py              # v=0.05 前进 3秒
      python3 tracer_test.py 0 0.3        # 原地转
"""
import sys, time, os, struct, subprocess
import can

def cmd_motion(v_mps, w_radps):
    # 手册: 0x111 线速度 signed int16 单位 mm/s (±1800), 角速度 int16 单位 0.001rad/s (±1000)
    # 报文 MOTOROLA 格式 = 大端 (byte0高八位, byte1低八位)
    v_mm = int(max(-1800, min(1800, v_mps * 1000)))        # mm/s
    w_mrad = int(max(-1000, min(1000, w_radps * 1000)))    # 0.001 rad/s
    d = bytearray(8)
    # 大端 pack (MOTOROLA): byte0=高位, byte1=低位
    d[0] = (v_mm >> 8) & 0xFF;  d[1] = v_mm & 0xFF
    d[2] = (w_mrad >> 8) & 0xFF; d[3] = w_mrad & 0xFF
    return can.Message(arbitration_id=0x111, data=list(d), is_extended_id=False)

def set_cmd_mode():
    return can.Message(arbitration_id=0x421, data=[0x01], is_extended_id=False)

def clear_errors():
    """0x441 [0x00] 清除急停/所有错误 (手册表3.8)"""
    return can.Message(arbitration_id=0x441, data=[0x00], is_extended_id=False)

v = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
w = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

os.system('modprobe gs_usb 2>/dev/null')   # 板子重启后要加载 gs_usb 模块
time.sleep(1)

# 自动找底盘: 扫描 can0/can2, up 后看哪个有 0x211 (USB 重插接口名会变)
def find_chassis_if():
    for cif in ['can0', 'can2']:
        os.system(f'ip link set {cif} down 2>/dev/null')
        os.system(f'ip link set {cif} up type can bitrate 500000 2>/dev/null')
        time.sleep(0.3)
        r = subprocess.run(f'timeout 0.5 candump {cif} 2>/dev/null | grep -c " 211 "',
                           shell=True, capture_output=True, text=True)
        if int(r.stdout.strip() or '0') > 0:
            return cif
    return None

CAN_IF = find_chassis_if()
if CAN_IF is None:
    CAN_IF = 'can0'   # 没找到有数据的, 默认 can0
    os.system(f'ip link set {CAN_IF} up type can bitrate 500000 2>/dev/null')
    time.sleep(0.3)
    print(f"⚠️  没找到有底盘数据的接口 (can0/can2 都0帧)! 默认用 {CAN_IF}")
    print(f"    检查: 底盘上电? CAN线接好? H/L没反?")
else:
    print(f"✅ 底盘接口: {CAN_IF}")
bus = can.interface.Bus(channel=CAN_IF, interface='socketcan')

print("→ 清除急停/错误 (0x441) + 切 CAN 指令模式 (0x421)")
for _ in range(5):
    bus.send(clear_errors())   # 0x441 清急停/错误
    time.sleep(0.02)
    bus.send(set_cmd_mode())   # 0x421 切指令控制模式
    time.sleep(0.05)

print(f"⚠️  运动 v={v} m/s, w={w} rad/s, {dur}秒! 3秒倒计时...")
for i in range(3, 0, -1):
    print(f"   {i}..."); time.sleep(1)

print(f"→ 前进 (周期 20ms)")
t0 = time.time()
while time.time() - t0 < dur:
    bus.send(cmd_motion(v, w))
    time.sleep(0.02)

print("→ 停止")
t0 = time.time()
while time.time() - t0 < 1.0:
    bus.send(cmd_motion(0.0, 0.0))
    time.sleep(0.02)

print("\n→ 读底盘反馈 2秒:")
t0 = time.time()
seen = {}
while time.time() - t0 < 2.0:
    m = bus.recv(timeout=0.1)
    if m:
        seen[hex(m.arbitration_id)] = list(m.data)
for cid, d in seen.items():
    if cid in ('0x211', '0x221', '0x311'):
        print(f"  {cid}: {d}")
if not seen:
    print("  (无反馈 — CAN 不通, 检查 CAN_H/CAN_L 接线)")

print("\n✅ 完成")
