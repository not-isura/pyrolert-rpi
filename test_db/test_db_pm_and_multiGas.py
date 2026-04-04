import sys
import json
import time
import random
from time import sleep
from datetime import datetime

from sps30 import SPS30
from DFRobot_MultiGasSensor import *
import db


def generate_mock_ambient_temp(board_temp_co, board_temp_o2, board_temp_no2):
    """Generate a mock ambient temperature using board temperatures as rough anchors."""
    board_avg = (float(board_temp_co) + float(board_temp_o2) + float(board_temp_no2)) / 3.0
    # Ambient is often below board temp due to sensor self-heating.
    ambient = board_avg - 1.5 + random.uniform(-0.8, 0.8)
    return round(max(-20.0, min(80.0, ambient)), 2)


def mock_detection_result(gas_co, gas_no2, gas_o2, pm25, temp_c):
    """Simple placeholder logic for detection result; tune thresholds later."""
    if pm25 >= 55.0 or gas_co >= 10.0 or gas_no2 >= 0.20:
        return "high_alert"
    if pm25 >= 35.0 or gas_co >= 5.0 or gas_no2 >= 0.10:
        return "alert"
    if pm25 >= 20.0 or gas_co >= 1.5 or gas_no2 >= 0.05:
        return "warning"
    if temp_c >= 40.0 or gas_o2 <= 19.0:
        return "warning"
    return "normal"

def PM_Sensor_setup():
    pm_sensor = SPS30()
    print(f"Firmware version: {pm_sensor.firmware_version()}")
    print(f"Product type: {pm_sensor.product_type()}")
    print(f"Serial number: {pm_sensor.serial_number()}")
    print(f"Status register: {pm_sensor.read_status_register()}")
    print(f"Auto cleaning interval: {pm_sensor.read_auto_cleaning_interval()}s")
    print(f"Set auto cleaning interval: {pm_sensor.write_auto_cleaning_interval_days(0)}s")
    pm_sensor.start_measurement()

    print("PM Sensor connected and ready")

    return pm_sensor

def GAS_Sensors_setup():
    gas_CO = DFRobot_MultiGasSensor_I2C(1, 0x74)
    gas_O2 = DFRobot_MultiGasSensor_I2C(1, 0x75)
    gas_NO2 = DFRobot_MultiGasSensor_I2C(1, 0x76)

    # Wait until passive mode is successfully set
    print("connecting CO")
    while not gas_CO.change_acquire_mode(gas_CO.PASSIVITY):
        print("Waiting for CO sensor to enter passive mode...")
        sleep(0.1)
    print("success CO")
    sleep(0.1)

    print("connecting O2")
    while not gas_O2.change_acquire_mode(gas_O2.PASSIVITY):
        print("Waiting for O2 sensor to enter passive mode...")
        sleep(0.1)
    print("success O2")
    sleep(0.1)

    print("connecting NO2")
    while not gas_NO2.change_acquire_mode(gas_NO2.PASSIVITY):
        print("Waiting for NO2 sensor to enter passive mode...")
        sleep(0.1)
    sleep(1)
    print("success NO2")

    sleep(1)

    # Enable temperature compensation
    gas_CO.set_temp_compensation(gas_CO.ON)
    sleep(0.5)  # short wait to stabilize

    gas_O2.set_temp_compensation(gas_O2.ON)
    sleep(0.5)  # short wait to stabilize

    gas_NO2.set_temp_compensation(gas_NO2.ON)
    sleep(0.5)  # short wait to stabilize

    print("ALL Gas Sensors connected and ready")

    return gas_CO, gas_O2, gas_NO2

