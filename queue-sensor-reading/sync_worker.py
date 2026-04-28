
import time
import threading
from datetime import datetime
import db
import supabase_client

# How often the background sync runs (in seconds)
SYNC_INTERVAL_S = 30

# How many rows to sync per batch
SYNC_BATCH_SIZE = 50

# Background thread reference
_sync_thread: threading.Thread = None
_stop_event = threading.Event()


def _sync_loop(db_conn):
    """Main sync loop that runs in the background thread."""
    print("[Sync] Background sync worker started ✅")

    while not _stop_event.is_set():
        try:
            _run_sync(db_conn)
        except Exception as e:
            print(f"[Sync] Unexpected error in sync loop: {e}")

        # Wait for next sync interval or until stop is requested
        _stop_event.wait(timeout=SYNC_INTERVAL_S)

    print("[Sync] Background sync worker stopped ✅")


def _run_sync(db_conn):
    """Fetch unsynced rows and push them to Supabase."""
    try:
        unsynced = db.fetch_unsynced_readings(db_conn, limit=SYNC_BATCH_SIZE)

        if not unsynced:
            return  # nothing to sync, skip silently

        print(f"[Sync] Found {len(unsynced)} unsynced rows, pushing to Supabase...")

        successful_ids = supabase_client.push_readings_batch(unsynced)

        if successful_ids:
            db.mark_as_synced(db_conn, successful_ids)
            print(f"[Sync] ✅ Synced {len(successful_ids)}/{len(unsynced)} rows at "
                  f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        failed_count = len(unsynced) - len(successful_ids)
        if failed_count > 0:
            print(f"[Sync] ⚠️ {failed_count} rows failed to sync, will retry next cycle")

    except Exception as e:
        print(f"[Sync] Sync run failed: {e}")


def start(db_conn):
    """Start the background sync worker thread."""
    global _sync_thread

    _stop_event.clear()
    _sync_thread = threading.Thread(
        target=_sync_loop,
        args=(db_conn,),
        daemon=True,  # thread dies automatically when main program exits
        name="SyncWorker"
    )
    _sync_thread.start()


def stop():
    """Stop the background sync worker thread gracefully."""
    _stop_event.set()
    if _sync_thread is not None:
        _sync_thread.join(timeout=5)
        print("[Sync] Sync worker stopped")