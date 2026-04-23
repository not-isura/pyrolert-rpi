import sys
import time
import glob
import os
from time import sleep
from datetime import datetime

from sps30 import SPS30
from DFRobot_MultiGasSensor import DFRobot_MultiGasSensor_I2C, recvbuf
import db

GAS_SETUP_TIMEOUT_S = 10
TEMP_READ_TIMEOUT_S = 5
SETUP_MAX_RETRIES = 5

def pyrolert_detection_result(gas_co, gas_no2, gas_o2, pm25, temp_c, temp_c_1min = 0):
    temp_RoC = temp_c - temp_c_1min
    if (gas_co >= 60 or gas_no2 >= 1) and (gas_o2 < 18 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 150):
        return "High Alert"
    if (gas_co >= 25 or gas_no2 >= 0.2) and (gas_o2 < 19 and (temp_c > 57.2 or temp_RoC >= 8) and pm25 >= 90):
        return "Warning"
    return "Normal"

def mock_detection_result(gas_co, gas_no2, gas_o2, pm25, temp_c):
    """Simple placeholder logic for detection result; tune thresholds later."""
    if pm25 >= 55.0 or gas_co >= 10.0 or gas_no2 >= 0.20:
        return "MOCK: high_alert"
    if pm25 >= 35.0 or gas_co >= 5.0 or gas_no2 >= 0.10:
        return "MOCK: alert"
    if pm25 >= 20.0 or gas_co >= 1.5 or gas_no2 >= 0.05:
        return "MOCK: warning"
    if temp_c >= 40.0 or gas_o2 <= 19.0:
        return "MOCK: warning"
    return "MOCK: normal"

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

    print("PM Sensor connected and ready")

    print("Startup Cleaning: Wait for 10s")
    pm_sensor.start_fan_cleaning()
    sleep(1)
    print("Cleaning for 10s...")

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
        
        # Extract particle count values
        # particle_count = pm_data["sensor_data"]["particle_count"]
        # pm_count = {
        #     "pm0.5": particle_count["pm0.5"],
        #     "pm1.0": particle_count["pm1.0"],
        #     "pm2.5": particle_count["pm2.5"],
        #     "pm4.0": particle_count["pm4.0"],
        #     "pm10": particle_count["pm10"]
        # }
        
        # Extract other values
        # particle_size = pm_data["sensor_data"]["particle_size"]
        mass_unit = pm_data["sensor_data"]["mass_density_unit"]
        # count_unit = pm_data["sensor_data"]["particle_count_unit"]
        # size_unit = pm_data["sensor_data"]["particle_size_unit"]
        # timestamp = pm_data["timestamp"]

        return pm_mass["pm2.5"], mass_unit

def GAS_Sensors_setup():
    gas_CO = DFRobot_MultiGasSensor_I2C(1, 0x74)
    gas_O2 = DFRobot_MultiGasSensor_I2C(1, 0x75)
    gas_NO2 = DFRobot_MultiGasSensor_I2C(1, 0x76)

    # Wait until passive mode is successfully set
    print("connecting CO")
    start_wait = time.monotonic()
    while not gas_CO.change_acquire_mode(gas_CO.PASSIVITY):
        if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
            raise TimeoutError("CO sensor timed out entering passive mode")
        if all(b == 0 for b in recvbuf):
            raise RuntimeError("CO sensor returned all zeros — sensor may be disconnected")
        print("Waiting for CO sensor to enter passive mode...")
        sleep(0.1)
    print("success CO")
    sleep(0.1)

    print("connecting O2")
    start_wait = time.monotonic()
    while not gas_O2.change_acquire_mode(gas_O2.PASSIVITY):
        if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
            raise TimeoutError("O2 sensor timed out entering passive mode")
        if all(b == 0 for b in recvbuf):
            raise RuntimeError("O2 sensor returned all zeros — sensor may be disconnected")
        print("Waiting for O2 sensor to enter passive mode...")
        sleep(0.1)
    print("success O2")
    sleep(0.1)

    print("connecting NO2")
    start_wait = time.monotonic()
    while not gas_NO2.change_acquire_mode(gas_NO2.PASSIVITY):
        if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
            raise TimeoutError("NO2 sensor timed out entering passive mode")
        if all(b == 0 for b in recvbuf):
            raise RuntimeError("NO2 sensor returned all zeros — sensor may be disconnected")
        print("Waiting for NO2 sensor to enter passive mode...")
        sleep(0.1)
    #sleep(1)
    print("success NO2")

    sleep(0.3)

    # Enable temperature compensation
    gas_CO.set_temp_compensation(gas_CO.ON)
    sleep(0.3)  # short wait to stabilize

    gas_O2.set_temp_compensation(gas_O2.ON)
    sleep(0.3)  # short wait to stabilize

    gas_NO2.set_temp_compensation(gas_NO2.ON)
    sleep(0.3)  # short wait to stabilize

    print("ALL Gas Sensors connected and ready")

    return gas_CO, gas_O2, gas_NO2

