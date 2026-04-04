import time
import db


def test_init_creates_tables(tmp_path):
	db_path = tmp_path / "test.sqlite"
	conn = db.init_db(str(db_path), enable_wal=False)

	tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
	assert "sensor_readings" in tables
	assert "detection_events" in tables


def test_insert_and_fetch_order(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	ts = int(time.time())

	first_id = db.insert_reading(conn, ts, 1.0, 0.02, 20.5, 26.0, 8.0, "normal")
	second_id = db.insert_reading(conn, ts + 1, 2.0, 0.03, 20.4, 26.1, 12.0, "alert")

	rows = db.fetch_recent_readings(conn, limit=2)
	assert len(rows) == 2
	assert rows[0]["id"] == second_id
	assert rows[0]["detection_result"] == "alert"
	assert rows[1]["id"] == first_id
	assert rows[1]["gas_co"] == 1.0


def test_prune_older_than(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	now = 1_000_000
	old_ts = now - int(4 * 86400)
	new_ts = now - int(1 * 86400)

	db.insert_reading(conn, old_ts, 1.0, 0.02, 20.5, 26.0, 8.0, "normal")
	db.insert_reading(conn, new_ts, 1.1, 0.02, 20.6, 25.9, 9.0, "normal")

	deleted = db.prune_older_than(conn, days=3, now=now)
	remaining = conn.execute("SELECT COUNT(*) FROM sensor_readings;").fetchone()[0]

	assert deleted == 1
	assert remaining == 1


def test_bulk_insert_mock_readings(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	base_ts = int(time.time())
	payload = [
		{"ts": base_ts, "gas_co": 0.5, "gas_no2": 0.01, "gas_o2": 20.5, "temp_c": 25.0, "pm25": 5.0, "detection_result": "normal"},
		{"ts": base_ts + 1, "gas_co": 3.0, "gas_no2": 0.05, "gas_o2": 20.0, "temp_c": 27.0, "pm25": 40.0, "detection_result": "alert"},
	]

	inserted = db.bulk_insert_mock_readings(conn, payload)
	rows = db.fetch_recent_readings(conn, limit=5)

	assert inserted == 2
	assert len(rows) == 2
	assert rows[0]["detection_result"] == "alert"
	assert rows[1]["pm25"] == 5.0


def test_insert_detection_event(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	ts = int(time.time())

	event_id = db.insert_detection(conn, ts, "alert", meta={"reason": "mock"})
	row = conn.execute("SELECT id, ts, result, meta FROM detection_events WHERE id = ?;", (event_id,)).fetchone()

	assert row is not None
	assert row["result"] == "alert"
	assert "mock" in row["meta"]
