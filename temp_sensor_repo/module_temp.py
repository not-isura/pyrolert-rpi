import os
import glob
from time import sleep



def init_temp():
    #these tow lines mount the device:
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
    
    base_dir = '/sys/bus/w1/devices/'
    device_path = glob.glob(base_dir + '28*')[0] #get file path of sensor
    rom = device_path.split('/')[-1] #get rom name

    sleep(0.5)
    print('Temperature Device ROM: '+ rom)
    return device_path, rom

def read_temp_raw(device_path):
    with open(device_path +'/w1_slave','r') as f:
        valid, temp = f.readlines()
    return valid, temp
 
def read_temp(device_path):
    valid, temp = read_temp_raw(device_path)

    while 'YES' not in valid:
        sleep(0.2)
        valid, temp = read_temp_raw()

    pos = temp.index('t=')
    if pos != -1:
        #read the temperature .
        temp_string = temp[pos+2:]
        temp_c = float(temp_string)/1000.0 
        temp_f = temp_c * (9.0 / 5.0) + 32.0
        return temp_c, temp_f

temp_dev_path = init_temp()

while True:
    c, f = read_temp(temp_dev_path)
    print('C={:,.3f} F={:,.3f}'.format(c, f))
    sleep(1)

