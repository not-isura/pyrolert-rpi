import time
import os
from dotenv import load_dotenv
from supabase import create_client

# Load env variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
print("done env")

def test_insert():
    """Test inserting a fake row to Supabase."""
    fake_row = {
        "ts": int(time.time()),  # current unix timestamp
        "gas_co": 0.00,
        "gas_no2": 0.00,
        "gas_o2": 20.90,
        "temp_c": 32.0,
        "pm25": 17.028,
        "detection_result": "normal"
    }

    try:
        response = supabase.table("sensor_readings").insert(fake_row).execute()
        print("✅ INSERT successful!")
        print(f"Inserted row: {response.data}")
    except Exception as e:
        print(f"❌ INSERT failed: {e}")

def test_read():
    """Test reading last 5 rows from Supabase."""
    try:
        response = (
            supabase.table("sensor_readings")
            .select("*")
            .order("ts", desc=True)
            .limit(5)
            .execute()
        )
        print("✅ READ successful!")
        print(f"Last 5 rows:")
        for row in response.data:
            print(f"  id={row['id']} | ts={row['ts']} | recorded_at={row['recorded_at']} | gas_co={row['gas_co']}")
    except Exception as e:
        print(f"❌ READ failed: {e}")

if __name__ == "__main__":
    print("🔥 Testing Supabase connection...")
    print("─" * 50)
    
    print("\n1. Testing INSERT...")
    test_insert()
    time.sleep(1)
    test_insert()
    time.sleep(1)
    test_insert()
    time.sleep(1)
    test_insert()
    time.sleep(1)
    test_insert()
    
    print("\n2. Testing READ...")
    test_read()