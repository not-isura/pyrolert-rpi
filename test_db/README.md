# Test DB helpers (quick guide)

This folder has three small pieces to learn SQLite with mocked sensor data before wiring real hardware.

- **db.py** — SQLite helper. Opens/creates the database, applies pragmas (WAL + busy timeout), creates tables, and exposes functions:
  - `init_db(db_path)` — get a connection with schema ensured.
  - `insert_reading(...)` — add one sensor row (CO, NO2, O2, temp, pm25 as REAL, detection_result string).
  - `insert_detection(...)` — add a detection event with optional JSON metadata.
  - `fetch_recent_readings(limit, after_ts)` — newest-first rows.
  - `prune_older_than(days)` / `prune_detections_older_than(days)` — delete old rows.
  - `bulk_insert_mock_readings(rows)` — insert a list/iterator of reading dicts.

- **mock_sensor_logger.py** — Mock data producer. Generates random per-second sensor readings and writes them with `insert_reading`. Prints the last few rows when it stops.

- **test_db.py** — Pytest checks to make sure the helper works (schema exists, inserts/fetch order, pruning, bulk insert, detection events).

## What init_db does

`init_db(db_path, enable_wal=True, busy_timeout_ms=5000)` is the main setup function for SQLite.

When you call it, it does 4 things for you:

1. Opens (or creates) the SQLite file at `db_path`.
2. Configures the connection:
  - `check_same_thread=False` allows use across threads.
  - `row_factory=sqlite3.Row` lets you read rows by column name (for example `row["pm25"]`).
3. Applies DB runtime settings through `_apply_pragmas(...)`:
  - WAL mode (optional) for better read/write behavior.
  - Busy timeout to reduce `database is locked` errors.
  - Foreign keys ON.
4. Ensures required tables/indexes exist via `_ensure_schema(...)`.

It then returns a ready-to-use connection object, so your app can immediately insert and query data.

## How to run (from repo root)

1) Install pytest if needed: `python -m pip install pytest`

2) Run tests:
- `python -m pytest test_db/test_db.py`

3) Generate mock data into a DB file and see sample rows:
- `python -m mock_sensor_logger --db db.sqlite --limit 5`
  - `--limit 5` stops after 5 samples; omit to run continuously.
  - Change `--rate` to set samples per second (default 1 Hz).

4) Peek at the DB (optional):
- `sqlite3 db.sqlite "select * from sensor_readings limit 5;"`

## Mental model

- Start with mock data to learn SQLite. Real sensors can later call the same `insert_reading` API, so your scripts stay simple.
- `pm25` is stored as REAL (double precision) so you can compute on it easily.
- WAL + busy timeout makes reads/writes smoother on the Pi; keep or disable via `init_db(enable_wal=False)` if desired.


============
SQLITE
Display format for timestamp (ts) inside DB Browser
- `strftime('%m/%d/%Y %I:%M:%S %p', "ts", 'unixepoch', 'localtime')`

## New schema additions (head detection)

`db.py` now includes two new tables so the design supports both strategies:

- Occasional head detection (for example every 30s), then faster checks (for example every 5s) during high alert.
- No occasional checks, only run head detection when high alert is active.

### 1) head_detection_runs

Tracks each run session (when/why the head detector was executed).

- `id`
- `started_ts`
- `ended_ts`
- `mode` (for example: `scheduled`, `alert_burst`)
- `interval_seconds` (for example: `30`, `5`)
- `trigger_type` (for example: `timer`, `high_alert`, `manual`)
- `trigger_detection_event_id` (optional link to `detection_events.id`)
- `status` (for example: `running`, `completed`, `failed`)
- `meta` (optional JSON text)

### 2) head_detection_results

Stores each output produced by a run.

- `id`
- `run_id` (required FK to `head_detection_runs.id`)
- `ts`
- `sensor_reading_id` (optional FK to `sensor_readings.id`)
- `headcount_conf30`
- `headcount_conf60`
- `result_label` (optional)
- `meta` (optional JSON text)

### New helper functions in db.py

- `insert_head_detection_run(...)`
- `complete_head_detection_run(...)`
- `insert_head_detection_result(...)`
- `fetch_recent_head_detection_results(...)`
- `prune_head_detection_results_older_than(...)`

These additions are backward-compatible with existing sensor logging functions.

## Minimal usage flow for head detection

1. Insert a sensor reading -> keep returned `sensor_reading_id`.
2. Create a run with `insert_head_detection_run(...)` -> get `run_id`.
3. Insert one or more results with `insert_head_detection_result(..., run_id=..., sensor_reading_id=...)`.
4. Mark run complete with `complete_head_detection_run(...)`.
