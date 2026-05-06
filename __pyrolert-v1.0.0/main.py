import sys
import time
import traceback
from time import sleep
from datetime import datetime

from Sensor_Libraries import SPS30
from Helpers_Sensors import GasSensor, GasSensorGroup, TempSensor
from Database import db, supabase_client, sync_worker
from Helpers_Actuators import ToggleBuzzer, ToggleLED

from alert_logic import AlertEpisodeManager, SlidingWindowAlert, pyrolert_detection_result


# VARIABLE CONSTANTS
GAS_SETUP_TIMEOUT_S = 10
TEMP_READ_TIMEOUT_S = 5
SETUP_MAX_RETRIES = 5
WINDOW_SIZE = 20
HIGH_ALERT_THRESHOLD = 12
WARNING_THRESHOLD = 12
BUZZER_PIN = 22
LED_PIN = 23

toggle_buzzer = ToggleBuzzer(BUZZER_PIN)
toggle_led = ToggleLED(LED_PIN)

def PM_Sensor_setup():
    sleep(0.5)
    pm_sensor = SPS30()
    sleep(0.1)
    pm_sensor.start_measurement()
    sleep(0.5)
    print(f"Firmware version: {pm_sensor.firmware_version()}")
    print(f"Product type: {pm_sensor.product_type()}")
    print(f"Serial number: {pm_sensor.serial_number()}")
    print(f"Status register: {pm_sensor.read_status_register()}")
    print(f"Auto cleaning interval: {pm_sensor.read_auto_cleaning_interval()}s")
    print(f"Set auto cleaning interval: {pm_sensor.write_auto_cleaning_interval_days(0)}s")

    print("PM Sensor connected and ready\n")

    #print("Startup Cleaning: Wait for 10s")
    #pm_sensor.start_fan_cleaning()
    sleep(2)
    #print("Cleaning for 10s...")

    return pm_sensor

def PM_Sensor_measure(pm_sensor):
    # Get PM sensor measurement as dictionary
    pm_data = pm_sensor.get_measurement()

    if not pm_data:
        print("No data — sensor may be disconnected")
        return None
    else:
        # Extract mass density values
        mass_density = pm_data["sensor_data"]["mass_density"]
        pm_mass = {
            "pm1.0": mass_density["pm1.0"],
            "pm2.5": mass_density["pm2.5"],
            "pm4.0": mass_density["pm4.0"],
            "pm10": mass_density["pm10"]
        }
        
        mass_unit = pm_data["sensor_data"]["mass_density_unit"]

        return pm_mass["pm2.5"], mass_unit

def GAS_Sensors_setup():
    gas_CO  = GasSensor(1, 0x74)
    gas_O2  = GasSensor(1, 0x75)
    gas_NO2 = GasSensor(1, 0x76)

    gas_CO.setup()
    sleep(0.1)
    gas_O2.setup()
    sleep(0.1)
    gas_NO2.setup()
    sleep(0.1)

    gas_group = GasSensorGroup(gas_CO, gas_O2, gas_NO2)
    gas_group.start()
    print("All Gas Sensor Connected and Ready\n")
    return gas_CO, gas_O2, gas_NO2, gas_group

def GAS_measure(gas_group):
    concentration_CO, concentration_O2, concentration_NO2 = gas_group.get()
    return concentration_CO, concentration_O2, concentration_NO2

def Temp_Sensor_setup():
    temp_sensor = TempSensor()
    temp_sensor.setup()
    temp_sensor.start()
    return temp_sensor

def Temp_Sensor_measure(temp_sensor):
    temp_c, unit_Temp = temp_sensor.get()
    return temp_c, unit_Temp


def print_readings(ctr, gas_CO, concentration_CO, gas_O2, concentration_O2, gas_NO2, concentration_NO2, volume_PM, unit_PM, temp_c, temp_roc, unit_Temp, capture_ts, delay):
    print("----------------------------")
    print("Reading No.", ctr)
    print(f"{gas_CO.gastype}: {concentration_CO:.3f} {gas_CO.gasunits}")
    print(f"{gas_O2.gastype}: {concentration_O2:.3f} {gas_O2.gasunits}")
    print(f"{gas_NO2.gastype}: {concentration_NO2:.3f} {gas_NO2.gasunits}")
    print(f"PM 2.5: {volume_PM:.3f} {unit_PM}")
    print(f"Temp: {temp_c} {unit_Temp}")
    if temp_roc is not None:
        print(f"Temp RoC (1 min): {temp_roc:.2f} {unit_Temp}")
    else:
        print(f"Temp RoC (1 min): N/A {unit_Temp}")
    #print(f"Timestamp: {capture_ts} ({datetime.fromtimestamp(capture_ts).strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"Timestamp: {capture_ts} ({datetime.fromtimestamp(capture_ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]})")
    print(f"Delay: {delay:.1f} ms")