def GAS_measure(gas_CO, gas_O2, gas_NO2):
    sleep(0.1)
    concentration_CO = gas_CO.read_gas_concentration()
    if all(b == 0 for b in recvbuf):
        raise RuntimeError("CO sensor returned all zeros — sensor may be disconnected")
    
    sleep(0.1)
    concentration_O2 = gas_O2.read_gas_concentration()
    if all(b == 0 for b in recvbuf):
        raise RuntimeError("O2 sensor returned all zeros — sensor may be disconnected")
    
    sleep(0.1)
    concentration_NO2 = gas_NO2.read_gas_concentration()
    if all(b == 0 for b in recvbuf):
        raise RuntimeError("NO2 sensor returned all zeros — sensor may be disconnected")
    sleep(0.1)
    
    # Gas Value correction for normal conditions 
    if concentration_CO < 0.1:
        concentration_CO = 0
    if concentration_NO2 < 0.1:
        concentration_NO2 = 0

    return concentration_CO, concentration_O2, concentration_NO2

def Temp_Sensor_setup():
    #these tow lines mount the device:
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
    
    base_dir = '/sys/bus/w1/devices/'
    devices = glob.glob(base_dir + '28*')
    if not devices:
        raise RuntimeError("No DS18B20 temperature sensor found under /sys/bus/w1/devices/")

    device_path = devices[0] #get file path of sensor
    rom = device_path.split('/')[-1] #get rom name

    sleep(0.5)
    print('Temperature Device ROM: '+ rom)
    return device_path

def read_temp_raw(device_path):
    with open(device_path + '/w1_slave', 'r') as f:
        lines = f.readlines()
    
    if len(lines) < 2:
        raise ValueError(f"Unexpected sensor output: {lines}")
    
    valid, temp = lines
    return valid, temp
 
def read_temp(device_path):
    valid, temp = read_temp_raw(device_path)
    temp_unit = "°C"

    start_wait = time.monotonic()
    while 'YES' not in valid:
        if time.monotonic() - start_wait >= TEMP_READ_TIMEOUT_S:
            raise TimeoutError("Temperature sensor timed out waiting for valid reading")
        sleep(0.2)
        valid, temp = read_temp_raw(device_path)

    pos = temp.find('t=')
    if pos == -1:
        raise ValueError(f"Malformed temperature sensor payload: {temp.strip()}")

    #read the temperature .
    temp_string = temp[pos+2:]

    raw_value = int(temp_string)
    # DS18B20 returns exactly 0 raw when disconnected
    if raw_value == 0:
        raise RuntimeError("Temperature sensor returned raw 0 — sensor may be disconnected or faulty")

    temp_c = float(temp_string)/1000.0 
    #temp_f = temp_c * (9.0 / 5.0) + 32.0
    #return temp_c, temp_f
    return round(temp_c, 2), temp_unit

