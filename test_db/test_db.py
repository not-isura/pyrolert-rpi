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


def test_new_head_detection_tables_exist(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}

	assert "head_detection_runs" in tables
	assert "head_detection_results" in tables


def test_insert_and_complete_head_detection_run(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	started_ts = int(time.time())

	run_id = db.insert_head_detection_run(
		conn,
		started_ts=started_ts,
		mode="alert_burst",
		trigger_type="high_alert",
		status="running",
		interval_seconds=5,
		meta={"source": "test"},
	)

	affected = db.complete_head_detection_run(conn, run_id=run_id, ended_ts=started_ts + 15, status="completed")
	row = conn.execute("SELECT status, ended_ts, mode, trigger_type FROM head_detection_runs WHERE id = ?;", (run_id,)).fetchone()

	assert affected == 1
	assert row is not None
	assert row["status"] == "completed"
	assert row["ended_ts"] == started_ts + 15
	assert row["mode"] == "alert_burst"
	assert row["trigger_type"] == "high_alert"


def test_insert_head_detection_result_with_links(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	now = int(time.time())

	reading_id = db.insert_reading(conn, now, 1.2, 0.03, 20.4, 26.5, 11.0, "alert")
	detection_event_id = db.insert_detection(conn, now, "high_alert", meta={"reason": "co"})
	run_id = db.insert_head_detection_run(
		conn,
		started_ts=now,
		mode="alert_burst",
		trigger_type="high_alert",
		status="running",
		interval_seconds=5,
		trigger_detection_event_id=detection_event_id,
	)

	result_id = db.insert_head_detection_result(
		conn,
		run_id=run_id,
		ts=now + 2,
		headcount_conf30=2,
		headcount_conf60=1,
		sensor_reading_id=reading_id,
		result_label="people_detected",
		meta={"model": "mock-v1"},
	)

	row = conn.execute(
		"SELECT run_id, sensor_reading_id, headcount_conf30, headcount_conf60, result_label, meta FROM head_detection_results WHERE id = ?;",
		(result_id,),
	).fetchone()

	assert row is not None
	assert row["run_id"] == run_id
	assert row["sensor_reading_id"] == reading_id
	assert row["headcount_conf30"] == 2
	assert row["headcount_conf60"] == 1
	assert row["result_label"] == "people_detected"
	assert "mock-v1" in row["meta"]


def test_fetch_recent_head_detection_results_filters(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	base_ts = int(time.time())

	run_a = db.insert_head_detection_run(conn, base_ts, "scheduled", "timer", "running", interval_seconds=30)
	run_b = db.insert_head_detection_run(conn, base_ts + 1, "alert_burst", "high_alert", "running", interval_seconds=5)

	db.insert_head_detection_result(conn, run_id=run_a, ts=base_ts + 10, headcount_conf30=1, headcount_conf60=1)
	db.insert_head_detection_result(conn, run_id=run_b, ts=base_ts + 20, headcount_conf30=3, headcount_conf60=2)

	rows = db.fetch_recent_head_detection_results(conn, limit=10, run_id=run_b, after_ts=base_ts + 15)

	assert len(rows) == 1
	assert rows[0]["run_id"] == run_b
	assert rows[0]["headcount_conf30"] == 3


def test_prune_head_detection_results_older_than(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	now = 1_000_000

	run_id = db.insert_head_detection_run(conn, started_ts=now, mode="scheduled", trigger_type="timer", status="running", interval_seconds=30)
	db.insert_head_detection_result(conn, run_id=run_id, ts=now - int(4 * 86400), headcount_conf30=1, headcount_conf60=1)
	db.insert_head_detection_result(conn, run_id=run_id, ts=now - int(1 * 86400), headcount_conf30=2, headcount_conf60=2)

	deleted = db.prune_head_detection_results_older_than(conn, days=3, now=now)
	remaining = conn.execute("SELECT COUNT(*) FROM head_detection_results;").fetchone()[0]

	assert deleted == 1
	assert remaining == 1


def test_delete_run_cascades_head_detection_results(tmp_path):
	conn = db.init_db(str(tmp_path / "test.sqlite"), enable_wal=False)
	now = int(time.time())

	run_id = db.insert_head_detection_run(
		conn,
		started_ts=now,
		mode="alert_burst",
		trigger_type="high_alert",
		status="running",
		interval_seconds=5,
	)
	db.insert_head_detection_result(conn, run_id=run_id, ts=now + 1, headcount_conf30=2, headcount_conf60=1)
	db.insert_head_detection_result(conn, run_id=run_id, ts=now + 2, headcount_conf30=3, headcount_conf60=2)

	before = conn.execute("SELECT COUNT(*) FROM head_detection_results WHERE run_id = ?;", (run_id,)).fetchone()[0]
	with conn:
		conn.execute("DELETE FROM head_detection_runs WHERE id = ?;", (run_id,))
	after = conn.execute("SELECT COUNT(*) FROM head_detection_results WHERE run_id = ?;", (run_id,)).fetchone()[0]

	assert before == 2
	assert after == 0
