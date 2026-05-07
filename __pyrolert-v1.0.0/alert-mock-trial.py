from time import time, sleep

from Database import db, supabase_client, sync_worker
from alert_logic import AlertEpisodeManager, SlidingWindowAlert

from Helpers_Actuators import ToggleBuzzer, ToggleLED
toggle_buzzer = ToggleBuzzer(22)
toggle_led = ToggleLED(23)

WINDOW_SIZE = 20
HIGH_ALERT_THRESHOLD = 12
WARNING_THRESHOLD = 12

db_conn = db.init_db("Database/db_pyrolert.sqlite")
supabase_client.get_client()
sync_worker.start(db_conn)
window = SlidingWindowAlert(WINDOW_SIZE, HIGH_ALERT_THRESHOLD, WARNING_THRESHOLD)
toggle_led.start()
alert_manager = AlertEpisodeManager(db_conn, buzzer=toggle_buzzer, led=toggle_led)

# 20 samples: 8 Normal + 12 Warning -> should confirm Warning
# sequence = ["Normal"] * 8 + ["Warning"] * 8 + ["High Alert"] * 4 + ["Warning"] * 10 + ["Normal"] * 8 + ["High Alert"] * 15 + ["Warning"] * 15 + ["Normal"] * 28 + ["Warning"] * 15
sequence = ["Normal"] * 10 + ["Warning"] * 20 + ["High Alert"] * 20

for i, det in enumerate(sequence, 1):
    ts = time()
    print("timestamp:", ts)
    confirmed = window.add(det)
    print(f"{i:02d}: det={det} confirmed={confirmed}")
    alert_manager.handle(confirmed, ts)

    print("Delay:", time()-ts)
    sleep(1)


sleep(5)
print("ALARM OFF")
toggle_buzzer.stop()
toggle_led.stop()
sync_worker.stop()
