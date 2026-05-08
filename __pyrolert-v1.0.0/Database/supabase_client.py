import os
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Global Supabase client instance
_client: Optional[Client] = None


def get_client() -> Optional[Client]:
    """Get or initialize the Supabase client."""
    global _client
    if _client is None:
        try:
            _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            print("[Supabase] Client initialized ✅")
        except Exception as e:
            print(f"[Supabase] Failed to initialize client: {e}")
            _client = None
    return _client


def push_reading(row: dict) -> bool:
    """
    Push a single sensor reading to Supabase.
    Returns True if successful, False if failed.
    """
    client = get_client()
    if client is None:
        return False

    try:
        payload = {
            "ts":               float(row["ts"]),
            "gas_co":           row["gas_co"],
            "gas_no2":          row["gas_no2"],
            "gas_o2":           row["gas_o2"],
            "temp_c":           row["temp_c"],
            "temp_roc":         row.get("temp_roc"),
            "pm25":             row["pm25"],
            "detection_result": row["detection_result"],
        }
        client.table("sensor_readings").insert(payload).execute()
        return True
    except Exception as e:
        print(f"[Supabase] Push failed: {e}")
        return False


def push_readings_batch(rows: list) -> list[int]:
    """
    Push a batch of sensor readings to Supabase.
    Returns list of successfully pushed row ids.
    """
    client = get_client()
    if client is None:
        return []

    successful_ids = []

    for row in rows:
        try:
            temp_roc = row["temp_roc"] if "temp_roc" in row.keys() else None
            payload = {
                "ts":               float(row["ts"]),
                "gas_co":           row["gas_co"],
                "gas_no2":          row["gas_no2"],
                "gas_o2":           row["gas_o2"],
                "temp_c":           row["temp_c"],
                "temp_roc":         temp_roc,
                "pm25":             row["pm25"],
                "detection_result": row["detection_result"],
            }
            client.table("sensor_readings").insert(payload).execute()
            successful_ids.append(row["id"])
        except Exception as e:
            print(f"[Supabase] Batch push failed for id={row['id']}: {e}")
            continue  # skip failed row, try next one

    return successful_ids


def push_alert_episode(row: dict) -> Optional[int]:
    """Push a single alert episode to Supabase and return its id if available."""
    client = get_client()
    if client is None:
        return None

    try:
        payload = {
            "started_ts":      float(row["started_ts"]),
            "last_updated_ts": float(row["last_updated_ts"]),
            "current_state":   row["current_state"],
            "status":          row.get("status", "active"),
            "meta":            row.get("meta"),
        }
        response = client.table("alert_episodes").insert(payload).execute()
        if response.data:
            return int(response.data[0]["id"])
    except Exception as e:
        print(f"[Supabase] Alert episode push failed: {e}")
    return None


def push_alert_transition(row: dict) -> bool:
    """Push a single alert transition to Supabase; returns True if successful."""
    client = get_client()
    if client is None:
        return False

    try:
        payload = {
            "episode_id": row["episode_id"],
            "ts":         float(row["ts"]),
            "state":      row["state"],
            "meta":       row.get("meta"),
        }
        client.table("alert_transitions").insert(payload).execute()
        return True
    except Exception as e:
        print(f"[Supabase] Alert transition push failed: {e}")
        return False


def fetch_episode_status(episode_id: int) -> Optional[str]:
    """
    Fetch the current status of an alert episode from Supabase.
    Returns the status string, or None if unreachable or not found.
    """
    client = get_client()
    if client is None:
        return None

    try:
        response = (
            client.table("alert_episodes")
            .select("status")
            .eq("id", episode_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["status"]
    except Exception as e:
        print(f"[Supabase] fetch_episode_status failed: {e}")
    return None


def update_alert_episode(
    episode_id: int,
    last_updated_ts: Optional[float] = None,
    current_state: Optional[str] = None,
    status: Optional[str] = None,
    rpi_acknowledged_at: Optional[float] = None,
    buzzer_status: Optional[str] = None,
    meta: Optional[dict] = None,
) -> bool:
    """Update an alert episode in Supabase; returns True if successful."""
    from datetime import datetime, timezone

    client = get_client()
    if client is None:
        return False

    payload = {}
    if last_updated_ts is not None:
        payload["last_updated_ts"] = float(last_updated_ts)
    if current_state is not None:
        payload["current_state"] = current_state
    if status is not None:
        payload["status"] = status
    if rpi_acknowledged_at is not None:
        payload["rpi_acknowledged_at"] = datetime.fromtimestamp(
            rpi_acknowledged_at, tz=timezone.utc
        ).isoformat()
    if buzzer_status is not None:
        payload["buzzer_status"] = buzzer_status
    if meta is not None:
        payload["meta"] = meta

    try:
        client.table("alert_episodes").update(payload).eq("id", episode_id).execute()
        return True
    except Exception as e:
        print(f"[Supabase] Alert episode update failed: {e}")
        return False


def fetch_episode_fields(episode_id: int) -> Optional[dict]:
    """Fetch status, buzzer_muted, and buzzer_status for an episode (used by sync worker fallback)."""
    client = get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("alert_episodes")
            .select("status, buzzer_muted, buzzer_status")
            .eq("id", episode_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return dict(response.data[0])
    except Exception as e:
        print(f"[Supabase] fetch_episode_fields failed: {e}")
    return None