if __name__ == "__main__":
    # Record start time
    start_time = datetime.now()
    print(f"\n{'='*50}")
    print(f"Session started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    pm_sensor = PM_Sensor_setup()
    gas_CO, gas_O2, gas_NO2 = GAS_Sensors_setup()

    db_path = "sensor_data.sqlite"
    db_conn = None
    db_error_count = 0
    max_db_errors = 5
    try:
        db_conn = db.init_db(db_path)
        print(f"SQLite ready: {db_path}")
    except Exception as db_init_error:
        print(f"[!] DB init failed. Continuing without DB writes: {db_init_error}")

    ctr = 0
    error_count = 0
    max_errors = 5
    error_log = []  # Store errors with timestamps
    
    while True:
        try:
            # Get PM sensor measurement as dictionary
            pm_data = pm_sensor.get_measurement()
            
            # Extract mass density values
            mass_density = pm_data["sensor_data"]["mass_density"]
            pm_mass = {
                "pm1.0": mass_density["pm1.0"],
                "pm2.5": mass_density["pm2.5"],
                "pm4.0": mass_density["pm4.0"],
                "pm10": mass_density["pm10"]
            }
            
            # Extract particle count values
            particle_count = pm_data["sensor_data"]["particle_count"]
            pm_count = {
                "pm0.5": particle_count["pm0.5"],
                "pm1.0": particle_count["pm1.0"],
                "pm2.5": particle_count["pm2.5"],
                "pm4.0": particle_count["pm4.0"],
                "pm10": particle_count["pm10"]
            }
            
            # Extract other values
            particle_size = pm_data["sensor_data"]["particle_size"]
            mass_unit = pm_data["sensor_data"]["mass_density_unit"]
            count_unit = pm_data["sensor_data"]["particle_count_unit"]
            size_unit = pm_data["sensor_data"]["particle_size_unit"]
            timestamp = pm_data["timestamp"]
            
            time.sleep(0.1)
            concentration_CO = gas_CO.read_gas_concentration()
            time.sleep(0.1)
            concentration_O2 = gas_O2.read_gas_concentration()
            time.sleep(0.1)
            concentration_NO2 = gas_NO2.read_gas_concentration()
            time.sleep(0.1)
            
            if concentration_CO < 0.01:
                concentration_CO = 0
            #if concentration_O2 < 0:
            #    concentration_O2 = 0
            if concentration_NO2 < 0.01:
                concentration_NO2 = 0

            # Mock values before persistence (replace with real logic/sensor later)
            mock_temp_c = generate_mock_ambient_temp(gas_CO.temp, gas_O2.temp, gas_NO2.temp)
            pm25_value = float(pm_mass["pm2.5"])
            detection_result = mock_detection_result(
                gas_co=float(concentration_CO),
                gas_no2=float(concentration_NO2),
                gas_o2=float(concentration_O2),
                pm25=pm25_value,
                temp_c=mock_temp_c,
            )

            # Use one timestamp captured when this cycle is fully processed and ready to persist.
            capture_ts = int(time.time())

            if db_conn is not None:
                try:
                    db.insert_reading(
                        conn=db_conn,
                        ts=capture_ts,
                        gas_co=float(concentration_CO),
                        gas_no2=float(concentration_NO2),
                        gas_o2=float(concentration_O2),
                        temp_c=mock_temp_c,
                        pm25=pm25_value,
                        detection_result=detection_result,
                    )
                    db_error_count = 0
                except Exception as db_write_error:
                    db_error_count += 1
                    print(f"[!] DB write error {db_error_count}/{max_db_errors}: {db_write_error}")
                    # Mitigation: re-open connection on repeated DB errors.
                    if db_error_count >= max_db_errors:
                        print("[!] Reinitializing SQLite connection after repeated write failures...")
                        try:
                            if db_conn is not None:
                                db_conn.close()
                            db_conn = db.init_db(db_path)
                            db_error_count = 0
                            print("SQLite reconnected.")
                        except Exception as reconnect_error:
                            print(f"[!] SQLite reconnect failed, DB writes paused: {reconnect_error}")
                            db_conn = None
            

            # PRINT READINGS ================================
            print("----------------------------")
            print("Reading No.", ctr)
            ctr += 1

            print("Gas:", gas_CO.gastype)
            print("Concentration:", concentration_CO, gas_CO.gasunits)
            print("Temperature:", gas_CO.temp, "°C")
            
            print("Gas:", gas_O2.gastype)
            print("Concentration:", concentration_O2, gas_O2.gasunits)
            print("Temperature:", gas_O2.temp, "°C")
            
            print("Gas:", gas_NO2.gastype)
            print("Concentration:", concentration_NO2, gas_NO2.gasunits)
            print("Temperature:", gas_NO2.temp, "°C")  
            print("Mock ambient temp (DB temp_c):", mock_temp_c, "°C")
            print("Mock detection_result:", detection_result)

            # Print PM sensor data in formatted way
            print("\n=== PM Sensor Data ===")
            print("Mass Density:")
            print(f"  PM 1.0:  {pm_mass['pm1.0']:.3f} {mass_unit}")
            print(f"  PM 2.5:  {pm_mass['pm2.5']:.3f} {mass_unit}")
            print(f"  PM 4.0:  {pm_mass['pm4.0']:.3f} {mass_unit}")
            print(f"  PM 10:   {pm_mass['pm10']:.3f} {mass_unit}")
            
            print("\nParticle Count:")
            print(f"  PM 0.5:  {pm_count['pm0.5']:.3f} {count_unit}")
            print(f"  PM 1.0:  {pm_count['pm1.0']:.3f} {count_unit}")
            print(f"  PM 2.5:  {pm_count['pm2.5']:.3f} {count_unit}")
            print(f"  PM 4.0:  {pm_count['pm4.0']:.3f} {count_unit}")
            print(f"  PM 10:   {pm_count['pm10']:.3f} {count_unit}")
            
            print(f"\nParticle Size: {particle_size:.3f} {size_unit}")
            print(f"Sensor Timestamp: {timestamp}")
            print(f"DB Capture Timestamp (unix): {capture_ts}")

            sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping measurement...")
            pm_sensor.stop_measurement()
            if db_conn is not None:
                db_conn.close()
            
            # Record end time
            end_time = datetime.now()
            duration = end_time - start_time
            
            print(f"\n{'='*50}")
            print(f"Session ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Duration: {duration}")
            print(f"Total errors encountered: {error_count}")
            print(f"{'='*50}\n")
            
            # Save to log file
            with open('session_log.txt', 'a') as log_file:
                log_file.write(f"\n{'='*50}\n")
                log_file.write(f"Session Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"Session End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"Duration:      {duration}\n")
                log_file.write(f"Status:        User interrupted\n")
                log_file.write(f"Total readings: {ctr}\n")
                log_file.write(f"Total errors:   {error_count}\n")
                if error_log:
                    log_file.write(f"\nErrors encountered:\n")
                    for i, err in enumerate(error_log, 1):
                        log_file.write(f"  {i}. [{err['time']}] {err['error']}\n")
                log_file.write(f"{'='*50}\n")
            
            print("Session logged to session_log.txt")
            sys.exit()
        
        except Exception as e:
            # Record error with timestamp
            error_time = datetime.now()
            error_count += 1
            error_info = {
                'time': error_time.strftime('%Y-%m-%d %H:%M:%S'),
                'error': str(e)
            }
            error_log.append(error_info)
            
            print(f"\n[!] Error {error_count}/{max_errors} at {error_info['time']}: {e}")
            
            # Check if max errors reached
            if error_count >= max_errors:
                print(f"\nMaximum error limit ({max_errors}) reached. Stopping...")
                pm_sensor.stop_measurement()
                if db_conn is not None:
                    db_conn.close()
                
                # Record end time
                end_time = datetime.now()
                duration = end_time - start_time
                
                print(f"\n{'='*50}")
                print(f"Session ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Duration: {duration}")
                print(f"Total errors: {error_count}")
                print(f"{'='*50}\n")
                
                # Save to log file
                with open('session_log.txt', 'a') as log_file:
                    log_file.write(f"\n{'='*50}\n")
                    log_file.write(f"Session Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write(f"Session End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write(f"Duration:      {duration}\n")
                    log_file.write(f"Status:        Stopped - Max errors reached ({max_errors})\n")
                    log_file.write(f"Total readings: {ctr}\n")
                    log_file.write(f"Total errors:   {error_count}\n")
                    log_file.write(f"\nErrors encountered:\n")
                    for i, err in enumerate(error_log, 1):
                        log_file.write(f"  {i}. [{err['time']}] {err['error']}\n")
                    log_file.write(f"{'='*50}\n")
                
                print("Session logged to session_log.txt")
                sys.exit()
            else:
                print(f"Continuing... ({max_errors - error_count} errors remaining)\n")
                sleep(2)  # Wait a bit before continuing

