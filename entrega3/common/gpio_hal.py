from __future__ import annotations

import threading
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

        if not self._mock:
            _GPIO.setwarnings(False)
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
        if debounce_ms is None:
            _GPIO.add_event_detect(pin, _GPIO.RISING, callback=callback)
        else:
            _GPIO.add_event_detect(
                pin,
                _GPIO.RISING,
                callback=callback,
                bouncetime=debounce_ms,
            )

    def mock_trigger_rising(self, pin: int) -> None:
        if not self._mock:
            return
        cb = self._callbacks.get(pin)
        if cb:
            cb(pin)

    def cleanup(self) -> None:
        if self._mock:
            return
        _GPIO.cleanup()
