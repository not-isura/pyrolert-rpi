from DFRobot_MultiGasSensor import *
import time

gas = DFRobot_MultiGasSensor_I2C(1, 0x76)

# Wait until passive mode is successfully set
while not gas.change_acquire_mode(gas.PASSIVITY):
    print("Waiting for sensor to enter passive mode...")
    time.sleep(1)

# Enable temperature compensation
gas.set_temp_compensation(gas.ON)
time.sleep(1)  # short wait to stabilize

print("Sensor connected and ready")

while True:
    concentration = gas.read_gas_concentration()  # triggers data analysis
    if concentration < 0:
        concentration = 0
    print("Gas:", gas.gastype)
    print("Concentration:", concentration, gas.gasunits)
    print("Temperature:", gas.read_temp(), "°C")
    print("------------------")
    time.sleep(0.5)
