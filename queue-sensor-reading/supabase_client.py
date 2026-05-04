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