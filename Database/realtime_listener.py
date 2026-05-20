import asyncio
import queue
import threading

_stop_event = threading.Event()
_current_episode_id = None
_id_lock = threading.Lock()
_thread = None

# Track last-seen state to dedupe heartbeat events that don't change buzzer/status/headcount fields
_last_seen = {"episode_id": None, "status": None, "buzzer_muted": None, "buzzer_status": None, "headcount_requested": None}
_state_lock = threading.Lock()


def start(command_queue: queue.Queue) -> None:
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(
        target=_listener_thread,
        args=(command_queue,),
        daemon=True,
        name="RealtimeListener",
    )
    _thread.start()
    print("[Realtime] Listener thread started ✅")


def set_episode(supabase_episode_id: int) -> None:
    global _current_episode_id
    with _id_lock:
        _current_episode_id = supabase_episode_id
    print(f"[Realtime] Tracking episode id={supabase_episode_id}")


def stop() -> None:
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)


def _handle_payload(payload: dict, command_queue: queue.Queue) -> None:
    # supabase-py async realtime payload shapes have evolved across versions:
    #   newer: { "data": { "record": {...}, "old_record": {...}, ... } }
    #   older: { "new": {...}, "old": {...}, ... }
    record = (
        payload.get("new")
        or (payload.get("data") or {}).get("record")
        or {}
    )
    episode_id = record.get("id")

    with _id_lock:
        current = _current_episode_id

    print(f"[Realtime] Event received: episode_id={episode_id} tracking={current}")
    if episode_id is None:
        print(f"[Realtime] Raw payload (for debugging): {payload}")

    if current is None:
        print("[Realtime] Ignored — no episode tracked (set_episode never called)")
        return
    if episode_id != current:
        print(f"[Realtime] Ignored — id mismatch (got {episode_id}, tracking {current})")
        return

    status = record.get("status")
    buzzer_muted = record.get("buzzer_muted")
    buzzer_status_remote = record.get("buzzer_status")
    headcount_requested = record.get("headcount_requested")

    # Skip heartbeat events: if none of the fields we care about changed,
    # this update was just a last_updated_ts heartbeat — don't re-queue commands.
    with _state_lock:
        unchanged = (
            _last_seen["episode_id"] == episode_id
            and _last_seen["status"] == status
            and _last_seen["buzzer_muted"] == buzzer_muted
            and _last_seen["buzzer_status"] == buzzer_status_remote
            and _last_seen["headcount_requested"] == headcount_requested
        )
        _last_seen["episode_id"] = episode_id
        _last_seen["status"] = status
        _last_seen["buzzer_muted"] = buzzer_muted
        _last_seen["buzzer_status"] = buzzer_status_remote
        _last_seen["headcount_requested"] = headcount_requested

    if unchanged:
        # print("[Realtime] Skipping — heartbeat (no command-relevant change)")
        return

    print(f"[Realtime] Evaluating — status={status} buzzer_muted={buzzer_muted} buzzer_status={buzzer_status_remote} headcount_requested={headcount_requested}")

    if status in ("resolved", "false_alarm"):
        command_queue.put({"action": status})
        print(f"[Realtime] Command received: {status}")
    elif buzzer_muted is True and buzzer_status_remote == "on":
        command_queue.put({"action": "mute_buzzer"})
        print("[Realtime] Command received: mute_buzzer")
    elif buzzer_muted is False and buzzer_status_remote == "muted":
        command_queue.put({"action": "unmute_buzzer"})
        print("[Realtime] Command received: unmute_buzzer")
    elif headcount_requested is True:
        command_queue.put({"action": "trigger_headcount"})
        print("[Realtime] Command received: trigger_headcount")
        # Reset the flag immediately so repeated heartbeats don't re-queue
        from Database import supabase_client
        supabase_client.update_alert_episode(episode_id, headcount_requested=False)


def _listener_thread(command_queue: queue.Queue) -> None:
    try:
        asyncio.run(_run(command_queue))
    except Exception as e:
        print(f"[Realtime] Listener thread error: {e}")


async def _run(command_queue: queue.Queue) -> None:
    import os
    from dotenv import load_dotenv
    from supabase import acreate_client

    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        print("[Realtime] Missing SUPABASE_URL/SUPABASE_ANON_KEY — listener not started")
        return

    client = await acreate_client(url, key)
    print("[Realtime] Async client created")

    channel = client.channel("alert_episodes_commands")
    await channel.on_postgres_changes(
        event="UPDATE",
        schema="public",
        table="alert_episodes",
        callback=lambda payload: _handle_payload(payload, command_queue),
    ).subscribe()

    print("[Realtime] Subscribed to alert_episodes ✅")

    while not _stop_event.is_set():
        await asyncio.sleep(1)

    await client.remove_channel(channel)
    print("[Realtime] Unsubscribed")
