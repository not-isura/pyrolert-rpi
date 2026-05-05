from time import time, sleep

import db
import supabase_client
from alert_logic import AlertEpisodeManager, SlidingWindowAlert

from buzzer_toggle import ToggleBuzzer
toggle_buzzer = ToggleBuzzer(22)

WINDOW_SIZE = 20
HIGH_ALERT_THRESHOLD = 12
WARNING_THRESHOLD = 12
HEARTBEAT_S = 20


db_conn = db.init_db("db_pyrolert.sqlite")
supabase_client.get_client()
window = SlidingWindowAlert(WINDOW_SIZE, HIGH_ALERT_THRESHOLD, WARNING_THRESHOLD)
alert_manager = AlertEpisodeManager(db_conn, buzzer=toggle_buzzer)
supa_episode_id = None
supa_state = None
severity = {"Warning": 1, "High Alert": 2}
last_heartbeat_ts = None

# 20 samples: 8 Normal + 12 Warning -> should confirm Warning
sequence = ["Normal"] * 8 + ["Warning"] * 8 + ["High Alert"] * 4 + ["Warning"] * 10 + ["Normal"] * 8 + ["High Alert"] * 15

for i, det in enumerate(sequence, 1):
    ts = time()
    confirmed = window.add(det)
    print(f"{i:02d}: det={det} confirmed={confirmed}")
    alert_manager.handle(confirmed, ts)
    if confirmed is not None:
        if supa_episode_id is None:
            supa_episode_id = supabase_client.push_alert_episode(
                {
                    "started_ts": ts,
                    "last_updated_ts": ts,
                    "current_state": confirmed,
                    "status": "active",
                    "meta": {"source": "mock"},
                }
            )
            if supa_episode_id is not None:
                supa_state = confirmed
                last_heartbeat_ts = ts
                supabase_client.push_alert_transition(
                    {"episode_id": supa_episode_id, "ts": ts, "state": confirmed}
                )
        else:
            new_severity = severity.get(confirmed, 0)
            current_severity = severity.get(supa_state, 0)
            if new_severity > current_severity and supa_episode_id is not None:
                supa_state = confirmed
                last_heartbeat_ts = ts
                supabase_client.update_alert_episode(
                    supa_episode_id, last_updated_ts=ts, current_state=confirmed
                )
                supabase_client.push_alert_transition(
                    {"episode_id": supa_episode_id, "ts": ts, "state": confirmed}
                )
    if supa_episode_id is not None and supa_state is not None:
        if last_heartbeat_ts is None or (ts - last_heartbeat_ts) >= HEARTBEAT_S:
            last_heartbeat_ts = ts
            supabase_client.update_alert_episode(
                supa_episode_id, last_updated_ts=ts, current_state=supa_state
            )
    sleep(0.1)  # speed up


sleep(5)
print("ALARM OFF")
toggle_buzzer.stop()