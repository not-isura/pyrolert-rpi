from collections import deque
from typing import Optional

from Database import db


def pyrolert_detection_result(gas_co, gas_no2, gas_o2, pm25, temp_c, temp_roc=None):
    temp_RoC = temp_roc if temp_roc is not None else 0.0
    if (gas_co >= 60 or gas_no2 >= 1) and (gas_o2 < 18 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 150):
        return "High Alert"
    if (gas_co >= 25 or gas_no2 >= 0.2) and (gas_o2 < 19 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 90):
        return "Warning"
    return "Normal"


class SlidingWindowAlert:
    def __init__(self, window_size: int, high_threshold: int, warning_threshold: int):
        self._window_size = window_size
        self._high_threshold = high_threshold
        self._warning_threshold = warning_threshold
        self._window = deque()
        self._high_count = 0
        self._warning_count = 0

    def add(self, detection_result: str) -> Optional[str]:
        if detection_result == "High Alert":
            self._high_count += 1
        elif detection_result == "Warning":
            self._warning_count += 1

        self._window.append(detection_result)
        if len(self._window) > self._window_size:
            removed = self._window.popleft()
            if removed == "High Alert":
                self._high_count -= 1
            elif removed == "Warning":
                self._warning_count -= 1

        if self._high_count >= self._high_threshold:
            return "High Alert"
        if self._high_count + self._warning_count >= self._warning_threshold:
            return "Warning"
        return None

    def counts(self) -> tuple[int, int, int]:
        normal_count = len(self._window) - self._high_count - self._warning_count
        return normal_count, self._warning_count, self._high_count


class AlertEpisodeManager:
    _SEVERITY = {"Warning": 1, "High Alert": 2}

    def __init__(self, db_conn, buzzer=None):
        self._db_conn = db_conn
        self._buzzer = buzzer
        self._episode_id = None
        self._current_state = None

    def handle(self, confirmed_state: Optional[str], ts: float) -> None:
        if confirmed_state is None:
            return

        if self._episode_id is None:
            self._episode_id = self._create_episode(ts, confirmed_state)
            self._current_state = confirmed_state
            self._insert_transition(ts, confirmed_state)
            print(f"[Alert] New episode {self._episode_id} started: {confirmed_state}")
            if confirmed_state == "High Alert" and self._buzzer is not None:
                self._buzzer.start()
            return

        new_severity = self._SEVERITY.get(confirmed_state, 0)
        current_severity = self._SEVERITY.get(self._current_state, 0)
        if new_severity > current_severity:
            self._update_episode(ts, confirmed_state)
            self._insert_transition(ts, confirmed_state)
            self._current_state = confirmed_state
            print(f"[Alert] Episode {self._episode_id} escalated to: {confirmed_state}")
            if confirmed_state == "High Alert" and self._buzzer is not None:
                self._buzzer.start()
        else:
            self._update_episode(ts, None)

    def _create_episode(self, ts: float, state: str) -> int:
        if self._db_conn is None:
            return 0
        return db.create_alert_episode(self._db_conn, started_ts=ts, current_state=state)

    def _update_episode(self, ts: float, state: Optional[str]) -> None:
        if self._db_conn is None or self._episode_id is None:
            return
        db.update_alert_episode(self._db_conn, self._episode_id, last_updated_ts=ts, current_state=state)

    def _insert_transition(self, ts: float, state: str) -> None:
        if self._db_conn is None or self._episode_id is None:
            return
        db.insert_alert_transition(self._db_conn, self._episode_id, ts=ts, state=state)
