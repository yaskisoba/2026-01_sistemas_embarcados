from __future__ import annotations

import logging
import struct
import threading
import time
from typing import List

import serial


log = logging.getLogger(__name__)


def crc16_modbus(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def matricula_bytes(matricula_6: str) -> bytes:
    if len(matricula_6) != 6 or not matricula_6.isdigit():
        raise ValueError("A matrícula deve ter 6 dígitos.")
    digits = [int(c) for c in matricula_6]
    return bytes(reversed(digits))


class ModbusRTUClient:
    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout_s: float,
        retries: int,
        matricula_6: str,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_s = timeout_s
        self.retries = retries
        self._matricula = matricula_bytes(matricula_6)
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout_s,
        )
        log.info("MODBUS RS485 aberto em %s @ %d", self.port, self.baudrate)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _ensure_serial(self) -> serial.Serial:
        if not self._ser or not self._ser.is_open:
            self.connect()
        assert self._ser is not None
        return self._ser

    def _build_frame(self, pdu_wo_crc: bytes) -> bytes:
        payload = pdu_wo_crc + self._matricula
        crc = crc16_modbus(payload)
        return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _validate_crc(self, frame: bytes) -> None:
        body = frame[:-2]
        got = frame[-2] | (frame[-1] << 8)
        expected = crc16_modbus(body)
        if got != expected:
            raise ValueError(f"CRC inválido. esperado=0x{expected:04X}, recebido=0x{got:04X}")

    def _transaction(self, tx: bytes, expected_min_rx: int, expected_exact_rx: int | None = None) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                ser = self._ensure_serial()
                with self._lock:
                    ser.reset_input_buffer()
                    ser.write(tx)
                    time.sleep(0.002)
                    rx = ser.read(expected_exact_rx or expected_min_rx)
                    if len(rx) < expected_min_rx:
                        raise TimeoutError(
                            f"RX incompleto: {len(rx)} bytes (mínimo {expected_min_rx})"
                        )
                    if expected_exact_rx is None and ser.in_waiting:
                        rx += ser.read(ser.in_waiting)
                self._validate_crc(rx)
                return rx
            except Exception as exc:
                last_exc = exc
                log.warning("Falha MODBUS tentativa %d/%d: %s", attempt, self.retries, exc)
                self.close()
                time.sleep(0.05)
        raise RuntimeError(f"Transação MODBUS falhou: {last_exc}")

    def read_holding_registers(self, slave: int, start: int, qty: int) -> List[int]:
        pdu = struct.pack(">BBHH", slave, 0x03, start, qty)
        tx = self._build_frame(pdu)

        expected = 5 + 2 * qty
        rx = self._transaction(tx, expected_min_rx=expected, expected_exact_rx=expected)
        if rx[0] != slave or rx[1] != 0x03:
            raise RuntimeError(f"Resposta inesperada: {rx.hex(' ')}")
        byte_count = rx[2]
        if byte_count != 2 * qty:
            raise RuntimeError(f"Byte count inválido: {byte_count}, esperado {2 * qty}")

        regs: List[int] = []
        data = rx[3 : 3 + byte_count]
        for i in range(0, len(data), 2):
            regs.append((data[i] << 8) | data[i + 1])
        return regs

    def write_multiple_registers(self, slave: int, start: int, values: List[int]) -> None:
        qty = len(values)
        if qty <= 0:
            raise ValueError("Ao menos 1 registrador é necessário.")
        byte_count = qty * 2
        data = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        pdu = struct.pack(">BBHHB", slave, 0x10, start, qty, byte_count) + data
        tx = self._build_frame(pdu)

        expected = 8
        rx = self._transaction(tx, expected_min_rx=expected, expected_exact_rx=expected)
        if rx[0] != slave or rx[1] != 0x10:
            raise RuntimeError(f"Resposta inesperada: {rx.hex(' ')}")

    @staticmethod
    def decode_plate_from_regs(regs_4: List[int]) -> str:
        if len(regs_4) != 4:
            raise ValueError("São necessários 4 registradores para decodificar a placa.")
        chars = []
        for reg in regs_4:
            chars.append(chr((reg >> 8) & 0xFF))
            chars.append(chr(reg & 0xFF))
        return "".join(chars).strip("\x00 ")
