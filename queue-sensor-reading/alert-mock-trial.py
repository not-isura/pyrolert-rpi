from time import time, sleep

import db
from alert_logic import AlertEpisodeManager, SlidingWindowAlert

from buzzer_toggle import ToggleBuzzer
toggle_buzzer = ToggleBuzzer(22)

WINDOW_SIZE = 20
HIGH_ALERT_THRESHOLD = 12
WARNING_THRESHOLD = 12


db_conn = db.init_db("db_pyrolert.sqlite")
window = SlidingWindowAlert(WINDOW_SIZE, HIGH_ALERT_THRESHOLD, WARNING_THRESHOLD)
alert_manager = AlertEpisodeManager(db_conn, buzzer=toggle_buzzer)

# 20 samples: 8 Normal + 12 Warning -> should confirm Warning
sequence = ["Normal"] * 8 + ["Warning"] * 8 + ["High Alert"] * 4 + ["Warning"] * 10 + ["Normal"] * 8 + ["High Alert"] * 15

for i, det in enumerate(sequence, 1):
    ts = time()
    confirmed = window.add(det)
    print(f"{i:02d}: det={det} confirmed={confirmed}")
    alert_manager.handle(confirmed, ts)
    sleep(1)  # speed up


sleep(5)
print("ALARM OFF")
toggle_buzzer.stop()