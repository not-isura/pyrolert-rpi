import argparse
import random
import time
from typing import Iterator

import db


MEAN_CO = 1.0
MEAN_NO2 = 0.02
MEAN_O2 = 20.5
MEAN_TEMP_C = 26.0
MEAN_PM25 = 8.0


def mock_readings(rate_hz: float = 1.0) -> Iterator[dict]:
    """Yield mock sensor readings at the requested rate."""
    interval = 1.0 / rate_hz
    while True:
        ts = int(time.time())
        sample = {
            "ts": ts,
            "gas_co": max(0.0, random.gauss(MEAN_CO, 0.3)),
            "gas_no2": max(0.0, random.gauss(MEAN_NO2, 0.01)),
            "gas_o2": max(0.0, random.gauss(MEAN_O2, 0.2)),
            "temp_c": random.gauss(MEAN_TEMP_C, 1.0),
            "pm25": max(0.0, random.gauss(MEAN_PM25, 2.0)),
        }
        sample["detection_result"] = "alert" if sample["pm25"] > 35 or sample["gas_co"] > 10 else "normal"
        yield sample
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock sensor logger that writes to SQLite.")
    parser.add_argument("--db", dest="db_path", default="db.sqlite", help="Path to sqlite database file")
    parser.add_argument("--rate", dest="rate", type=float, default=1.0, help="Samples per second")
    parser.add_argument("--limit", dest="limit", type=int, default=0, help="Stop after N samples; 0 = run forever")
    args = parser.parse_args()

    random.seed(42)
    conn = db.init_db(args.db_path)

    print(f"Writing mock sensor readings to {args.db_path} (rate={args.rate} Hz, limit={args.limit or '∞'})")
    try:
        for idx, sample in enumerate(mock_readings(rate_hz=args.rate), start=1):
            db.insert_reading(
                conn=conn,
                ts=sample["ts"],
                gas_co=sample["gas_co"],
                gas_no2=sample["gas_no2"],
                gas_o2=sample["gas_o2"],
                temp_c=sample["temp_c"],
                pm25=sample["pm25"],
                detection_result=sample["detection_result"],
            )
            if args.limit and idx >= args.limit:
                break
    except KeyboardInterrupt:
        print("\nStopped by user.")

    rows = db.fetch_recent_readings(conn, limit=5)
    print(f"Last {len(rows)} rows:")
    for row in rows:
        print(dict(row))


if __name__ == "__main__":
    main()
