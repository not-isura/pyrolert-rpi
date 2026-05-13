import time
import queue
from collections import deque
from typing import Optional

from Database import db, supabase_client, sync_worker


def pyrolert_detection_result(gas_co, gas_no2, gas_o2, pm25, temp_c, temp_roc=None):
    temp_RoC = temp_roc if temp_roc is not None else 0.0
    # if (gas_co >= 60 or gas_no2 >= 1) and (gas_o2 < 18 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 150):
    #     return "High Alert"
    # if (gas_co >= 25 or gas_no2 >= 0.2) and (gas_o2 < 19 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 90):
    #     return "Warning"
    
    if (gas_co >= 60 or gas_no2 >= 1) and (pm25 >= 150):
        return "High Alert"
    if (gas_co >= 25 or gas_no2 >= 0.2) and (pm25 >= 90):
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


# --- Heartbeat mode: toggle between the two ---
HEARTBEAT_EVERY_LOOP = True    # Option 1: push last_updated_ts on every confirmed reading
HEARTBEAT_INTERVAL_S = 30      # Option 2: used when HEARTBEAT_EVERY_LOOP = False


class AlertEpisodeManager:
    _SEVERITY = {"Warning": 1, "High Alert": 2}

    def __init__(self, db_conn, buzzer=None, led=None, command_queue=None, on_episode_created=None):
        self._db_conn = db_conn
        self._buzzer = buzzer
        self._led = led
        self._command_queue = command_queue
        self._on_episode_created = on_episode_created
        self._episode_id = None
        self._supabase_episode_id = None
        self._current_state = None
        self._last_heartbeat_ts = None
        self._restore_active_episode()

    def _should_heartbeat(self, ts: float) -> bool:
        if HEARTBEAT_EVERY_LOOP:
            return True
        return (
            self._last_heartbeat_ts is None
            or ts - self._last_heartbeat_ts >= HEARTBEAT_INTERVAL_S
        )

    def handle(self, confirmed_state: Optional[str], ts: float) -> None:
        if confirmed_state is None:
            return

        if self._episode_id is None:
            self._episode_id = self._create_episode(ts, confirmed_state)
            self._current_state = confirmed_state
            self._insert_transition(ts, confirmed_state)
            self._last_heartbeat_ts = ts
            print(f"[Alert] New episode {self._episode_id} started: {confirmed_state}")
            if self._led is not None:
                self._led.solid()
            if confirmed_state == "High Alert" and self._buzzer is not None:
                self._buzzer.start()
            return

        new_severity = self._SEVERITY.get(confirmed_state, 0)
        current_severity = self._SEVERITY.get(self._current_state, 0)
        if new_severity > current_severity:
            self._update_episode(ts, confirmed_state)
            self._insert_transition(ts, confirmed_state)
            self._current_state = confirmed_state
            self._last_heartbeat_ts = ts
            print(f"[Alert] Episode {self._episode_id} escalated to: {confirmed_state}")
            if self._led is not None:
                self._led.solid()
            if confirmed_state == "High Alert" and self._buzzer is not None:
                self._buzzer.start()
        else:
            if self._should_heartbeat(ts):
                self._update_episode(ts, None)
                self._last_heartbeat_ts = ts

    def _restore_active_episode(self) -> None:
        if self._db_conn is None:
            return
        row = db.fetch_active_episode(self._db_conn)
        if row is None:
            return

        supa_id = row["supabase_episode_id"]
        if supa_id is not None:
            status = supabase_client.fetch_episode_status(supa_id)
            if status is not None and status != "active":
                db.set_episode_status(self._db_conn, row["id"], status)
                print(f"[Alert] Episode {row['id']} is '{status}' on Supabase — SQLite updated, skipping restore")
                return
            if status is None:
                print(f"[Alert] Supabase unreachable — trusting SQLite for episode {row['id']} (fail-safe)")

        self._episode_id = row["id"]
        self._current_state = row["current_state"]
        self._supabase_episode_id = supa_id
        self._last_heartbeat_ts = row["last_updated_ts"]
        print(f"[Alert] Restored active episode {self._episode_id} ({self._current_state}) from SQLite")
        if self._led is not None:
            self._led.solid()
        if self._current_state == "High Alert" and self._buzzer is not None:
            self._buzzer.start()
            print("[Alert] Buzzer restarted — restored High Alert episode")
        if self._on_episode_created and supa_id is not None:
            self._on_episode_created(supa_id)

    def _create_episode(self, ts: float, state: str) -> int:
        if self._db_conn is None:
            return 0
        episode_id = db.create_alert_episode(self._db_conn, started_ts=ts, current_state=state)
        self._supabase_episode_id = supabase_client.push_alert_episode({
            "started_ts":      ts,
            "last_updated_ts": ts,
            "current_state":   state,
            "status":          "active",
        })
        if self._supabase_episode_id is None:
            print("[Alert] Supabase episode id not captured — last_updated_ts will not sync to Supabase")
        else:
            print(f"[Alert] Supabase episode id: {self._supabase_episode_id}")
            db.set_supabase_episode_id(self._db_conn, episode_id, self._supabase_episode_id)
            if self._on_episode_created:
                self._on_episode_created(self._supabase_episode_id)
        return episode_id

    def _update_episode(self, ts: float, state: Optional[str]) -> None:
        if self._db_conn is None or self._episode_id is None:
            return
        db.update_alert_episode(self._db_conn, self._episode_id, last_updated_ts=ts, current_state=state)
        if self._supabase_episode_id is None:
            row = db.fetch_active_episode(self._db_conn)
            if row and row["supabase_episode_id"]:
                self._supabase_episode_id = row["supabase_episode_id"]
                print(f"[Alert] Supabase episode id recovered from SQLite: {self._supabase_episode_id}")
        if self._supabase_episode_id is not None:
            sync_worker.push_episode_update(self._supabase_episode_id, ts=ts, current_state=state)

    def _insert_transition(self, ts: float, state: str) -> None:
        if self._db_conn is None or self._episode_id is None:
            return
        db.insert_alert_transition(self._db_conn, self._episode_id, ts=ts, state=state)
        if self._supabase_episode_id is not None:
            supabase_client.push_alert_transition({
                "episode_id": self._supabase_episode_id,
                "ts":         ts,
                "state":      state,
            })

    def process_commands(self) -> None:
        """Drain the command queue and act on each pending command. Call once per main loop cycle."""
        if self._command_queue is None:
            return
        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except Exception:
                break
            action = cmd.get("action")
            if action in ("resolved", "false_alarm"):
                self._handle_resolution(action)
            elif action == "mute_buzzer":
                self._handle_mute_buzzer()
            elif action == "unmute_buzzer":
                self._handle_unmute_buzzer()

    def _handle_resolution(self, action: str) -> None:
        ts = time.time()
        print(f"[Alert] Episode {self._episode_id} marked as '{action}' by website — acknowledging")

        if self._buzzer is not None:
            self._buzzer.stop()
        if self._led is not None:
            self._led.start()

        if self._db_conn is not None and self._episode_id is not None:
            db.set_episode_status(self._db_conn, self._episode_id, action)

        if self._supabase_episode_id is not None:
            supabase_client.update_alert_episode(
                self._supabase_episode_id,
                rpi_acknowledged_at=ts,
            )
            print(f"[Alert] Acknowledged '{action}' to Supabase (episode {self._supabase_episode_id})")

        self._episode_id = None
        self._supabase_episode_id = None
        self._current_state = None
        self._last_heartbeat_ts = None

    def _handle_mute_buzzer(self) -> None:
        if self._episode_id is None:
            return
        print(f"[Alert] Buzzer mute command received for episode {self._episode_id}")

        if self._buzzer is not None:
            self._buzzer.stop()

        if self._supabase_episode_id is not None:
            supabase_client.update_alert_episode(
                self._supabase_episode_id,
                buzzer_status="muted",
            )
            print(f"[Alert] Buzzer muted — acknowledged to Supabase")

    def _handle_unmute_buzzer(self) -> None:
        if self._episode_id is None:
            return
        print(f"[Alert] Buzzer unmute command received for episode {self._episode_id}")

        if self._current_state == "High Alert" and self._buzzer is not None:
            self._buzzer.start()

        if self._supabase_episode_id is not None:
            supabase_client.update_alert_episode(
                self._supabase_episode_id,
                buzzer_status="on",
            )
            print(f"[Alert] Buzzer unmuted — acknowledged to Supabase")