import time
from pathlib import Path

from Database import db, supabase_client
from Headcount_Manager import HeadcountManager

# ── Configuration ─────────────────────────────────────────────────────────────
MOCK_CAPTURE_IMAGE = None  # set to None to use real ESP32-CAM
NUM_CAPTURES       = 3    # how many captures to run
CAPTURE_INTERVAL_S = 5    # seconds between captures
MOCK_EPISODE_ID    = None # Supabase episode id to link logs to (None = unlinked)
# ──────────────────────────────────────────────────────────────────────────────

db_conn = db.init_db("Database/db_pyrolert.sqlite")
supabase_client.get_client()

headcount_manager = HeadcountManager(
    esp32_url="http://pyrolert-esp32cam.local",
    model_path=Path("Headcount_Manager/best.pt"),
    raw_output_dir=Path("Captures_RAW"),
    annotated_output_dir=Path("Captures_YOLO"),
    interval_s=CAPTURE_INTERVAL_S,
    db_conn=db_conn,
    show_labels=True,
    mock_image_path=MOCK_CAPTURE_IMAGE,
    #resize=[640, 640],
)

if MOCK_EPISODE_ID is not None:
    headcount_manager.set_episode(MOCK_EPISODE_ID)

print(f"\n================== Mock Headcount Trial ({NUM_CAPTURES} capture(s)) ==================\n")

for i in range(1, NUM_CAPTURES + 1):
    print(f"[Trial] ── Capture {i}/{NUM_CAPTURES} ──────────────────────────────────")
    headcount_manager.trigger_now()

    # Poll _busy until the capture thread finishes (max 30s)
    deadline = time.time() + 30
    while headcount_manager._busy and time.time() < deadline:
        time.sleep(0.5)

    if headcount_manager._busy:
        print(f"[Trial] Capture {i} timed out after 30s — still running in background")

    if i < NUM_CAPTURES:
        print(f"[Trial] Waiting {CAPTURE_INTERVAL_S}s...\n")
        time.sleep(CAPTURE_INTERVAL_S)

print("\n================== Mock headcount trial complete ==================")
