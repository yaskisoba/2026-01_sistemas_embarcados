from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional


try:
    import RPi.GPIO as _GPIO  # type: ignore
except Exception:  # pragma: no cover
    _GPIO = None


class GPIOAdapter:
    BCM = "BCM"
    IN = "IN"
    OUT = "OUT"
    PUD_DOWN = "PUD_DOWN"
    RISING = "RISING"

    def __init__(self, force_mock: bool = False) -> None:
        self._mock = force_mock or (_GPIO is None)
        self._callbacks: Dict[int, Callable[[int], None]] = {}
        self._pin_state: Dict[int, int] = {}
        self._lock = threading.Lock()
        self._poll_pins: Dict[int, Callable[[int], None]] = {}
        self._poll_thread: Optional[threading.Thread] = None
        self._running = True

        if not self._mock:
            _GPIO.setwarnings(False)
            _GPIO.cleanup()
            _GPIO.setmode(_GPIO.BCM)

    @property
    def is_mock(self) -> bool:
        return self._mock

    def setup_output(self, pin: int) -> None:
        if self._mock:
            self._pin_state[pin] = 0
            return
        _GPIO.setup(pin, _GPIO.OUT)

    def setup_input(self, pin: int, pull_down: bool = True) -> None:
        if self._mock:
            self._pin_state[pin] = 0
            return
        pud = _GPIO.PUD_DOWN if pull_down else _GPIO.PUD_UP
        _GPIO.setup(pin, _GPIO.IN, pull_up_down=pud)

    def write(self, pin: int, value: int) -> None:
        v = 1 if value else 0
        if self._mock:
            self._pin_state[pin] = v
            return
        _GPIO.output(pin, v)

    def read(self, pin: int) -> int:
        if self._mock:
            return self._pin_state.get(pin, 0)
        return int(_GPIO.input(pin))

    def add_rising_callback(
        self,
        pin: int,
        callback: Callable[[int], None],
        debounce_ms: Optional[int] = None,
    ) -> None:
        if self._mock:
            self._callbacks[pin] = callback
            return
        try:
            _GPIO.remove_event_detect(pin)
        except Exception:
            pass
        try:
            if debounce_ms is None:
                _GPIO.add_event_detect(pin, _GPIO.RISING, callback=callback)
            else:
                _GPIO.add_event_detect(
                    pin,
                    _GPIO.RISING,
                    callback=callback,
                    bouncetime=debounce_ms,
                )
        except RuntimeError:
            # Pino não suporta interrupt (ex: GPIO1/SDA) — usa polling
            self._poll_pins[pin] = callback
            if self._poll_thread is None or not self._poll_thread.is_alive():
                self._poll_thread = threading.Thread(
                    target=self._poll_loop, daemon=True
                )
                self._poll_thread.start()

    def _poll_loop(self) -> None:
        last: Dict[int, int] = {}
        while self._running:
            for pin, cb in list(self._poll_pins.items()):
                try:
                    val = int(_GPIO.input(pin))
                    prev = last.get(pin, 0)
                    if val == 1 and prev == 0:
                        cb(pin)
                    last[pin] = val
                except Exception:
                    pass
            time.sleep(0.01)

    def mock_trigger_rising(self, pin: int) -> None:
        if not self._mock:
            return
        cb = self._callbacks.get(pin)
        if cb:
            cb(pin)

    def cleanup(self) -> None:
        self._running = False
        if self._mock:
            return
        _GPIO.cleanup()
