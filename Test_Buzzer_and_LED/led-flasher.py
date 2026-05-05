from time import sleep

from led_toggle import ToggleLED


toggle_led = ToggleLED(23)
toggle_led.toggle()
sleep(20)
toggle_led.toggle()
sleep(1)
toggle_led.close()