def print_readings(ctr, gas_CO, concentration_CO, gas_O2, concentration_O2, gas_NO2, concentration_NO2, volume_PM, unit_PM, temp_c, unit_Temp):
    print("----------------------------")
    print("Reading No.", ctr)
    print(f"{gas_CO.gastype}: {concentration_CO:.3f} {gas_CO.gasunits}")
    print(f"{gas_O2.gastype}: {concentration_O2:.3f} {gas_O2.gasunits}")
    print(f"{gas_NO2.gastype}: {concentration_NO2:.3f} {gas_NO2.gasunits}")
    print(f"PM 2.5: {volume_PM:.3f} {unit_PM}")
    print(f"Temp: {temp_c} {unit_Temp}")

def write_session_log(start_time, end_time, duration, status, ctr, error_count, error_log):
    with open('session_log.txt', 'a') as log_file:
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
        log_file.write(f"{'='*50}\n")

def finalize_session(pm_sensor, start_time, status, ctr, error_count, error_log):
    if pm_sensor is not None:
        pm_sensor.stop_measurement()

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
            if attempt == max_retries:
                raise RuntimeError(f"{setup_name} setup failed after {max_retries} attempts") from e
            sleep(retry_delay_s)

if __name__ == "__main__":
    # Record start time
    start_time = datetime.now()
    print(f"\n{'='*50}")
    print(f"Session started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    db_path = "db_pyrolert.sqlite"
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

    try:
        pm_sensor = setup_with_retries("PM sensor", PM_Sensor_setup)
        gas_CO, gas_O2, gas_NO2 = setup_with_retries("Gas sensors", GAS_Sensors_setup)
        temp_dev_path = setup_with_retries("Temperature sensor", Temp_Sensor_setup)
    except Exception as e:
        error_count += 1
        error_info = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'error': str(e)
        }
        error_log.append(error_info)
        print(f"\n[!] Startup failed: {e}")
        finalize_session(
            pm_sensor if 'pm_sensor' in dir() else None,
            start_time,
            "Startup failed",
            ctr,
            error_count,
            error_log,
        )

    """
    Variables for Sensor Readings
    - volume_PM
    - temp_c
    - concentration_CO
    - concentration_O2
    - concentration_NO2
    """

    while True:
        try:
            # Read PM Values                
            pm_result = PM_Sensor_measure(pm_sensor) # returns PM 2.5 volume (ug/m3)
            if pm_result is None:
                raise ValueError("volume_PM is None: sensor may be disconnected or returning invalid data")
            volume_PM, unit_PM = pm_result

            # Read Temp Values
            temp_c, unit_Temp= read_temp(temp_dev_path)

            # Read Gas Values (CO, O2, NO2)
            concentration_CO, concentration_O2, concentration_NO2 = GAS_measure(gas_CO, gas_O2, gas_NO2)
            

            ### SMOKE DETECTION LOGIC =========================
            detection_result = pyrolert_detection_result(
                gas_co=float(concentration_CO),
                gas_no2=float(concentration_NO2),
                gas_o2=float(concentration_O2),
                pm25=volume_PM,
                temp_c=temp_c,
            )

            ### DATABASE SAVING ===============================

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
                        temp_c=temp_c,
                        pm25=volume_PM,
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
            ctr += 1
            print_readings(ctr, gas_CO, concentration_CO, gas_O2, concentration_O2, gas_NO2, concentration_NO2, volume_PM, unit_PM, temp_c, unit_Temp)
            sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping measurement...")
            if db_conn is not None:
                db_conn.close()
            finalize_session(pm_sensor if 'pm_sensor' in dir() else None, start_time, "User interrupted", ctr, error_count, error_log)
        
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
                if db_conn is not None:
                    db_conn.close()
                finalize_session(
                    pm_sensor if 'pm_sensor' in dir() else None,
                    start_time,
                    f"Stopped - Max errors reached ({max_errors})",
                    ctr,
                    error_count,
                    error_log,
                )
            else:
                print(f"Continuing... ({max_errors - error_count} errors remaining)\n")
                sleep(2)  # Wait a bit before continuing

