from DFRobot_MultiGasSensor import *
import time

gas_CO = DFRobot_MultiGasSensor_I2C(1, 0x74)
gas_O2 = DFRobot_MultiGasSensor_I2C(1, 0x75)
gas_NO2 = DFRobot_MultiGasSensor_I2C(1, 0x76)

# Wait until passive mode is successfully set
print("connecting CO")
while not gas_CO.change_acquire_mode(gas_CO.PASSIVITY):
    print("Waiting for CO sensor to enter passive mode...")
    time.sleep(1)
print("success CO")
time.sleep(1)

print("connecting O2")
while not gas_O2.change_acquire_mode(gas_O2.PASSIVITY):
    print("Waiting for O2 sensor to enter passive mode...")
    time.sleep(1)
print("success O2")
time.sleep(1)

print("connecting NO2")
while not gas_NO2.change_acquire_mode(gas_NO2.PASSIVITY):
    print("Waiting for NO2 sensor to enter passive mode...")
    time.sleep(1)
time.sleep(1)
print("success NO2")

time.sleep(3)

# Enable temperature compensation
gas_CO.set_temp_compensation(gas_CO.ON)
time.sleep(1)  # short wait to stabilize

gas_O2.set_temp_compensation(gas_O2.ON)
time.sleep(1)  # short wait to stabilize

gas_NO2.set_temp_compensation(gas_NO2.ON)
time.sleep(1)  # short wait to stabilize

print("ALL Sensor connected and ready")


ctr = 1

while True:
    concentration_CO = gas_CO.read_gas_concentration()  # triggers data analysis
    time.sleep(0.1)
    concentration_O2 = gas_O2.read_gas_concentration()  # triggers data analysis
    time.sleep(0.1)
    concentration_NO2 = gas_NO2.read_gas_concentration()  # triggers data analysis
    time.sleep(0.1)
    
    if concentration_CO < 0.01:
        concentration_CO = 0
    #if concentration_O2 < 0:
    #    concentration_O2 = 0
    if concentration_NO2 < 0.01:
        concentration_NO2 = 0
	
    print("Reading No.", ctr)
	
    print("Gas:", gas_CO.gastype)
    print("Concentration:", concentration_CO, gas_CO.gasunits)
    print("Temperature:", gas_CO.temp, "°C")
    
    print("Gas:", gas_O2.gastype)
    print("Concentration:", concentration_O2, gas_O2.gasunits)
    print("Temperature:", gas_O2.temp, "°C")
    
    print("Gas:", gas_NO2.gastype)
    print("Concentration:", concentration_NO2, gas_NO2.gasunits)
    print("Temperature:", gas_NO2.temp, "°C")
    
    
    print("------------------")
    ctr += 1    
    time.sleep(0.1)

