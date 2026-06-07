from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from common.modbus_rtu import ModbusRTUClient


log = logging.getLogger(__name__)

_STATUS_READY = 2
_STATUS_ERROR = 3
_POLL_INTERVAL_S = 0.08


@dataclass
class LPRResult:
    ok: bool
    plate: str = ""
    confidence: int = 0
    error_code: int = 0
    status: int = 0


class LPRCameraService:
    def __init__(self, modbus: ModbusRTUClient) -> None:
        self._modbus = modbus

    def capture(self, slave_address: int, timeout_s: float = 2.0) -> LPRResult:
        self._trigger_capture(slave_address)
        try:
            return self._await_capture_result(slave_address, timeout_s)
        finally:
            self._release_trigger(slave_address)

    def _trigger_capture(self, slave: int) -> None:
        self._modbus.write_multiple_registers(slave, 1, [1])

    def _release_trigger(self, slave: int) -> None:
        try:
            self._modbus.write_multiple_registers(slave, 1, [0])
        except Exception as exc:
            log.warning("Falha ao resetar trigger LPR 0x%02X: %s", slave, exc)

    def _await_capture_result(self, slave: int, timeout_s: float) -> LPRResult:
        deadline = time.monotonic() + timeout_s
        status = 0
        while time.monotonic() < deadline:
            status = self._poll_until_ready(slave)
            if status == _STATUS_READY:
                plate, confidence = self._read_capture_payload(slave)
                log.info(
                    "Captura LPR 0x%02X: placa=%s confiança=%d%%",
                    slave,
                    plate,
                    confidence,
                )
                return LPRResult(ok=True, plate=plate, confidence=confidence, status=status)
            if status == _STATUS_ERROR:
                break
            time.sleep(_POLL_INTERVAL_S)
        return LPRResult(ok=False, status=status, error_code=0)

    def _poll_until_ready(self, slave: int) -> int:
        return self._modbus.read_holding_registers(slave, 0, 1)[0]

    def _read_capture_payload(self, slave: int) -> tuple[str, int]:
        regs = self._modbus.read_holding_registers(slave, 2, 5)
        plate = self._modbus.decode_plate_from_regs(regs[:4])
        confidence = regs[4] & 0xFFFF
        return plate, confidence
