import requests
import random
import time
from datetime import datetime, timedelta

# URL = "http://localhost:3000/api/sensor-data"
URL = "http://LAPTOP-O7823JST.local:3000/api/sensor-data"

def generate_fake_readings(count: int) -> list:
    """Generate fake sensor readings to simulate SQLite query result."""
    readings = []
    now = datetime.now()

    for i in range(count):
        # Go back in time for older readings
        timestamp = now - timedelta(seconds=(count - i))
        
        gas1 = round(random.uniform(0.1, 0.9), 2)
        gas2 = round(random.uniform(0.1, 0.9), 2)
        gas3 = round(random.uniform(0.1, 0.9), 2)
        temperature = round(random.uniform(25.0, 75.0), 2)
        pm = round(random.uniform(5.0, 20.0), 2)

        # Mock fire detection logic
        is_fire = gas1 > 0.8 or temperature > 60
        triggered_by = []
        if gas1 > 0.8: triggered_by.append("gas1")
        if temperature > 60: triggered_by.append("temperature")

        readings.append({
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "gas1": gas1,
            "gas2": gas2,
            "gas3": gas3,
            "temperature": temperature,
            "pm": pm,
            "is_fire": is_fire,
            "confidence": round(random.uniform(0.8, 1.0), 2) if is_fire else 0.0,
            "triggered_by": "+".join(triggered_by) if triggered_by else "none"
        })

    return readings


def push_to_nextjs(readings: list):
    """Send readings to Next.js API."""
    try:
        payload = {
            "readings": readings,
            "count": len(readings),
            "warming_up": len(readings) < 100
        }
        response = requests.post(URL, json=payload, timeout=2)
        data = response.json()

        if data.get("success"):
            latest = readings[-1]  # last reading is the most recent
            print(f"[✅ SENT] {len(readings)} rows | "
                  f"Gas1: {latest['gas1']} | "
                  f"Temp: {latest['temperature']} | "
                  f"Fire: {latest['is_fire']}")
        else:
            print(f"[❌ FAILED] Server responded with error")

    except requests.exceptions.ConnectionError:
        print(f"[❌ CONNECTION ERROR] Is Next.js running?")
    except requests.exceptions.Timeout:
        print(f"[⚠️ TIMEOUT] Server took too long to respond")
    except Exception as e:
        print(f"[❌ ERROR] {e}")


def main():
    print("🔥 Fire Detection Tester Started")
    print(f"📡 Pushing to: {URL}")
    print("─" * 50)

    # Start with 0 rows, build up to 100 (simulates warming up)
    row_count = 0

    while True:
        # Simulate warming up — increment until 100
        if row_count < 100:
            row_count += 1
        
        readings = generate_fake_readings(row_count)
        push_to_nextjs(readings)
        time.sleep(1)


if __name__ == "__main__":
    main()