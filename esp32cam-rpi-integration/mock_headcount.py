import time
from pathlib import Path
from headcount_manager import HeadcountManager
from supabase_client import get_client

ESP32_URL            = "http://pyrolert-esp32cam.local"
MODEL_PATH           = Path("best.pt")
YOLO_CAPTURES_DIR    = Path("yolo_captures")
HEADCOUNT_INTERVAL_S = 30

if __name__ == "__main__":
    get_client()  # initialize and confirm Supabase connection at startup

    headcount_manager = HeadcountManager(
        esp32_url=ESP32_URL,
        model_path=MODEL_PATH,
        output_dir=YOLO_CAPTURES_DIR,
        interval_s=HEADCOUNT_INTERVAL_S,
        # resize=[640, 640],
        show_labels=False,
    )

    print(f"Passive headcount started — capturing every {HEADCOUNT_INTERVAL_S}s. Ctrl+C to stop.\n")
    while True:
        headcount_manager.trigger_if_due(time.time())
        time.sleep(1)
