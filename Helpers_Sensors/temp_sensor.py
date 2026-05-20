# temp_sensor.py
import os
import glob
import time
import queue
import threading
import traceback
from time import sleep

TEMP_SETUP_TIMEOUT_S = 5
TEMP_SAMPLING_PERIOD = 0.25
TEMP_MAX_CONSECUTIVE_ERRORS = 3


class TempSensor:

    def __init__(self):
        self._device_path = None
        self._data: queue.Queue = queue.Queue(maxsize=3)
        self._last_value = None
        self._consecutive_errors = 0

    def setup(self):
        os.system('modprobe w1-gpio')
        os.system('modprobe w1-therm')

        base_dir = '/sys/bus/w1/devices/'
        devices = glob.glob(base_dir + '28*')
        if not devices:
            raise RuntimeError("No DS18B20 temperature sensor found under /sys/bus/w1/devices/")

        self._device_path = devices[0]
        rom = self._device_path.split('/')[-1]

        sleep(0.5)
        print(f"Temperature Device ROM: {rom}")

        # Warm-up read to verify sensor responds
        warmup, unit_Temp = self._read_temp()
        print(f"Temperature sensor ready (warm-up: {warmup:.2f} {unit_Temp})\n")

    def _read_raw(self):
        with open(self._device_path + '/w1_slave', 'r') as f:
            lines = f.readlines()

        if len(lines) < 2:
            raise ValueError(f"Unexpected sensor output: {lines}")

        valid, temp = lines
        return valid, temp

    def _read_temp(self) -> float:
        valid, temp = self._read_raw()

        start_wait = time.monotonic()
        while 'YES' not in valid:
            if time.monotonic() - start_wait >= TEMP_SETUP_TIMEOUT_S:
                raise TimeoutError("Temperature sensor timed out waiting for valid reading")
            sleep(0.2)
            valid, temp = self._read_raw()

        pos = temp.find('t=')
        if pos == -1:
            raise ValueError(f"Malformed temperature sensor payload: {temp.strip()}")

        raw = int(temp[pos + 2:])
        if raw == 0:
            raise RuntimeError("Temperature sensor returned raw 0 — sensor may be disconnected")

        return round(raw / 1000.0, 2), "°C"

    def _drain(self):
        if self._data.full():
            try:
                self._data.get_nowait()
            except queue.Empty:
                pass

    def _run(self):
        while True:
            try:
                temp_c = self._read_temp()
                self._consecutive_errors = 0
                self._drain()
                self._data.put(temp_c)

            except KeyboardInterrupt:
                raise

            except Exception as e:
                self._consecutive_errors += 1
                error_msg = f"{type(e).__name__}: {e}"
                try:
                    if self._consecutive_errors < TEMP_MAX_CONSECUTIVE_ERRORS:
                        print(f"[TempSensor] {error_msg} (transient {self._consecutive_errors}/{TEMP_MAX_CONSECUTIVE_ERRORS})")
                    else:
                        print(f"[TempSensor] {error_msg} (persistent, error #{self._consecutive_errors})")
                except (OSError, ValueError):
                    pass

                self._drain()
                if self._consecutive_errors >= TEMP_MAX_CONSECUTIVE_ERRORS:
                    self._data.put({"error": error_msg, "traceback": traceback.format_exc().strip()})
                else:
                    self._data.put(None)

            finally:
                sleep(TEMP_SAMPLING_PERIOD)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="TempSensor").start()

    def get(self, timeout: float = 5.0) -> tuple:
        try:
            value = self._data.get_nowait()
        except queue.Empty:
            if self._last_value is not None:
                return self._last_value
            try:
                value = self._data.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError(f"TempSensor timed out after {timeout}s — no data from background thread")

        if isinstance(value, dict) and "error" in value:
            raise RuntimeError(f"TempSensor disconnected or failed: {value['error']}")

        if value is None:
            if self._last_value is not None:
                return self._last_value
            raise RuntimeError("TempSensor reported a sensor error — check logs above")

        self._last_value = value
        return value