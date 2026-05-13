
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
_command_queue: queue.Queue = None


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

    _sync_pending_episodes(db_conn)
    _check_episode_commands(db_conn)
    _sync_pending_headcount_logs(db_conn)


def _sync_pending_episodes(db_conn):
    """Push any active episodes that failed to reach Supabase (e.g. device was offline)."""
    try:
        pending = db.fetch_episodes_without_supabase_id(db_conn)
        if not pending:
            return

        for episode in pending:
            try:
                supa_id = supabase_client.push_alert_episode({
                    "started_ts":      episode["started_ts"],
                    "last_updated_ts": episode["last_updated_ts"],
                    "current_state":   episode["current_state"],
                    "status":          episode["status"],
                })
                if supa_id is not None:
                    db.set_supabase_episode_id(db_conn, episode["id"], supa_id)
                    try:
                        print(f"[Sync] ✅ Episode {episode['id']} pushed to Supabase (id={supa_id})")
                    except (OSError, ValueError):
                        pass
                else:
                    try:
                        print(f"[Sync] ⚠️ Episode {episode['id']} push failed, will retry next cycle")
                    except (OSError, ValueError):
                        pass
            except Exception as e:
                try:
                    print(f"[Sync] Episode {episode['id']} sync error: {e}")
                except (OSError, ValueError):
                    pass

    except Exception as e:
        try:
            print(f"[Sync] _sync_pending_episodes failed: {e}")
        except (OSError, ValueError):
            pass


def _check_episode_commands(db_conn) -> None:
    """Fallback: poll Supabase for pending commands on the active episode (runs every 30s)."""
    if _command_queue is None:
        print("[Sync] Fallback skipped: _command_queue is None (was sync_worker.start called with command_queue?)")
        return

    row = db.fetch_active_episode(db_conn)
    if row is None:
        print("[Sync] Fallback skipped: no active episode in SQLite")
        return

    supa_id = row["supabase_episode_id"]
    if supa_id is None:
        print(f"[Sync] Fallback skipped: SQLite episode {row['id']} has no supabase_episode_id yet")
        return

    fields = supabase_client.fetch_episode_fields(supa_id)
    if fields is None:
        print(f"[Sync] Fallback skipped: Supabase unreachable for episode {supa_id}")
        return

    status = fields.get("status")
    buzzer_muted = fields.get("buzzer_muted")
    buzzer_status_remote = fields.get("buzzer_status")
    print(f"[Sync] Fallback poll: episode={supa_id} status={status} buzzer_muted={buzzer_muted} buzzer_status={buzzer_status_remote}")

    if status in ("resolved", "false_alarm"):
        _command_queue.put({"action": status})
        try:
            print(f"[Sync] Fallback: episode {supa_id} has status='{status}', queuing command")
        except (OSError, ValueError):
            pass
    elif buzzer_muted is True and buzzer_status_remote == "on":
        _command_queue.put({"action": "mute_buzzer"})
        try:
            print(f"[Sync] Fallback: buzzer mute pending for episode {supa_id}, queuing command")
        except (OSError, ValueError):
            pass
    elif buzzer_muted is False and buzzer_status_remote == "muted":
        _command_queue.put({"action": "unmute_buzzer"})
        try:
            print(f"[Sync] Fallback: buzzer unmute pending for episode {supa_id}, queuing command")
        except (OSError, ValueError):
            pass
    elif fields.get("headcount_requested") is True:
        _command_queue.put({"action": "trigger_headcount"})
        supabase_client.update_alert_episode(supa_id, headcount_requested=False)
        try:
            print(f"[Sync] Fallback: headcount requested for episode {supa_id}, queuing command")
        except (OSError, ValueError):
            pass


def _sync_pending_headcount_logs(db_conn) -> None:
    """Retry headcount logs that failed to reach Supabase (e.g. device was offline)."""
    try:
        from pathlib import Path
        pending = db.fetch_unsynced_headcount_logs(db_conn)
        if not pending:
            return

        for log in pending:
            try:
                annotated_path = Path(log["annotated_path"]) if log["annotated_path"] else None
                image_url = None
                if annotated_path and annotated_path.exists():
                    image_url = supabase_client.upload_headcount_image(annotated_path, annotated_path.name)

                success = supabase_client.push_headcount_log(
                    ts=log["ts"],
                    high_count=log["high_count"],
                    mid_count=log["mid_count"],
                    low_count=log["low_count"],
                    total_count=log["total_count"],
                    trigger_source=log["trigger_source"],
                    episode_id=log["supabase_episode_id"],
                    image_url=image_url,
                )
                if success:
                    db.mark_headcount_log_synced(db_conn, log["id"], image_url)
                    try:
                        print(f"[Sync] ✅ Headcount log {log['id']} synced to Supabase")
                    except (OSError, ValueError):
                        pass
                else:
                    try:
                        print(f"[Sync] ⚠️ Headcount log {log['id']} sync failed, will retry next cycle")
                    except (OSError, ValueError):
                        pass
            except Exception as e:
                try:
                    print(f"[Sync] Headcount log {log['id']} sync error: {e}")
                except (OSError, ValueError):
                    pass

    except Exception as e:
        try:
            print(f"[Sync] _sync_pending_headcount_logs failed: {e}")
        except (OSError, ValueError):
            pass


def push_live(row: dict) -> None:
    try:
        _live_push_queue.put_nowait(row)
    except queue.Full:
        pass  # queue full — sync_worker will catch it on next batch cycle


def push_episode_update(episode_id: int, ts: float, current_state=None) -> None:
    try:
        _live_push_queue.put_nowait({
            "_type":           "episode_update",
            "episode_id":      episode_id,
            "last_updated_ts": ts,
            "current_state":   current_state,
        })
    except queue.Full:
        pass


def _live_push_loop(db_conn):
    while not _stop_event.is_set():
        try:
            row = _live_push_queue.get(timeout=1.0)
            if row.get("_type") == "episode_update":
                success = supabase_client.update_alert_episode(
                    row["episode_id"],
                    last_updated_ts=row["last_updated_ts"],
                    current_state=row["current_state"],
                )
                try:
                    if success:
                        print(f"[Supabase] ✅ Episode {row['episode_id']} updated (last_updated_ts={row['last_updated_ts']:.3f})")
                    else:
                        print(f"[Supabase] ⚠️ Episode {row['episode_id']} update failed")
                except (OSError, ValueError):
                    pass
            else:
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


def start(db_conn, command_queue: queue.Queue = None):
    global _sync_thread, _live_push_thread, _command_queue

    _stop_event.clear()
    _command_queue = command_queue
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