import sqlite3
import time
import os

while True:
    os.system('clear')
    conn = sqlite3.connect('sensor_data.sqlite')
    cursor = conn.execute("""
        SELECT strftime('%m/%d/%Y %I:%M:%S %p', ts, 'unixepoch', 'localtime'), 
               gas_co, gas_no2, pm25, detection_result 
        FROM sensor_readings 
        ORDER BY ts DESC 
        LIMIT 10
    """)
    for row in cursor:
        print(row)
    conn.close()
    time.sleep(2)
