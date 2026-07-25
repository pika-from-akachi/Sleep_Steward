import json
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hardware_agent import HardwareController, create_server, read_dht11


SENSOR_READING = {"tempC": 26.2, "humidityPct": 63.5}


class FakePWM:
    def __init__(self, pin, frequency):
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = None

    def start(self, duty_cycle):
        self.duty_cycle = duty_cycle

    def ChangeDutyCycle(self, duty_cycle):
        self.duty_cycle = duty_cycle

    def stop(self):
        self.duty_cycle = 0


class FakeGPIO:
    BOARD = "BOARD"
    OUT = "OUT"

    def __init__(self):
        self.mode = None
        self.outputs = []
        self.pwms = {}
        self.output_values = []

    def setwarnings(self, _enabled):
        pass

    def setmode(self, mode):
        self.mode = mode

    def setup(self, pin, direction, initial=0):
        self.outputs.append((pin, direction, initial))

    def PWM(self, pin, frequency):
        pwm = FakePWM(pin, frequency)
        self.pwms[pin] = pwm
        return pwm

    def output(self, pin, value):
        self.output_values.append((pin, value))

    def cleanup(self):
        pass


class HardwareControllerTest(unittest.TestCase):
    def make_controller(self, sensor_reader=lambda: SENSOR_READING):
        controller = HardwareController(FakeGPIO(), sensor_reader)
        self.addCleanup(controller.close)
        return controller

    def test_uses_software_pwm_for_gpio_only_pins(self):
        gpio = FakeGPIO()
        controller = HardwareController(gpio, lambda: SENSOR_READING)
        self.addCleanup(controller.close)

        self.assertEqual(gpio.pwms, {})

    def test_warm_light_uses_yellow_and_red_only(self):
        controller = self.make_controller()

        result = controller.set_light(True, 20, "warm")

        self.assertEqual(
            result["channels"],
            {"white": 0.0, "yellow": 20.0, "blue": 0.0, "red": 7.0},
        )

    def test_cool_light_uses_blue_and_white_only(self):
        controller = self.make_controller()

        result = controller.set_light(True, 20, "cool")

        self.assertEqual(
            result["channels"],
            {"white": 7.0, "yellow": 0.0, "blue": 20.0, "red": 0.0},
        )

    def test_brightness_is_clamped_to_safe_range(self):
        controller = self.make_controller()

        self.assertEqual(controller.set_light(True, 140, "warm")["brightness"], 100.0)
        self.assertEqual(controller.set_light(True, -20, "warm")["brightness"], 0.0)

    def test_off_turns_every_channel_off(self):
        controller = self.make_controller()
        controller.set_light(True, 20, "warm")

        result = controller.set_light(False, 20, "warm")

        self.assertEqual(result["channels"], dict.fromkeys(("white", "yellow", "blue", "red"), 0.0))

    def test_sensor_failure_returns_last_value_as_stale(self):
        readings = iter((SENSOR_READING, RuntimeError("checksum")))

        def read_sensor():
            value = next(readings)
            if isinstance(value, Exception):
                raise value
            return value

        controller = self.make_controller(read_sensor)

        self.assertFalse(controller.read_environment()["stale"])
        stale = controller.read_environment()

        self.assertTrue(stale["stale"])
        self.assertEqual(stale["tempC"], 26.2)
        self.assertEqual(stale["humidityPct"], 63.5)

    def test_estimated_lux_tracks_commanded_brightness(self):
        controller = self.make_controller()
        controller.set_light(True, 12, "warm")

        reading = controller.read_environment()

        self.assertEqual(reading["lightLux"], 122.0)
        self.assertEqual(reading["lightSource"], "estimated")

    def test_slow_sensor_read_does_not_block_light_control(self):
        sensor_started = threading.Event()
        release_sensor = threading.Event()

        def slow_sensor():
            sensor_started.set()
            release_sensor.wait(timeout=2)
            return SENSOR_READING

        controller = self.make_controller(slow_sensor)
        reader = threading.Thread(target=controller.read_environment)
        reader.start()
        self.assertTrue(sensor_started.wait(timeout=1))

        started_at = time.monotonic()
        result = controller.set_light(True, 12, "warm")
        elapsed = time.monotonic() - started_at

        release_sensor.set()
        reader.join(timeout=2)
        self.assertLess(elapsed, 0.2)
        self.assertEqual(result["brightness"], 12.0)


class HardwareHttpTest(unittest.TestCase):
    def setUp(self):
        self.controller = HardwareController(FakeGPIO(), lambda: SENSOR_READING)
        self.server = create_server(self.controller, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.controller.close()
        self.thread.join(timeout=2)

    def request_json(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.load(response)

    def test_environment_endpoint_returns_complete_contract(self):
        status, payload = self.request_json("/environment")

        self.assertEqual(status, 200)
        self.assertEqual(payload["tempC"], 26.2)
        self.assertEqual(payload["humidityPct"], 63.5)
        self.assertEqual(payload["lightSource"], "estimated")
        self.assertFalse(payload["stale"])

    def test_light_endpoint_rejects_non_boolean_on_value(self):
        with self.assertRaises(HTTPError) as caught:
            self.request_json("/light", {"on": "yes", "brightness": 10, "colorTemp": "warm"})

        self.assertEqual(caught.exception.code, 400)

class DhtReaderTest(unittest.TestCase):
    def test_dht_reader_maps_verified_binary_payload(self):
        def runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"ok":true,"humidity":63.5,"temperature":26.2}',
                stderr="",
            )

        self.assertEqual(
            read_dht11("/fake/dht11-read", runner=runner),
            {"tempC": 26.2, "humidityPct": 63.5},
        )


class ServerBindingTest(unittest.TestCase):
    def test_server_creation_does_not_require_reverse_dns(self):
        controller = HardwareController(FakeGPIO(), lambda: SENSOR_READING)
        try:
            with patch("socket.getfqdn", side_effect=AssertionError("reverse DNS called")):
                server = create_server(controller, "127.0.0.1", 0)
            server.server_close()
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
