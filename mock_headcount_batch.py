import time
from pathlib import Path

from Database import db, supabase_client
from Headcount_Manager import HeadcountManager

# ── Configuration ─────────────────────────────────────────────────────────────
EPISODE_ID    = 167
IMAGE_DIR     = Path("for pyrolert testing 1")
# ──────────────────────────────────────────────────────────────────────────────

images = sorted(IMAGE_DIR.glob("*.jpg"))
if not images:
    print(f"[!] No .jpg images found in {IMAGE_DIR}/")
    exit(1)

print(f"\n================== Mock Headcount Batch (episode {EPISODE_ID}) ==================")
print(f"  Found {len(images)} image(s) in {IMAGE_DIR}/\n")

db_conn = db.init_db("Database/db_pyrolert.sqlite")
supabase_client.get_client()

headcount_manager = HeadcountManager(
    esp32_url="http://pyrolert-esp32cam.local",
    model_path=Path("Headcount_Manager/best.pt"),
    raw_output_dir=Path("Captures_RAW"),
    annotated_output_dir=Path("Captures_YOLO"),
    interval_s=30,
    db_conn=db_conn,
    show_labels=False,
)

headcount_manager.set_episode(supabase_episode_id=EPISODE_ID)

for i, image_path in enumerate(images, 1):
    print(f"[Batch] [{i}/{len(images)}] {image_path.name}")
    headcount_manager._mock_image_path = image_path
    headcount_manager.trigger_now()

    deadline = time.time() + 30
    while headcount_manager._busy and time.time() < deadline:
        time.sleep(0.5)

    if headcount_manager._busy:
        print(f"[Batch] [{i}/{len(images)}] timed out after 30s — skipping\n")
    else:
        print(f"[Batch] [{i}/{len(images)}] done\n")

print(f"================== Batch complete — {len(images)} image(s) sent to episode {EPISODE_ID} ==================")
