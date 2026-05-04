from time import sleep

from led_toggle import ToggleLED


toggle_led = ToggleLED(22)
toggle_led.toggle()
sleep(6)
toggle_led.toggle()
sleep(1)
toggle_led.close()




