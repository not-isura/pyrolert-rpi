# temp_sensor.py
import os
import glob
import time
import queue
import threading
from time import sleep

TEMP_SETUP_TIMEOUT_S = 5
TEMP_SAMPLING_PERIOD = 0.250


class TempSensor:

    def __init__(self):
        self._device_path = None
        self._data: queue.Queue = queue.Queue(maxsize=20)

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
        print(f"Temperature sensor ready (warm-up: {warmup:.2f} {unit_Temp})")

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

    def _run(self):
        while True:
            try:
                temp_c = self._read_temp()

                if self._data.full():
                    try:
                        self._data.get_nowait()
                    except queue.Empty:
                        pass

                self._data.put(temp_c)

            except KeyboardInterrupt:
                raise

            except Exception as e:
                print(f"[TempSensor] {type(e).__name__}: {e}")

                if self._data.full():
                    try:
                        self._data.get_nowait()
                    except queue.Empty:
                        pass

                self._data.put(None)

            finally:
                sleep(TEMP_SAMPLING_PERIOD)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="TempSensor").start()

    def get(self, timeout: float = 5.0) -> float:
        try:
            value = self._data.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"TempSensor timed out after {timeout}s — no data from background thread")

        if value is None:
            raise RuntimeError("TempSensor reported a sensor error — check logs above")

        return value