def write_session_log(start_time, end_time, duration, status, ctr, error_count, error_log):
    with open('Logs/session_log.txt', 'a') as log_file:
        log_file.write(f"\n{'='*50}\n")
        log_file.write(f"Session Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"Session End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"Duration:      {duration}\n")
        log_file.write(f"Status:        {status}\n")
        log_file.write(f"Total readings: {ctr}\n")
        log_file.write(f"Total errors:   {error_count}\n")
        if error_log:
            log_file.write(f"\nErrors encountered:\n")
            for i, err in enumerate(error_log, 1):
                log_file.write(f"  {i}. [{err['time']}] {err['error']}\n")
                if err.get('traceback'):
                    log_file.write("     Traceback:\n")
                    for line in err['traceback'].splitlines():
                        log_file.write(f"       {line}\n")
        log_file.write(f"{'='*50}\n")

def finalize_session(pm_sensor, start_time, status, ctr, error_count, error_log):
    if pm_sensor is not None:
        try:
            pm_sensor.stop_measurement()
        except OSError:
            print("[!] PM sensor already disconnected, skipping stop.")

    end_time = datetime.now()
    duration = end_time - start_time

    print(f"\n{'='*50}")
    print(f"Session ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration}")
    print(f"Total errors encountered: {error_count}")
    print(f"{'='*50}\n")

    write_session_log(start_time, end_time, duration, status, ctr, error_count, error_log)

    print("Session logged to session_log.txt")
    sys.exit()

def setup_with_retries(setup_name, setup_callable, max_retries=SETUP_MAX_RETRIES, retry_delay_s=1):
    for attempt in range(1, max_retries + 1):
        try:
            result = setup_callable()
            if attempt > 1:
                print(f"{setup_name} setup succeeded on attempt {attempt}/{max_retries}")
            return result
        except Exception as e:
            print(f"[!] {setup_name} setup failed (attempt {attempt}/{max_retries}): {e}")
            print(traceback.format_exc())
            if attempt == max_retries:
                raise RuntimeError(f"{setup_name} setup failed after {max_retries} attempts") from e
            sleep(retry_delay_s)

