import sys
import time
import glob
import os
from time import sleep
from datetime import datetime

from sps30 import SPS30
from DFRobot_MultiGasSensor import DFRobot_MultiGasSensor_I2C

GAS_SETUP_TIMEOUT_S = 10
TEMP_READ_TIMEOUT_S = 5

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
    sleep(10)
    print("Done Fan Cleaning")

    return pm_sensor

def PM_Sensor_measure(pm_sensor):
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
        print("Waiting for CO sensor to enter passive mode...")
        sleep(0.1)
    print("success CO")
    sleep(0.1)

    print("connecting O2")
    start_wait = time.monotonic()
    while not gas_O2.change_acquire_mode(gas_O2.PASSIVITY):
        if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
            raise TimeoutError("O2 sensor timed out entering passive mode")
        print("Waiting for O2 sensor to enter passive mode...")
        sleep(0.1)
    print("success O2")
    sleep(0.1)

    print("connecting NO2")
    start_wait = time.monotonic()
    while not gas_NO2.change_acquire_mode(gas_NO2.PASSIVITY):
        if time.monotonic() - start_wait >= GAS_SETUP_TIMEOUT_S:
            raise TimeoutError("NO2 sensor timed out entering passive mode")
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

def GAS_measure(gas_CO, gas_O2, gas_NO2):
    time.sleep(0.1)
    concentration_CO = gas_CO.read_gas_concentration() # returns concentration (ppm)
    time.sleep(0.1)
    concentration_O2 = gas_O2.read_gas_concentration() # returns concentration (ppm)
    time.sleep(0.1)
    concentration_NO2 = gas_NO2.read_gas_concentration() # returns concentration (ppm)
    time.sleep(0.1)
    
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
    device_path = glob.glob(base_dir + '28*')[0] #get file path of sensor
    rom = device_path.split('/')[-1] #get rom name

    sleep(0.5)
    print('Temperature Device ROM: '+ rom)
    return device_path

def read_temp_raw(device_path):
    with open(device_path +'/w1_slave','r') as f:
        valid, temp = f.readlines()
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

    pos = temp.index('t=')
    if pos != -1:
        #read the temperature .
        temp_string = temp[pos+2:]
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

if __name__ == "__main__":
    # Record start time
    start_time = datetime.now()
    print(f"\n{'='*50}")
    print(f"Session started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    pm_sensor = PM_Sensor_setup()
    gas_CO, gas_O2, gas_NO2 = GAS_Sensors_setup()
    temp_dev_path = Temp_Sensor_setup()

    """
    Variables for Sensor Readings
    - volume_PM
    - temp_c
    - concentration_CO
    - concentration_O2
    - concentration_NO2
    """

    ctr = 0
    error_count = 0
    max_errors = 5
    error_log = []  # Store errors with timestamps
    
    while True:
        try:
            # Read PM Values
            volume_PM, unit_PM = PM_Sensor_measure(pm_sensor) # returns PM 2.5 volume (ug/m3)

            # Read Temp Values
            temp_c, unit_Temp= read_temp(temp_dev_path)

            # Read Gas Values (CO, O2, NO2)
            concentration_CO, concentration_O2, concentration_NO2 = GAS_measure(gas_CO, gas_O2, gas_NO2)
            
            # PRINT READINGS ================================
            ctr += 1
            print_readings(ctr, gas_CO, concentration_CO, gas_O2, concentration_O2, gas_NO2, concentration_NO2, volume_PM, unit_PM, temp_c, unit_Temp)
            sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping measurement...")
            pm_sensor.stop_measurement()
            
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

