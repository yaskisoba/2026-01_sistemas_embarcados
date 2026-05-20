import RPi.GPIO as GPIO

class GPIOController:
    def __init__(self):
        self.pwm_instances = {}
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
        except Exception as error:
            raise RuntimeError(
                "Não foi possível acessar a GPIO da Raspberry."
            ) from error

    def setup_output(self, pin):
        GPIO.setup(pin, GPIO.OUT)

    def set_output(self, pin, state):
        GPIO.output(pin, state)

    def setup_input(self, pin, pull_up_down=GPIO.PUD_DOWN):
        GPIO.setup(pin, GPIO.IN, pull_up_down=pull_up_down)

    def add_interrupt(self, pin, edge, callback_function, bouncetime=None):
        if bouncetime:
            GPIO.add_event_detect(pin, edge, callback=callback_function, bouncetime=bouncetime)
        else:
            GPIO.add_event_detect(pin, edge, callback=callback_function)

    def cleanup(self):
        for pwm in self.pwm_instances.values():
            pwm.stop()
        GPIO.cleanup()