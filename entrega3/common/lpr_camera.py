from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from common.modbus_rtu import ModbusRTUClient


log = logging.getLogger(__name__)


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
        self._modbus.write_multiple_registers(slave_address, 1, [1])

        deadline = time.monotonic() + timeout_s
        status = 0
        while time.monotonic() < deadline:
            status = self._modbus.read_holding_registers(slave_address, 0, 1)[0]
            if status in (2, 3):
                break
            time.sleep(0.08)

        if status != 2:
            self._modbus.write_multiple_registers(slave_address, 1, [0])
            return LPRResult(ok=False, status=status, error_code=0)

        regs = self._modbus.read_holding_registers(slave_address, 2, 5)
        plate = self._modbus.decode_plate_from_regs(regs[:4])
        confidence = regs[4] & 0xFFFF
        error_code = self._modbus.read_holding_registers(slave_address, 7, 1)[0]

        self._modbus.write_multiple_registers(slave_address, 1, [0])
        log.info("LPR 0x%02X capturou placa=%s conf=%d", slave_address, plate, confidence)
        return LPRResult(ok=True, plate=plate, confidence=confidence, error_code=error_code, status=status)
