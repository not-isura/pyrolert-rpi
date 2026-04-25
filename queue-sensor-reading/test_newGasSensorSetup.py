from gas_sensor import GasSensor, GasSensorGroup
from temp_sensor import TempSensor
import time
from time import sleep
from datetime import datetime

gas_CO  = GasSensor(1, 0x74)
gas_O2  = GasSensor(1, 0x75)
gas_NO2 = GasSensor(1, 0x76)
temp_sensor = TempSensor()


gas_CO.setup()
sleep(0.1)
gas_O2.setup()
sleep(0.1)
gas_NO2.setup()
sleep(0.1)
temp_sensor.setup()

gas_group = GasSensorGroup(gas_CO, gas_O2, gas_NO2)
gas_group.start()
temp_sensor.start()

last_ts = None

print(int(0.9))

while True:
    concentration_CO, concentration_O2, concentration_NO2 = gas_group.get()
    temp_c, unit_Temp  = temp_sensor.get()
    capture_ts = float(time.time())
    delay = (capture_ts - last_ts) * 1000 if last_ts is not None else 0.0

    print("===========")
    print(f"{gas_CO.gastype}: {concentration_CO:.3f} {gas_CO.gasunits}")
    print(f"{gas_O2.gastype}: {concentration_O2:.3f} {gas_O2.gasunits}")
    print(f"{gas_NO2.gastype}: {concentration_NO2:.3f} {gas_NO2.gasunits}")
    print(f"Temp: {temp_c} {unit_Temp}")
    #print(f"Timestamp: {capture_ts} ({datetime.fromtimestamp(capture_ts).strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"Timestamp: {capture_ts} ({datetime.fromtimestamp(capture_ts).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]})")
    print(f"Delay: {delay:.1f} ms")

    last_ts = capture_ts

    #sleep(0.1)