from gpiozero import LED
from time import sleep

led = LED(22)

for j in range(10):
    led.on()
    sleep(0.05)
    led.off()
    sleep(5)




