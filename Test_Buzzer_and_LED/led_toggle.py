from __future__ import annotations

import threading
from gpiozero import LED


class ToggleLED:
    def __init__(self, pin: int, on_time: float = 0.05, off_time: float = 2.0) -> None:
        self._led = LED(pin)
        self._on_time = on_time
        self._off_time = off_time
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=self._on_time + self._off_time + 0.1)
        self._led.off()

    def toggle(self) -> None:
        if self.is_running():
            self.stop()
        else:
            self.start()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def close(self) -> None:
        self.stop()
        self._led.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._led.on()
            if self._stop_event.wait(self._on_time):
                break
            self._led.off()
            if self._stop_event.wait(self._off_time):
                break
        self._led.off()
