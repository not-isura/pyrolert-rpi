import time
from pathlib import Path

from Database import db, supabase_client
from Headcount_Manager import HeadcountManager

# ── Configuration ─────────────────────────────────────────────────────────────
EPISODE_ID         = 166   # Supabase episode id to link captures to
MOCK_CAPTURE_IMAGE = None  
# set to Path("../esp32_20260502_140319.jpg") to use static image

REQUEST_MODE = True   # True  = prompt "Capture? (y/n)" for each capture
                      # False = capture automatically every AUTO_INTERVAL_S seconds
AUTO_INTERVAL_S = 10
# ──────────────────────────────────────────────────────────────────────────────

mode_label = "Request" if REQUEST_MODE else f"Auto every {AUTO_INTERVAL_S}s"
print(f"\n================== Mock Headcount ({mode_label} | episode {EPISODE_ID}) ==================\n")

db_conn = db.init_db("Database/db_pyrolert.sqlite")
supabase_client.get_client()

headcount_manager = HeadcountManager(
    esp32_url="http://pyrolert-esp32cam.local",
    model_path=Path("Headcount_Manager/best.pt"),
    raw_output_dir=Path("Captures_RAW"),
    annotated_output_dir=Path("Captures_YOLO"),
    interval_s=AUTO_INTERVAL_S,
    db_conn=db_conn,
    show_labels=False,
    mock_image_path=MOCK_CAPTURE_IMAGE,
)

headcount_manager.set_episode(supabase_episode_id=EPISODE_ID)


def do_capture(count):
    headcount_manager.trigger_now()
    deadline = time.time() + 30
    while headcount_manager._busy and time.time() < deadline:
        time.sleep(0.5)
    if headcount_manager._busy:
        print(f"[Headcount] Capture #{count} timed out after 30s")


capture_count = 0

if REQUEST_MODE:
    while True:
        try:
            answer = input("Capture? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if answer == "y":
            capture_count += 1
            print(f"[Headcount] Capture #{capture_count} starting...")
            do_capture(capture_count)
            print(f"[Headcount] Capture #{capture_count} done — check the website\n")
        elif answer == "n":
            print(f"Done. {capture_count} capture(s) sent.")
            break
        else:
            print("Enter y or n.")

else:
    print(f"Auto mode — capturing every {AUTO_INTERVAL_S}s. Press Ctrl+C to stop.\n")
    try:
        while True:
            capture_count += 1
            print(f"[Headcount] Capture #{capture_count} starting...")
            do_capture(capture_count)
            print(f"[Headcount] Capture #{capture_count} done — check the website\n")
            for remaining in range(AUTO_INTERVAL_S, 0, -1):
                print(f"\r  Next capture in {remaining}s...  ", end="", flush=True)
                time.sleep(1)
            print()
    except KeyboardInterrupt:
        print(f"\nStopped. {capture_count} capture(s) sent.")

