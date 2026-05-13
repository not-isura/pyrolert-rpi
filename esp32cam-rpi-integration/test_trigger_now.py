import time
import threading
from pathlib import Path
from headcount_manager import HeadcountManager

ESP32_URL            = "http://pyrolert-esp32cam.local"
MODEL_PATH           = Path("best.pt")
YOLO_CAPTURES_DIR    = Path("yolo_captures")
HEADCOUNT_INTERVAL_S = 30

# Fire trigger_now() at these seconds after the script starts
MANUAL_TRIGGER_AT_S  = [10, 20, 54]  # mid-countdown triggers


def schedule_manual_triggers(manager: HeadcountManager, trigger_times: list[int]) -> None:
    def fire(delay: int) -> None:
        time.sleep(delay)
        print(f"\n[Manual] trigger_now() fired at t={delay}s  ← simulates website button\n")
        manager.trigger_now()

    for t in trigger_times:
        threading.Thread(target=fire, args=(t,), daemon=True).start()


if __name__ == "__main__":
    manager = HeadcountManager(
        esp32_url=ESP32_URL,
        model_path=MODEL_PATH,
        output_dir=YOLO_CAPTURES_DIR,
        interval_s=HEADCOUNT_INTERVAL_S,
    )

    schedule_manual_triggers(manager, MANUAL_TRIGGER_AT_S)

    print(f"Simulation started.")
    print(f"  Passive interval : every {HEADCOUNT_INTERVAL_S}s via trigger_if_due()")
    print(f"  Manual triggers  : trigger_now() at t={MANUAL_TRIGGER_AT_S}s")
    print(f"  Ctrl+C to stop\n")

    start = time.time()
    while True:
        elapsed = time.time() - start
        manager.trigger_if_due(time.time())
        print(f"[Loop] t={elapsed:.0f}s", end="\r")
        time.sleep(1)