if __name__ == "__main__":
    print("\n================== Pyrolert Starting Up... ==================\n")

    ### Start of Log =======================================
    # Record start time
    start_time = datetime.now()
    print(f"\n{'='*50}")
    print(f"Session started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    ctr = 0
    error_count = 0
    max_errors = 5
    error_log = []  # Store errors with timestamps


    ### DB Startup ==========================================
    db_path = "Database/db_pyrolert.sqlite"
    db_conn = None
    db_error_count = 0
    max_db_errors = 5
    try:
        db_conn = db.init_db(db_path)
        print(f"SQLite ready: {db_path}")
        # Start background sync worker
        # Commented out to Pause the Supabase Sync for now
        if db_conn is not None:
            sync_worker.start(db_conn)
    except Exception as db_init_error:
        print(f"[!] DB init failed. Continuing without DB writes: {db_init_error}")

    ### Sensor Setups ======================================
    pm_sensor = None
    try:
        pm_sensor = setup_with_retries("PM sensor", PM_Sensor_setup)
        gas_CO, gas_O2, gas_NO2, gas_group = setup_with_retries("Gas sensors", GAS_Sensors_setup)
        temp_sensor = setup_with_retries("Temperature sensor", Temp_Sensor_setup)

        window = SlidingWindowAlert(WINDOW_SIZE, HIGH_ALERT_THRESHOLD, WARNING_THRESHOLD)
        alert_manager = AlertEpisodeManager(db_conn, buzzer=toggle_buzzer)
    except Exception as e:
        error_count += 1
        error_info = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'error': str(e),
            'traceback': traceback.format_exc().strip(),
        }
        error_log.append(error_info)
        print(f"\n[!] Startup failed: {e}")
        print(error_info['traceback'])
        finalize_session(
            pm_sensor,
            start_time,
            "Startup failed",
            ctr,
            error_count,
            error_log,
        )


    ### Sensor Reading and Detection Loop ==================================================
    last_ts = None

    while True:
        try:
            print(f"Read {ctr}")
            ctr = ctr + 1
            sleep(1)
            # # Use one timestamp captured when this cycle is fully processed and ready to persist
            # capture_ts = float(time.time())

            # # Read PM Values                
            # pm_result = PM_Sensor_measure(pm_sensor) # returns PM 2.5 volume (ug/m3)
            # if pm_result is None:
            #     raise ValueError("volume_PM is None: sensor may be disconnected or returning invalid data")
            # volume_PM, unit_PM = pm_result

            # # Read Temp Values
            # temp_c, unit_Temp= Temp_Sensor_measure(temp_sensor)

            # temp_roc = None
            # if db_conn is not None:
            #     temp_c_1min = db.fetch_temp_c_at_or_before_ts(db_conn, capture_ts - 60.0)
            #     if temp_c_1min is not None:
            #         temp_roc = temp_c - temp_c_1min

            # # Read Gas Values (CO, O2, NO2)
            # concentration_CO, concentration_O2, concentration_NO2 = GAS_measure(gas_group)
    

            # ### SMOKE DETECTION LOGIC =========================
            # detection_result = pyrolert_detection_result(
            #     gas_co=float(concentration_CO),
            #     gas_no2=float(concentration_NO2),
            #     gas_o2=float(concentration_O2),
            #     pm25=volume_PM,
            #     temp_c=temp_c,
            #     temp_roc=temp_roc,
            # )

            # confirmed_state = window.add(detection_result)
            # normal_count, warning_count, high_count = window.counts()
            # print(f"[Alert] Window N={normal_count} W={warning_count} HL={high_count}")
            # if confirmed_state is not None:
            #     print(f"[Alert] Confirmed {confirmed_state} at {datetime.fromtimestamp(capture_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            # alert_manager.handle(confirmed_state, capture_ts)

            # ### DATABASE SAVING ===============================          
            # if db_conn is not None:
            #     try:
            #         row_id = db.insert_reading(
            #             conn=db_conn,
            #             ts=capture_ts,
            #             gas_co=float(concentration_CO),
            #             gas_no2=float(concentration_NO2),
            #             gas_o2=float(concentration_O2),
            #             temp_c=temp_c,
            #             temp_roc=temp_roc,
            #             pm25=volume_PM,
            #             detection_result=detection_result,
            #         )
            #         db_error_count = 0

            #         # Immediately push latest reading to Supabase
            #         # Commented out to Pause the Supabase Sync for now
                    
            #         row = {
            #             "id":               row_id,
            #             "ts":               capture_ts,
            #             "gas_co":           float(concentration_CO),
            #             "gas_no2":          float(concentration_NO2),
            #             "gas_o2":           float(concentration_O2),
            #             "temp_c":           temp_c,
            #             "temp_roc":         temp_roc,
            #             "pm25":             volume_PM,
            #             "detection_result": detection_result,
            #         }
            #         success = supabase_client.push_reading(row)
            #         if success:
            #             db.mark_as_synced(db_conn, [row_id])
            #             print("[Supabase] ✅ Live push successful")  # uncomment if you want to see it
            #         else:
            #             print("[Supabase] ⚠️ Live push failed, will sync later via background worker")
                    
            #     except Exception as db_write_error:
            #         db_error_count += 1
            #         print(f"[!] DB write error {db_error_count}/{max_db_errors}: {db_write_error}")
            #         # Mitigation: re-open connection on repeated DB errors.
            #         if db_error_count >= max_db_errors:
            #             print("[!] Reinitializing SQLite connection after repeated write failures...")
            #             try:
            #                 if db_conn is not None:
            #                     db_conn.close()
            #                 db_conn = db.init_db(db_path)
            #                 db_error_count = 0
            #                 print("SQLite reconnected.")
            #             except Exception as reconnect_error:
            #                 print(f"[!] SQLite reconnect failed, DB writes paused: {reconnect_error}")
            #                 db_conn = None
            # # PRINT READINGS ================================
            # #sleep(0.25)
            # delay = (capture_ts - last_ts) * 1000 if last_ts is not None else 0.0
            # last_ts = capture_ts

            # ctr += 1
            # print_readings(ctr, gas_CO, concentration_CO, gas_O2, concentration_O2, gas_NO2, concentration_NO2, volume_PM, unit_PM, temp_c, temp_roc, unit_Temp, capture_ts, delay)
            

        except KeyboardInterrupt:
            print("\n\nStopping measurement...")
            sync_worker.stop()  # stop background thread cleanly
            if db_conn is not None:
                db_conn.close()
            finalize_session(pm_sensor, start_time, "User interrupted", ctr, error_count, error_log)
        
        except Exception as e:
            # Record error with timestamp
            error_time = datetime.now()
            error_count += 1
            error_tb = traceback.format_exc().strip()
            error_info = {
                'time': error_time.strftime('%Y-%m-%d %H:%M:%S'),
                'error': str(e),
                'traceback': error_tb,
            }
            error_log.append(error_info)
            
            print(f"\n[!] Error {error_count}/{max_errors} at {error_info['time']}: {e}")
            print(error_tb)
            
            # Check if max errors reached
            if error_count >= max_errors:
                print(f"\nMaximum error limit ({max_errors}) reached. Stopping...")
                if db_conn is not None:
                    db_conn.close()
                finalize_session(
                    pm_sensor,
                    start_time,
                    f"Stopped - Max errors reached ({max_errors})",
                    ctr,
                    error_count,
                    error_log,
                )
            else:
                print(f"Continuing... ({max_errors - error_count} errors remaining)\n")
                sleep(2)  # Wait a bit before continuing

