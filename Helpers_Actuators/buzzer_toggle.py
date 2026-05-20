from __future__ import annotations

import threading
from time import sleep
from gpiozero import Buzzer


class ToggleBuzzer:
    def __init__(self, pin: int, on_time: float = 0.2, off_time: float = 0.1) -> None:
        self._buzzer = Buzzer(pin)
        self._on_time = on_time
        self._off_time = off_time
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._start_with(self._on_time, self._off_time)

    def start_warning(self) -> None:
        self._start_with(1.0, 1.0)

    def _start_with(self, on_time: float, off_time: float) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, args=(on_time, off_time), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=self._on_time + self._off_time + 0.1)
        self._buzzer.off()

    def toggle(self) -> None:
        if self.is_running():
            self.stop()
        else:
            self.start()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def close(self) -> None:
        self.stop()
        self._buzzer.close()

    def _loop(self, on_time: float, off_time: float) -> None:
        while not self._stop_event.is_set():
            self._buzzer.on()
            if self._stop_event.wait(on_time):
                break
            self._buzzer.off()
            if self._stop_event.wait(off_time):
                break
        self._buzzer.off()
