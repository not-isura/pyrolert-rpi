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
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                  REAL NOT NULL,
                gas_co              REAL,
                gas_no2             REAL,
                gas_o2              REAL,
                temp_c              REAL,
                pm25                REAL,
                detection_result    TEXT,
                is_synced           INTEGER DEFAULT 0
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS head_detection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_ts INTEGER NOT NULL,
                ended_ts INTEGER,
                mode TEXT NOT NULL,
                interval_seconds INTEGER,
                trigger_type TEXT NOT NULL,
                trigger_detection_event_id INTEGER,
                status TEXT NOT NULL,
                meta TEXT,
                FOREIGN KEY (trigger_detection_event_id) REFERENCES detection_events(id)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_head_detection_runs_started_ts
            ON head_detection_runs (started_ts);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_head_detection_runs_trigger_detection_event_id
            ON head_detection_runs (trigger_detection_event_id);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS head_detection_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                ts INTEGER NOT NULL,
                sensor_reading_id INTEGER,
                headcount_conf30 INTEGER,
                headcount_conf60 INTEGER,
                result_label TEXT,
                meta TEXT,
                FOREIGN KEY (run_id) REFERENCES head_detection_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (sensor_reading_id) REFERENCES sensor_readings(id)
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_head_detection_results_ts
            ON head_detection_results (ts);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_head_detection_results_run_id
            ON head_detection_results (run_id);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_head_detection_results_sensor_reading_id
            ON head_detection_results (sensor_reading_id);
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
            (ts, gas_co, gas_no2, gas_o2, temp_c, pm25, detection_result),
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
            (ts, result, meta_text),
        )
    return int(cursor.lastrowid)


def insert_head_detection_run(
    conn: sqlite3.Connection,
    started_ts: float,
    mode: str,
    trigger_type: str,
    status: str,
    interval_seconds: Optional[int] = None,
    trigger_detection_event_id: Optional[int] = None,
    ended_ts: Optional[float] = None,
    meta: Optional[dict] = None,
) -> int:
    """Insert a head-detection run row and return the new row id."""
    meta_text = json.dumps(meta) if meta is not None else None
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO head_detection_runs (
                started_ts,
                ended_ts,
                mode,
                interval_seconds,
                trigger_type,
                trigger_detection_event_id,
                status,
                meta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                int(started_ts),
                int(ended_ts) if ended_ts is not None else None,
                mode,
                interval_seconds,
                trigger_type,
                trigger_detection_event_id,
                status,
                meta_text,
            ),
        )
    return int(cursor.lastrowid)


def complete_head_detection_run(
    conn: sqlite3.Connection,
    run_id: int,
    ended_ts: Optional[float] = None,
    status: str = "completed",
) -> int:
    """Mark a head-detection run as finished; returns affected row count."""
    actual_ended_ts = int(ended_ts) if ended_ts is not None else int(time.time())
    with conn:
        cursor = conn.execute(
            """
            UPDATE head_detection_runs
            SET ended_ts = ?, status = ?
            WHERE id = ?;
            """,
            (actual_ended_ts, status, run_id),
        )
    return cursor.rowcount


def insert_head_detection_result(
    conn: sqlite3.Connection,
    run_id: int,
    ts: float,
    headcount_conf30: Optional[int],
    headcount_conf60: Optional[int],
    sensor_reading_id: Optional[int] = None,
    result_label: Optional[str] = None,
    meta: Optional[dict] = None,
) -> int:
    """Insert one head-detection result and return the new row id."""
    meta_text = json.dumps(meta) if meta is not None else None
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO head_detection_results (
                run_id,
                ts,
                sensor_reading_id,
                headcount_conf30,
                headcount_conf60,
                result_label,
                meta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run_id,
                ts,
                sensor_reading_id,
                headcount_conf30,
                headcount_conf60,
                result_label,
                meta_text,
            ),
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


def fetch_recent_head_detection_results(
    conn: sqlite3.Connection,
    limit: int = 100,
    run_id: Optional[int] = None,
    after_ts: Optional[float] = None,
) -> List[sqlite3.Row]:
    """Return recent head-detection result rows ordered by newest first."""
    query = "SELECT * FROM head_detection_results"
    params: List[object] = []
    clauses: List[str] = []

    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if after_ts is not None:
        clauses.append("ts > ?")
        params.append(int(after_ts))

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

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


def prune_head_detection_results_older_than(
    conn: sqlite3.Connection,
    days: float,
    now: Optional[float] = None,
) -> int:
    """Delete head-detection results older than N days; returns deleted row count."""
    current = now if now is not None else time.time()
    cutoff = int(current - days * 86400)
    with conn:
        cursor = conn.execute("DELETE FROM head_detection_results WHERE ts < ?;", (cutoff,))
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

def fetch_unsynced_readings(
    conn: sqlite3.Connection,
    limit: int = 50,
) -> List[sqlite3.Row]:
    """Return unsynced readings ordered by oldest first for batch sync."""
    cursor = conn.execute(
        """
        SELECT * FROM sensor_readings
        WHERE is_synced = 0
        ORDER BY ts ASC
        LIMIT ?;
        """,
        (limit,),
    )
    return list(cursor.fetchall())


def mark_as_synced(
    conn: sqlite3.Connection,
    row_ids: List[int],
) -> int:
    """Mark a list of row ids as synced; returns affected row count."""
    if not row_ids:
        return 0
    placeholders = ",".join("?" * len(row_ids))
    with conn:
        cursor = conn.execute(
            f"UPDATE sensor_readings SET is_synced = 1 WHERE id IN ({placeholders});",
            row_ids,
        )
    return cursor.rowcount