from gpiozero import Buzzer
from time import sleep

buzzer = Buzzer(22)

for i in range(1):
    for j in range(5):
        buzzer.on()
        sleep(0.2)
        buzzer.off()
        sleep(0.1)




