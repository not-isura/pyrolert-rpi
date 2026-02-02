import sys
import json
from time import sleep

from sps30 import SPS30
from DFRobot_MultiGasSensor import *

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
    pm_sensor = PM_Sensor_setup()
    gas_CO, gas_O2, gas_NO2 = GAS_Sensors_setup()

    ctr = 0
    while True:
        try:
            # pm_current_reading = json.dumps(pm_sensor.get_measurement(), indent=2)
            pm_measurement = pm_sensor.get_measurement()
            pm_sensor_data = pm_measurement.get("sensor_data", {})

            mass_density = pm_sensor_data.get("mass_density", {})
            mass_density_values = [
                ("pm1.0", mass_density.get("pm1.0", 0.0)),
                ("pm2.5", mass_density.get("pm2.5", 0.0)),
                ("pm4.0", mass_density.get("pm4.0", 0.0)),
                ("pm10", mass_density.get("pm10", 0.0)),
            ]
            mass_density_unit = pm_sensor_data.get("mass_density_unit", "ug/m3")

            particle_count = pm_sensor_data.get("particle_count", {})
            particle_count_values = [
                ("pm0.5", particle_count.get("pm0.5", 0.0)),
                ("pm1.0", particle_count.get("pm1.0", 0.0)),
                ("pm2.5", particle_count.get("pm2.5", 0.0)),
                ("pm4.0", particle_count.get("pm4.0", 0.0)),
                ("pm10", particle_count.get("pm10", 0.0)),
            ]
            particle_count_unit = pm_sensor_data.get("particle_count_unit", "#/cm3")

            particle_size = pm_sensor_data.get("particle_size")
            particle_size_unit = pm_sensor_data.get("particle_size_unit", "um")
            timestamp = pm_measurement.get("timestamp")


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

            print("Mass density", mass_density_unit, mass_density_values)
            # print("Particle count", particle_count_unit, particle_count_values)
            # print("Particle size", particle_size, particle_size_unit)
            #print(pm_current_reading)
            sleep(1)

        except KeyboardInterrupt:
            print("Stopping measurement...")
            pm_sensor.stop_measurement()
            sys.exit()

