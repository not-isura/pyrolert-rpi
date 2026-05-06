# gas_sensor.py
import time
import threading
import queue
import traceback
from time import sleep
from Sensor_Libraries import DFRobot_MultiGasSensor_I2C, recvbuf

GAS_SETUP_TIMEOUT_S = 10
GAS_SAMPLING_PERIOD = 0.250


class GasSensor:

    def __init__(self, bus: int, address: int):
        self._sensor = DFRobot_MultiGasSensor_I2C(bus, address)

    def setup(self):
        self._connect()
        self._sensor.set_temp_compensation(self._sensor.ON)
        sleep(0.3)

        warmup = self._sensor.read_gas_concentration()
        if all(b == 0 for b in recvbuf):
            raise RuntimeError("Warm-up read failed — sensor may be disconnected")

        print(f"{self._sensor.gastype} connected and ready (warm-up: {warmup:.3f} {self._sensor.gasunits})")

    def _connect(self):
        start_wait = time.monotonic()
        while not self._sensor.change_acquire_mode(self._sensor.PASSIVITY):
            if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
                raise TimeoutError("Sensor timed out entering passive mode")
            if all(b == 0 for b in recvbuf):
                raise RuntimeError("Sensor returned all zeros — sensor may be disconnected")
            print("Waiting for sensor to enter passive mode...")
            sleep(0.1)

    def measure(self) -> float:
        value = self._sensor.read_gas_concentration()
        if all(b == 0 for b in recvbuf):
            raise RuntimeError(f"{self._sensor.gastype} sensor returned all zeros — sensor may be disconnected")
        if value < 0.15 and self._sensor.gastype in ("CO", "NO2"):
            value = 0.0
        return value

    @property
    def gastype(self) -> str:
        return self._sensor.gastype

    @property
    def gasunits(self) -> str:
        return self._sensor.gasunits


class GasSensorGroup:

    def __init__(self, co: GasSensor, o2: GasSensor, no2: GasSensor):
        self.co  = co
        self.o2  = o2
        self.no2 = no2
        self._data: queue.Queue = queue.Queue(maxsize=1)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="GasSensorGroup").start()

    def _run(self):
        while True:
            try:
                co_val  = self.co.measure()
                sleep(0.001)
                o2_val  = self.o2.measure()
                sleep(0.001)
                no2_val = self.no2.measure()

                result = (co_val, o2_val, no2_val)

                if self._data.full():
                    try:
                        self._data.get_nowait()
                    except queue.Empty:
                        pass

                self._data.put(result)

            except KeyboardInterrupt:
                raise

            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                error_tb = traceback.format_exc().strip()
                print(f"[GasSensorGroup] {error_msg}")
                print(f"[GasSensorGroup] traceback:\n{error_tb}")

                if self._data.full():
                    try:
                        self._data.get_nowait()
                    except queue.Empty:
                        pass

                # Pass error details to main thread so root cause is not lost.
                self._data.put({"error": error_msg, "traceback": error_tb})

            finally:
                sleep(GAS_SAMPLING_PERIOD)

    def get(self, timeout: float = 5.0):
        """
        Returns (co, o2, no2) tuple.
        Raises TimeoutError if no data arrives within timeout.
        Raises RuntimeError if background thread reported a sensor error.
        """
        try:
            result = self._data.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"GasSensorGroup timed out after {timeout}s — no data from background thread")

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(f"GasSensorGroup reported a sensor error: {result['error']}")

        if result is None:
            raise RuntimeError("GasSensorGroup reported a sensor error")

        return result