import json
import sqlite3
import time
from typing import Iterable, List, Optional


def init_db(db_path: str, enable_wal: bool = True, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    """Create or open the database, apply pragmas, and ensure schema exists."""
    conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn, enable_wal, busy_timeout_ms)
    _ensure_schema(conn)
    return conn


def _apply_pragmas(conn: sqlite3.Connection, enable_wal: bool, busy_timeout_ms: int) -> None:
    if enable_wal:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    # sqlite does not accept parameters in PRAGMA statements, so interpolate the int
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)};")
    conn.execute("PRAGMA foreign_keys = ON;")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                gas_co REAL,
                gas_no2 REAL,
                gas_o2 REAL,
                temp_c REAL,
                pm25 REAL,
                detection_result TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_ts
            ON sensor_readings (ts);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                result TEXT NOT NULL,
                meta TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_detection_events_ts
            ON detection_events (ts);
            """
        )


def insert_reading(
    conn: sqlite3.Connection,
    ts: float,
    gas_co: Optional[float],
    gas_no2: Optional[float],
    gas_o2: Optional[float],
    temp_c: Optional[float],
    pm25: Optional[float],
    detection_result: Optional[str],
) -> int:
    """Insert a sensor reading row and return the new row id."""
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO sensor_readings (ts, gas_co, gas_no2, gas_o2, temp_c, pm25, detection_result)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (int(ts), gas_co, gas_no2, gas_o2, temp_c, pm25, detection_result),
        )
    return int(cursor.lastrowid)


def insert_detection(
    conn: sqlite3.Connection,
    ts: float,
    result: str,
    meta: Optional[dict] = None,
) -> int:
    """Insert a detection event row and return the new row id."""
    meta_text = json.dumps(meta) if meta is not None else None
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO detection_events (ts, result, meta)
            VALUES (?, ?, ?);
            """,
            (int(ts), result, meta_text),
        )
    return int(cursor.lastrowid)


def fetch_recent_readings(
    conn: sqlite3.Connection,
    limit: int = 100,
    after_ts: Optional[float] = None,
) -> List[sqlite3.Row]:
    """Return recent readings ordered by newest first."""
    query = "SELECT * FROM sensor_readings"
    params: List[object] = []
    if after_ts is not None:
        query += " WHERE ts > ?"
        params.append(int(after_ts))
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(query, params)
    return list(cursor.fetchall())


def prune_older_than(
    conn: sqlite3.Connection,
    days: float,
    now: Optional[float] = None,
) -> int:
    """Delete rows older than N days; returns number of deleted rows."""
    current = now if now is not None else time.time()
    cutoff = int(current - days * 86400)
    with conn:
        cursor = conn.execute("DELETE FROM sensor_readings WHERE ts < ?;", (cutoff,))
    return cursor.rowcount


def prune_detections_older_than(
    conn: sqlite3.Connection,
    days: float,
    now: Optional[float] = None,
) -> int:
    """Delete detection rows older than N days; returns number of deleted rows."""
    current = now if now is not None else time.time()
    cutoff = int(current - days * 86400)
    with conn:
        cursor = conn.execute("DELETE FROM detection_events WHERE ts < ?;", (cutoff,))
    return cursor.rowcount


def bulk_insert_mock_readings(
    conn: sqlite3.Connection,
    rows: Iterable[dict],
) -> int:
    """Insert a collection of mock reading dicts; returns count inserted."""
    count = 0
    with conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO sensor_readings (ts, gas_co, gas_no2, gas_o2, temp_c, pm25, detection_result)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    int(row.get("ts", time.time())),
                    row.get("gas_co"),
                    row.get("gas_no2"),
                    row.get("gas_o2"),
                    row.get("temp_c"),
                    row.get("pm25"),
                    row.get("detection_result"),
                ),
            )
            count += 1
    return count
