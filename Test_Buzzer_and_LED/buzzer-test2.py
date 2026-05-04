from time import sleep

from buzzer_toggle import ToggleBuzzer


toggle_buzzer = ToggleBuzzer(22)

toggle_buzzer.toggle()
sleep(6)
toggle_buzzer.toggle()
sleep(1)
toggle_buzzer.close()




