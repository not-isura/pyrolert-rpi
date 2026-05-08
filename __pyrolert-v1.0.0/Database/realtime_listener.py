import asyncio
import queue
import threading

_stop_event = threading.Event()
_current_episode_id = None
_id_lock = threading.Lock()
_thread = None


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
    record = payload.get("new") or {}
    episode_id = record.get("id")

    with _id_lock:
        current = _current_episode_id

    if current is None or episode_id != current:
        return

    status = record.get("status")
    buzzer_muted = record.get("buzzer_muted")
    buzzer_status_remote = record.get("buzzer_status")

    if status in ("resolved", "false_alarm"):
        command_queue.put({"action": status})
        print(f"[Realtime] Command received: {status}")
    elif buzzer_muted is True and buzzer_status_remote == "on":
        command_queue.put({"action": "mute_buzzer"})
        print("[Realtime] Command received: mute_buzzer")
    elif buzzer_muted is False and buzzer_status_remote == "muted":
        command_queue.put({"action": "unmute_buzzer"})
        print("[Realtime] Command received: unmute_buzzer")


def _listener_thread(command_queue: queue.Queue) -> None:
    try:
        asyncio.run(_run(command_queue))
    except Exception as e:
        print(f"[Realtime] Listener thread error: {e}")


async def _run(command_queue: queue.Queue) -> None:
    from Database import supabase_client

    client = supabase_client.get_client()
    if client is None:
        print("[Realtime] Supabase client unavailable — listener not started")
        return

    channel = client.channel("alert_episodes_commands")
    channel.on_postgres_changes(
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
