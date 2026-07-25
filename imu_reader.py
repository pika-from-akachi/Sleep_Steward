"""指环六轴 IMU 实时数据采集工具 v2

连接智能指环，实时显示六轴数据。自动处理模式切换。

用法:
    python imu_reader.py
    python imu_reader.py -a CD:40:FF:86:27:D5
    python imu_reader.py --no-save

依赖: pip install bleak
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SDK_DIR = _SCRIPT_DIR / "ring_sound_SDK"
if str(_SDK_DIR) not in sys.path:
    sys.path.insert(0, str(_SDK_DIR))

import ring_sound as sdk

DEFAULT_ADDRESS = "CD:40:FF:86:27:D5"
DEFAULT_BATCH_COUNT = 0  # 不限量
DEFAULT_OUTPUT_DIR = "imu_data"


class C:
    G = "\033[92m"
    Y = "\033[93m"
    B = "\033[96m"
    R = "\033[91m"
    W = "\033[1m"
    X = "\033[0m"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def log(p, m, c=""):
    print(f"{c}[{ts()} {p}]{C.X} {m}")


# ══════════════════════════════════════════════════════════════

async def run(args):
    # ── 1. 扫描 + 连接 ──
    print(f"\n{C.W}{'═' * 58}{C.X}")
    print(f"{C.W}  指环六轴 IMU 实时采集  |  SDK {sdk.__version__}{C.X}")
    print(f"{C.W}{'═' * 58}{C.X}")

    log("扫描", f"查找 {args.address} ...", C.B)
    devices = await sdk.scan_rings(address=args.address, timeout_s=8.0)
    if not devices:
        log("错误", "未找到指环", C.R)
        return
    for d in devices:
        print(f"   找到: name={d.name!r}  address={d.address}")

    try:
        ring = sdk.RingSoundClient(address=args.address)
        await ring.connect()
    except sdk.TransportError as e:
        log("错误", f"连接失败: {e}", C.R)
        return

    try:
        info = await sdk.get_system_info(ring)
        print(f"   固件: {info.firmware_version} | 型号: {info.model}")
        print(f"   电量: {info.battery_percent}% {'(充电中)' if info.battery_charging else ''}")
        log("连接", "成功！", C.G)
    except Exception as e:
        log("错误", f"读取系统信息失败: {e}", C.R)
        return

    # ── 2. 注册全部按键事件监听，同时尝试启动 IMU ──
    event_queue: asyncio.Queue[str] = asyncio.Queue()

    def _make_handler(name: str):
        def h(pkt):
            event_queue.put_nowait(name)
        return h

    ring.add_packet_handler(sdk.SensorCommand.KEY_SINGLE_PRESS, _make_handler("单击"))
    ring.add_packet_handler(sdk.SensorCommand.KEY_DOUBLE_PRESS, _make_handler("双击"))
    ring.add_packet_handler(sdk.SensorCommand.DOUBLE_TAP, _make_handler("六轴双击"))
    ring.add_packet_handler(sdk.SensorCommand.GESTURE, _make_handler("手势"))

    # ── 3. 主循环：持续尝试开启 IMU ──
    print()
    print(f"{C.W}{'─' * 58}{C.X}")
    print(f"{C.W}  正在尝试开启 IMU 上报...{C.X}")
    print(f"{C.W}{'─' * 58}{C.X}")
    print()
    print(f"  {C.B}LED 参考:{C.X} 单击→切换模式 | 长按绿灯=录音中 | 长按红灯=手势中")
    print(f"  {C.B}操作:{C.X} 如果一直显示'忙碌'，请 {C.W}快速单击{C.X} 指环按键 1 次")
    print(f"         （快按快放，不要按住！松开后等 0.5 秒）")
    print()

    start_info = None
    deadline = asyncio.get_event_loop().time() + 60.0

    while start_info is None:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            log("超时", "60秒内未能开启 IMU 上报", C.R)
            print()
            print(f"  {C.Y}可能的原因：{C.X}")
            print(f"  1. 按键没有被正确识别 — 试试不同力度/速度的单击")
            print(f"  2. 指环正在长按手势中 — 松开按键等红灯熄灭再试")
            print(f"  3. 指环仍在录音模式 — 观察长按时的 LED 颜色")
            print(f"     (绿色=录音模式, 红色=手势模式)")
            return

        # 尝试开启
        try:
            start_info = await sdk.start_sensor_report(ring)
        except sdk.DeviceError as e:
            if e.error_code == 2:
                # 忙碌 — 等按键事件或等一会再试
                pass
            else:
                log("错误", f"设备错误: {e}", C.R)
                return

        if start_info is not None:
            break

        # 还没成功 — 等 2 秒，同时监听按键事件
        log("状态", f"设备忙碌... 等待按键或重试 ({int(remaining)}s后超时)", C.Y)
        try:
            event_name = await asyncio.wait_for(event_queue.get(), timeout=2.0)
            log("事件", f"检测到: {event_name} ！", C.G)
            await asyncio.sleep(0.5)  # 等模式切换完成
        except asyncio.TimeoutError:
            pass  # 2秒没事件，继续重试

    # ── 4. IMU 已开启，开始实时采集 ──
    print()
    log("IMU", "✅ 上报已开启！", C.G)
    print(f"   采样率: {start_info.sample_rate_hz} Hz | 加速度量程: ±{start_info.accel_range_g}g | 陀螺仪量程: ±{start_info.gyro_range_dps} dps")
    print(f"   {C.W}按 Ctrl+C 停止采集{C.X}")
    print()

    # 表头
    print(f"{C.W}{'seq':>6s} {'time_ms':>8s} {'accel_x':>7s} {'accel_y':>7s} {'accel_z':>7s} {'gyro_x':>7s} {'gyro_y':>7s} {'gyro_z':>7s}   {'elapsed':>6s}{C.X}")

    # CSV
    csv_file = None
    csv_writer = None
    csv_path = None
    if not args.no_save:
        os.makedirs(args.output_dir, exist_ok=True)
        csv_path = Path(args.output_dir) / f"imu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_file = open(str(csv_path), "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["sequence", "timestamp_ms",
                             "accel_x", "accel_y", "accel_z",
                             "gyro_x", "gyro_y", "gyro_z"])

    batch_count = 0
    total_samples = 0
    max_batches = args.batch_count if args.batch_count > 0 else None
    start_time = time.time()

    try:
        while max_batches is None or batch_count < max_batches:
            try:
                batch = await asyncio.wait_for(
                    sdk.wait_sensor_data(ring, timeout_s=5.0),
                    timeout=6.0,
                )
            except asyncio.TimeoutError:
                # 顺便检查有没有新事件
                try:
                    ev = event_queue.get_nowait()
                    log("事件", f"检测到: {ev}", C.B)
                except asyncio.QueueEmpty:
                    pass
                continue

            batch_count += 1
            elapsed = time.time() - start_time

            for i, sample in enumerate(batch.samples):
                seq = batch.sequence_start + i
                total_samples += 1
                # 颜色：静止绿色，运动黄色
                m = abs(sample.accel_x) + abs(sample.accel_y) + abs(sample.accel_z)
                color = C.G if m < 3000 else (C.Y if m < 8000 else C.R)
                print(
                    f"{color}{seq:6d} {sample.timestamp_ms:8d} "
                    f"{sample.accel_x:7d} {sample.accel_y:7d} {sample.accel_z:7d} "
                    f"{sample.gyro_x:7d} {sample.gyro_y:7d} {sample.gyro_z:7d}{C.X}"
                    f"   {elapsed:5.1f}s"
                )
                if csv_writer:
                    csv_writer.writerow([
                        seq, sample.timestamp_ms,
                        sample.accel_x, sample.accel_y, sample.accel_z,
                        sample.gyro_x, sample.gyro_y, sample.gyro_z,
                    ])

    except KeyboardInterrupt:
        print()
        log("停止", "用户中断", C.Y)

    elapsed = time.time() - start_time
    try:
        await sdk.stop_sensor_report(ring)
    except Exception:
        pass

    print()
    log("统计", f"{batch_count} 批, {total_samples} 采样点, {elapsed:.1f}s", C.G)
    if total_samples > 0 and elapsed > 0:
        print(f"   速率: {total_samples/elapsed:.1f} 点/秒")
    if csv_path:
        print(f"   文件: {csv_path}")

    await ring.disconnect()


def main():
    parser = argparse.ArgumentParser(description="指环六轴 IMU 实时数据采集")
    parser.add_argument("-a", "--address", default=DEFAULT_ADDRESS)
    parser.add_argument("-n", "--batch-count", type=int, default=DEFAULT_BATCH_COUNT,
                        help="采集批数，0=不限量")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
