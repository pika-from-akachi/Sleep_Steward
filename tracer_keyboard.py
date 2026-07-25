"""Tracer 键盘遥控 (RDK X5/Linux, socketcan can2)。

candleLight 留在 X5 不用拔。SSH 连 X5 跑此脚本, 键盘经 SSH 终端。

W/↑ 前进  S/↓ 后退  A/← 左转  D/→ 右转
空格 停   Q/ESC 退出
速度限制(慢): v ≤ 0.3 m/s, w ≤ 0.5 rad/s
松开不自动停, 按空格停。

⚠️ 先清空底盘周围 + 手放急停!
"""
import can
import time
import sys
import subprocess
import termios
import tty
import select

CAN_IF = 'can2'
V_MAX, W_MAX = 0.3, 0.5       # 慢档上限
V_STEP, W_STEP = 0.05, 0.1    # 每次按键增量
SEND_PERIOD = 0.02            # 50Hz (防 500ms 超时)


def cmd_motion(v_mps, w_radps):
    """0x111 大端 MOTOROLA, mm/s, 0.001rad/s。"""
    v_mm = int(max(-1800, min(1800, v_mps * 1000)))
    w_mrad = int(max(-1000, min(1000, w_radps * 1000)))
    d = bytearray(8)
    d[0] = (v_mm >> 8) & 0xFF;   d[1] = v_mm & 0xFF
    d[2] = (w_mrad >> 8) & 0xFF; d[3] = w_mrad & 0xFF
    return can.Message(arbitration_id=0x111, data=list(d), is_extended_id=False)


# ─── 初始化 CAN (板子重启后 gs_usb 要 modprobe) ─────────────
subprocess.run('modprobe gs_usb', shell=True, capture_output=True)
time.sleep(1)

# 自动找底盘: 扫描 can0/can2, up 后 candump 看哪个有数据 (USB 重插接口名会变)
def find_chassis_if():
    for cif in ['can0', 'can2']:
        subprocess.run(f'ip link set {cif} down 2>/dev/null', shell=True, capture_output=True)
        subprocess.run(f'ip link set {cif} up type can bitrate 500000 2>/dev/null',
                       shell=True, capture_output=True)
        time.sleep(0.3)
        # candump 0.5秒看有没有 0x211
        r = subprocess.run(f'timeout 0.5 candump {cif} 2>/dev/null | grep -c " 211 "',
                           shell=True, capture_output=True, text=True)
        if int(r.stdout.strip() or '0') > 0:
            return cif
    return None

CAN_IF = find_chassis_if()
if CAN_IF is None:
    # 没找到有数据的接口, 默认 can0 (可能底盘没上电/线没连)
    CAN_IF = 'can0'
    subprocess.run(f'ip link set {CAN_IF} up type can bitrate 500000',
                   shell=True, capture_output=True)
    time.sleep(0.3)
    print(f"⚠️  没找到有底盘数据的接口 (can0/can2 都0帧)!")
    print(f"    检查: 底盘上电? CAN线接好? H/L没反? 默认用 {CAN_IF}\n")
else:
    print(f"✅ 找到底盘接口: {CAN_IF}\n")

bus = can.interface.Bus(channel=CAN_IF, interface='socketcan')

# 清急停 + 切指令模式
for _ in range(5):
    bus.send(can.Message(arbitration_id=0x441, data=[0x00])); time.sleep(0.02)
    bus.send(can.Message(arbitration_id=0x421, data=[0x01])); time.sleep(0.05)

print("\n=== Tracer 键盘遥控 ===")
print("W/↑前进  S/↓后退  A/←左转  D/→右转  空格停  Q/ESC退出")
print(f"速度限制: v≤{V_MAX}m/s  w≤{W_MAX}rad/s\n", flush=True)

v, w = 0.0, 0.0
last_send = time.time()
running = True
fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)

try:
    tty.setraw(fd)   # 单字符非阻塞读
    while running:
        # ── 键盘 ──
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            ch = sys.stdin.read(1)
            if ch == '\x1b':   # ESC 或方向键序列 (\x1b [ A/B/C/D)
                r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r2:
                    sys.stdin.read(1)   # [
                    r3, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r3:
                        a = sys.stdin.read(1)
                        if   a == 'A': v = min(V_MAX, v + V_STEP)     # ↑
                        elif a == 'B': v = max(-V_MAX, v - V_STEP)    # ↓
                        elif a == 'C': w = max(-W_MAX, w - W_STEP)    # →
                        elif a == 'D': w = min(W_MAX, w + W_STEP)     # ←
                else:
                    running = False   # 单 ESC = 退出
            else:
                k = ch.lower()
                if   k == 'w': v = min(V_MAX, v + V_STEP)
                elif k == 's': v = max(-V_MAX, v - V_STEP)
                elif k == 'a': w = min(W_MAX, w + W_STEP)
                elif k == 'd': w = max(-W_MAX, w - W_STEP)
                elif k == ' ': v, w = 0.0, 0.0
                elif k == 'q': running = False
            sys.stdout.write(f"\rv={v:+.2f}m/s  w={w:+.2f}rad/s   ")
            sys.stdout.flush()

        # ── 周期发 0x111 ──
        now = time.time()
        if now - last_send >= SEND_PERIOD:
            try:
                bus.send(cmd_motion(v, w))
            except Exception as e:
                if "buffer" in str(e).lower():
                    sys.stdout.write("\n\n❌ 发送缓冲区满 — 底盘没收到 (没ACK)!\n")
                    sys.stdout.write("   检查: 底盘上电(电压表亮)? CAN线底盘端插好? H/L没反?\n")
                    running = False
                else:
                    sys.stdout.write(f"\n发送错误: {e}\n")
            last_send = now

finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    sys.stdout.write("\n停止底盘...\n")
    t0 = time.time()
    while time.time() - t0 < 1.0:
        try:
            bus.send(cmd_motion(0.0, 0.0))
        except Exception:
            pass
        time.sleep(0.02)
    bus.shutdown()
    print("已退出, 底盘已停")
