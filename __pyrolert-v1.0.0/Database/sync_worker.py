
import queue
import threading
from datetime import datetime
from . import db
from . import supabase_client

# How often the background sync runs (in seconds)
SYNC_INTERVAL_S = 30

# How many rows to sync per batch
SYNC_BATCH_SIZE = 50

# Background thread references
_sync_thread: threading.Thread = None
_live_push_thread: threading.Thread = None
_stop_event = threading.Event()
_live_push_queue: queue.Queue = queue.Queue(maxsize=100)


def _sync_loop(db_conn):
    try:
        print("[Sync] Background sync worker started ✅\n")
    except (OSError, ValueError):
        pass

    while not _stop_event.is_set():
        try:
            _run_sync(db_conn)
        except Exception as e:
            try:
                print(f"[Sync] Unexpected error in sync loop: {e}")
            except (OSError, ValueError):
                pass

        _stop_event.wait(timeout=SYNC_INTERVAL_S)

    try:
        print("[Sync] Background sync worker stopped ✅")
    except (OSError, ValueError):
        pass


def _run_sync(db_conn):
    """Fetch unsynced rows and push them to Supabase."""
    try:
        unsynced = db.fetch_unsynced_readings(db_conn, limit=SYNC_BATCH_SIZE)

        if not unsynced:
            return  # nothing to sync, skip silently

        try:
            print(f"[Sync] Found {len(unsynced)} unsynced rows, pushing to Supabase...")
        except (OSError, ValueError):
            pass

        successful_ids = supabase_client.push_readings_batch(unsynced)

        if successful_ids:
            db.mark_as_synced(db_conn, successful_ids)
            try:
                print(f"[Sync] ✅ Synced {len(successful_ids)}/{len(unsynced)} rows at "
                      f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            except (OSError, ValueError):
                pass

        failed_count = len(unsynced) - len(successful_ids)
        if failed_count > 0:
            try:
                print(f"[Sync] ⚠️ {failed_count} rows failed to sync, will retry next cycle")
            except (OSError, ValueError):
                pass

    except Exception as e:
        try:
            print(f"[Sync] Sync run failed: {e}")
        except (OSError, ValueError):
            pass


def push_live(row: dict) -> None:
    try:
        _live_push_queue.put_nowait(row)
    except queue.Full:
        pass  # queue full — sync_worker will catch it on next batch cycle


def _live_push_loop(db_conn):
    while not _stop_event.is_set():
        try:
            row = _live_push_queue.get(timeout=1.0)
            success = supabase_client.push_reading(row)
            try:
                if success:
                    db.mark_as_synced(db_conn, [row["id"]])
                    print("[Supabase] ✅ Live push successful")
                else:
                    print("[Supabase] ⚠️ Live push failed, will retry via sync worker")
            except (OSError, ValueError):
                pass
        except queue.Empty:
            continue
        except Exception as e:
            try:
                print(f"[LivePush] Error: {e}")
            except (OSError, ValueError):
                pass


def start(db_conn):
    global _sync_thread, _live_push_thread

    _stop_event.clear()
    _sync_thread = threading.Thread(
        target=_sync_loop, args=(db_conn,), daemon=True, name="SyncWorker"
    )
    _live_push_thread = threading.Thread(
        target=_live_push_loop, args=(db_conn,), daemon=True, name="LivePushWorker"
    )
    _sync_thread.start()
    _live_push_thread.start()


def stop():
    _stop_event.set()
    if _sync_thread is not None:
        _sync_thread.join(timeout=5)
    if _live_push_thread is not None:
        _live_push_thread.join(timeout=5)
    print("[Sync] Workers stopped")