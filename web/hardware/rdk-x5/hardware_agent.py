#!/usr/bin/env python3
import argparse
import json
import math
import socketserver
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PIN_BY_COLOR = {"white": 13, "yellow": 15, "blue": 18, "red": 22}
SOFTWARE_PWM_HZ = 100


class SensorUnavailableError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def light_channels(on, brightness, color_temp):
    level = min(100.0, max(0.0, float(brightness))) if on else 0.0
    if color_temp == "cool":
        return {
            "white": round(level * 0.35, 1),
            "yellow": 0.0,
            "blue": level,
            "red": 0.0,
        }
    if color_temp != "warm":
        raise ValueError("colorTemp must be warm or cool")
    return {
        "white": 0.0,
        "yellow": level,
        "blue": 0.0,
        "red": round(level * 0.35, 1),
    }


class SoftwarePwmBank:
    def __init__(self, gpio_module, pin_by_color, frequency_hz=SOFTWARE_PWM_HZ):
        self._gpio = gpio_module
        self._pin_by_color = dict(pin_by_color)
        self._period = 1.0 / frequency_hz
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._closed = False
        self._duties = dict.fromkeys(self._pin_by_color, 0.0)

        for pin in self._pin_by_color.values():
            self._gpio.setup(pin, self._gpio.OUT, initial=0)

        self._thread = threading.Thread(
            target=self._run,
            name="sleep-light-software-pwm",
            daemon=True,
        )
        self._thread.start()

    def set_duty_cycles(self, duties):
        with self._lock:
            self._duties = {
                color: min(100.0, max(0.0, float(duties.get(color, 0.0))))
                for color in self._pin_by_color
            }

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        self._thread.join(timeout=1)
        for pin in self._pin_by_color.values():
            self._gpio.output(pin, 0)

    def _run(self):
        while not self._stop.is_set():
            cycle_start = time.monotonic()
            with self._lock:
                duties = dict(self._duties)

            off_events = {}
            for color, pin in self._pin_by_color.items():
                duty = duties[color]
                self._gpio.output(pin, 1 if duty > 0 else 0)
                if 0 < duty < 100:
                    off_events.setdefault(self._period * duty / 100.0, []).append(pin)

            for offset, pins in sorted(off_events.items()):
                remaining = cycle_start + offset - time.monotonic()
                if remaining > 0 and self._stop.wait(remaining):
                    break
                for pin in pins:
                    self._gpio.output(pin, 0)

            remaining = cycle_start + self._period - time.monotonic()
            if remaining > 0:
                self._stop.wait(remaining)


class HardwareController:
    def __init__(self, gpio_module, sensor_reader):
        self._gpio = gpio_module
        self._sensor_reader = sensor_reader
        self._lock = threading.RLock()
        self._sensor_lock = threading.Lock()
        self._last_sensor = None
        self._last_sensor_error = None
        self._light = {
            "on": False,
            "brightness": 0.0,
            "colorTemp": "warm",
            "channels": light_channels(False, 0, "warm"),
        }

        self._gpio.setwarnings(False)
        self._gpio.setmode(self._gpio.BOARD)
        self._pwm_bank = SoftwarePwmBank(self._gpio, PIN_BY_COLOR)

    def set_light(self, on, brightness, color_temp="warm"):
        if not isinstance(on, bool):
            raise ValueError("on must be boolean")
        if isinstance(brightness, bool) or not isinstance(brightness, (int, float)):
            raise ValueError("brightness must be a number")
        if not math.isfinite(float(brightness)):
            raise ValueError("brightness must be finite")

        level = min(100.0, max(0.0, float(brightness))) if on else 0.0
        channels = light_channels(on, level, color_temp)
        with self._lock:
            self._pwm_bank.set_duty_cycles(channels)
            self._light = {
                "on": on and level > 0,
                "brightness": level,
                "colorTemp": color_temp,
                "channels": channels,
            }
            return dict(self._light)

    def read_environment(self):
        with self._sensor_lock:
            try:
                raw = self._sensor_reader()
                temp_c = float(raw["tempC"])
                humidity_pct = float(raw["humidityPct"])
                if not math.isfinite(temp_c) or not math.isfinite(humidity_pct):
                    raise ValueError("sensor returned non-finite values")
                if not 0 <= humidity_pct <= 100 or not -40 <= temp_c <= 80:
                    raise ValueError("sensor values are out of range")
                with self._lock:
                    self._last_sensor = {
                        "tempC": temp_c,
                        "humidityPct": humidity_pct,
                        "sampledAt": utc_now(),
                    }
                    self._last_sensor_error = None
                    sensor = dict(self._last_sensor)
                    stale = False
            except Exception as error:
                with self._lock:
                    self._last_sensor_error = str(error)
                    if self._last_sensor is None:
                        raise SensorUnavailableError(str(error)) from error
                    sensor = dict(self._last_sensor)
                    stale = True

        with self._lock:
            light = dict(self._light)
            light_lux = 2.0 + light["brightness"] * 10.0 if light["on"] else 2.0
            return {
                **sensor,
                "lightLux": light_lux,
                "lightSource": "estimated",
                "stale": stale,
            }

    def health(self):
        with self._lock:
            return {
                "ok": self._last_sensor_error is None,
                "sensorOk": self._last_sensor_error is None,
                "sensorError": self._last_sensor_error,
                "light": dict(self._light),
            }

    def close(self):
        with self._lock:
            self._pwm_bank.close()
            self._gpio.cleanup()


def read_dht11(command="/usr/local/bin/dht11-read", runner=subprocess.run):
    result = runner(
        [command, "--json", "--attempts", "3"],
        capture_output=True,
        check=False,
        text=True,
        timeout=12,
    )
    if result.returncode != 0:
        raise SensorUnavailableError(
            result.stderr.strip() or result.stdout.strip() or "DHT11 read failed"
        )
    payload = json.loads(result.stdout)
    if payload.get("ok") is not True:
        raise SensorUnavailableError(payload.get("error", "DHT11 read failed"))
    return {
        "tempC": payload["temperature"],
        "humidityPct": payload["humidity"],
    }


def make_handler(controller):
    class HardwareRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self._json(200, controller.health())
                return
            if self.path == "/environment":
                try:
                    self._json(200, controller.read_environment())
                except SensorUnavailableError as error:
                    self._json(503, {"error": str(error)})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/light":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    raise ValueError("invalid request size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                result = controller.set_light(
                    payload.get("on"),
                    payload.get("brightness"),
                    payload.get("colorTemp", "warm"),
                )
                self._json(200, {"ok": True, "light": result})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})

        def log_message(self, _format, *_args):
            return

        def _json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return HardwareRequestHandler


class HardwareHttpServer(ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def create_server(controller, host="0.0.0.0", port=8765):
    return HardwareHttpServer((host, port), make_handler(controller))


def main():
    parser = argparse.ArgumentParser(description="Baby Good Sleep RDK X5 hardware agent")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dht-command", default="/usr/local/bin/dht11-read")
    args = parser.parse_args()

    import Hobot.GPIO as GPIO

    controller = HardwareController(GPIO, lambda: read_dht11(args.dht_command))
    server = create_server(controller, args.host, args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
