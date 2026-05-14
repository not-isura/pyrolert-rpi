import queue
import random
from pathlib import Path
from time import time, sleep

from Database import db, supabase_client, sync_worker, realtime_listener
from alert_logic import AlertEpisodeManager, SlidingWindowAlert, pyrolert_detection_result
from Helpers_Actuators import ToggleBuzzer, ToggleLED
from Headcount_Manager import HeadcountManager

WINDOW_SIZE = 20
HIGH_ALERT_THRESHOLD = 12
WARNING_THRESHOLD = 12
BUZZER_PIN = 22
LED_PIN = 23
ESP32_URL = "http://pyrolert-esp32cam.local"
HEADCOUNT_INTERVAL_S = 30

toggle_buzzer = ToggleBuzzer(BUZZER_PIN)
toggle_led = ToggleLED(LED_PIN)

db_conn = db.init_db("Database/db_pyrolert.sqlite")
supabase_client.get_client()

command_queue = queue.Queue()
realtime_listener.start(command_queue)
sync_worker.start(db_conn, command_queue)

window = SlidingWindowAlert(WINDOW_SIZE, HIGH_ALERT_THRESHOLD, WARNING_THRESHOLD)
toggle_led.start()
headcount_manager = HeadcountManager(
    esp32_url=ESP32_URL,
    model_path=Path("Headcount_Manager/best.pt"),
    raw_output_dir=Path("Captures_RAW"),
    annotated_output_dir=Path("Captures_YOLO"),
    interval_s=HEADCOUNT_INTERVAL_S,
    db_conn=db_conn,
    show_labels=False,
)
alert_manager = AlertEpisodeManager(
    db_conn,
    buzzer=toggle_buzzer,
    led=toggle_led,
    command_queue=command_queue,
    on_episode_created=realtime_listener.set_episode,
    headcount_manager=headcount_manager,
)


# --- Sensor value generators ---
# Each generator produces values that deterministically evaluate to the target state.

def _normal():
    # CO<25, NO2<0.2, O2>=19 → always "Normal"
    return dict(
        gas_co=random.uniform(3.0, 8.0),
        gas_no2=random.uniform(0.02, 0.08),
        gas_o2=random.uniform(20.5, 21.0),
        pm25=random.uniform(5.0, 15.0),
        temp_c=random.uniform(22.0, 28.0),
        temp_roc=random.uniform(0.0, 0.5),
    )

def _warning():
    # (CO>=25 AND NO2>=0.2) AND O2<19 AND temp>57.2 AND pm25>=90 → always "Warning"
    return dict(
        gas_co=random.uniform(25.0, 45.0),
        gas_no2=random.uniform(0.20, 0.60),
        gas_o2=random.uniform(17.5, 18.9),
        pm25=random.uniform(90.0, 140.0),
        temp_c=random.uniform(58.0, 65.0),
        temp_roc=random.uniform(8.0, 12.0),
    )

def _high_alert():
    # (CO>=60 AND NO2>=1) AND O2<18 AND temp>57.2 AND pm25>=150 → always "High Alert"
    return dict(
        gas_co=random.uniform(60.0, 100.0),
        gas_no2=random.uniform(1.00, 2.00),
        gas_o2=random.uniform(15.0, 17.9),
        pm25=random.uniform(150.0, 300.0),
        temp_c=random.uniform(65.0, 80.0),
        temp_roc=random.uniform(12.0, 20.0),
    )


def _sensor_values_for(reading_num: int) -> dict:
    if reading_num <= 20:
        # Phase 1 (0-20s): all normal
        return _normal()
    elif reading_num <= 40:
        # Phase 2 (21-40s): alternate Warning/Normal
        # 10 warnings in 20 readings → max warn count stays at 10, below threshold of 12, no trigger
        return _warning() if reading_num % 2 == 1 else _normal()
    elif reading_num <= 60:
        # Phase 3 (41-60s): steady warning
        # warn count hits 12 at ~reading 42 → episode created
        return _warning()
    elif reading_num <= 90:
        # Phase 4 (61-90s): steady high alert
        # high count hits 12 at ~reading 72 → episode escalates
        return _high_alert()
    elif reading_num <= 120:
        # Phase 5 (91-120s): cycle High Alert → Warning → Normal
        # individual readings fluctuate; window may still confirm Warning or None
        return [_high_alert, _warning, _normal][(reading_num - 91) % 3]()
    else:
        # Phase 6 (121-150s): steady normal
        return _normal()


def _phase_label(reading_num: int) -> str:
    if reading_num <= 20:   return "Phase 1  | Normal"
    if reading_num <= 40:   return "Phase 2  | Fluctuating W/N"
    if reading_num <= 60:   return "Phase 3  | Steady Warning"
    if reading_num <= 90:   return "Phase 4  | Steady High Alert"
    if reading_num <= 120:  return "Phase 5  | Fluctuating HA/W/N"
    return                         "Phase 6  | Steady Normal"


print("\n================== Mock Full Trial (150s) ==================\n")

for i in range(1, 451):
    ts = float(time())
    sensors = _sensor_values_for(i)

    detection_result = pyrolert_detection_result(
        gas_co=sensors['gas_co'],
        gas_no2=sensors['gas_no2'],
        gas_o2=sensors['gas_o2'],
        pm25=sensors['pm25'],
        temp_c=sensors['temp_c'],
        temp_roc=sensors['temp_roc'],
    )

    confirmed = window.add(detection_result)
    normal_count, warning_count, high_count = window.counts()

    print(f"[{i:03d}] {_phase_label(i)}")
    # print(f"      CO={sensors['gas_co']:.1f}  NO2={sensors['gas_no2']:.2f}  O2={sensors['gas_o2']:.1f}  PM2.5={sensors['pm25']:.1f}  Temp={sensors['temp_c']:.1f}  RoC={sensors['temp_roc']:.1f}")
    # print(f"      det={detection_result:<12}  confirmed={str(confirmed):<12}  window[N={normal_count} W={warning_count} HA={high_count}]")

    alert_manager.handle(confirmed, ts)
    alert_manager.process_commands()
    headcount_manager.trigger_if_due(ts)

    if db_conn is not None:
        try:
            row_id = db.insert_reading(
                conn=db_conn,
                ts=ts,
                gas_co=sensors['gas_co'],
                gas_no2=sensors['gas_no2'],
                gas_o2=sensors['gas_o2'],
                temp_c=sensors['temp_c'],
                temp_roc=sensors['temp_roc'],
                pm25=sensors['pm25'],
                detection_result=detection_result,
            )
            sync_worker.push_live({
                "_type":            "reading",
                "id":               row_id,
                "ts":               ts,
                "gas_co":           sensors['gas_co'],
                "gas_no2":          sensors['gas_no2'],
                "gas_o2":           sensors['gas_o2'],
                "temp_c":           sensors['temp_c'],
                "temp_roc":         sensors['temp_roc'],
                "pm25":             sensors['pm25'],
                "detection_result": detection_result,
            })
        except Exception as db_err:
            print(f"      [!] DB/push error: {db_err}")

    sleep(1)


sleep(5)
print("\n================== Mock trial complete ==================")
toggle_buzzer.stop()
toggle_led.stop()
realtime_listener.stop()
sync_worker.stop()
