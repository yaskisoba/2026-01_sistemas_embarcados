from __future__ import annotations

import logging
import struct
import threading
import time
from typing import List

import serial


log = logging.getLogger(__name__)

_MODBUS_EXCEPTIONS = {
    0x01: "Illegal Function",
    0x02: "Illegal Data Address",
    0x03: "Illegal Data Value",
    0x04: "Slave Device Failure",
}


class ModbusException(RuntimeError):
    def __init__(self, code: int, slave: int, func: int) -> None:
        self.code = code
        self.slave = slave
        self.func = func & 0x7F
        name = _MODBUS_EXCEPTIONS.get(code, f"0x{code:02X}")
        super().__init__(f"Escravo 0x{slave:02X} exceção {name} (func=0x{self.func:02X})")


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
    return bytes(int(c) for c in matricula_6)


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
        self._lock = threading.Lock()

    def _append_crc(self, body: bytes) -> bytes:
        crc = crc16_modbus(body)
        return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    @staticmethod
    def _validate_crc(frame: bytes) -> bool:
        if len(frame) < 3:
            return False
        received = frame[-2] | (frame[-1] << 8)
        expected = crc16_modbus(frame[:-2])
        return received == expected

    def _build_read_request(self, slave: int, start: int, qty: int) -> bytes:
        body = struct.pack("<BBHH", slave, 0x03, start, qty)
        return self._append_crc(body + self._matricula)

    def _build_write_request(self, slave: int, start: int, values: List[int]) -> bytes:
        registers = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        body = struct.pack("<BBHHB", slave, 0x10, start, len(values), len(registers))
        return self._append_crc(body + registers + self._matricula)

    def _exchange(self, request: bytes) -> bytes:
        last_exc: Exception | None = None

        with self._lock:
            for attempt in range(1, self.retries + 1):
                try:
                    with serial.Serial(
                        port=self.port,
                        baudrate=self.baudrate,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=self.timeout_s,
                        xonxoff=False,
                        rtscts=False,
                        dsrdtr=False,
                    ) as ser:
                        ser.reset_input_buffer()
                        ser.write(request)
                        ser.flush()
                        log.debug("TX: %s", request.hex(" "))

                        header = ser.read(2)
                        if len(header) < 2:
                            raise TimeoutError(
                                f"RX incompleto: cabeçalho {len(header)} bytes (esperado 2)"
                            )

                        func = header[1]
                        if func & 0x80:
                            tail = ser.read(3)
                            response = header + tail
                            min_len = 5
                        elif func == 0x03:
                            bc_byte = ser.read(1)
                            if not bc_byte:
                                raise TimeoutError("RX incompleto: byte_count ausente")
                            byte_count = bc_byte[0]
                            tail = ser.read(byte_count + 2)
                            response = header + bc_byte + tail
                            min_len = 3 + byte_count + 2
                        elif func == 0x10:
                            tail = ser.read(6)
                            response = header + tail
                            min_len = 8
                        else:
                            raise RuntimeError(f"Função MODBUS inesperada: 0x{func:02X}")

                    if len(response) < min_len:
                        raise TimeoutError(
                            f"RX incompleto: {len(response)} bytes (esperado {min_len})"
                        )
                    if not self._validate_crc(response):
                        raise ValueError("CRC inválido na resposta")
                    log.debug("RX: %s", response.hex(" "))
                    if response[1] & 0x80:
                        raise ModbusException(response[2], response[0], response[1])
                    return response
                except Exception as exc:
                    last_exc = exc
                    if attempt < self.retries:
                        log.debug(
                            "Falha MODBUS tentativa %d/%d: %s", attempt, self.retries, exc
                        )
                        time.sleep(0.05)
                    else:
                        log.warning(
                            "Falha MODBUS tentativa %d/%d: %s", attempt, self.retries, exc
                        )

        raise RuntimeError(f"Transação MODBUS falhou: {last_exc}")

    def read_holding_registers(self, slave: int, start: int, qty: int) -> List[int]:
        tx = self._build_read_request(slave, start, qty)
        rx = self._exchange(tx)

        if rx[0] != slave or rx[1] != 0x03:
            raise RuntimeError(f"Resposta inesperada: {rx.hex(' ')}")
        byte_count = rx[2]
        if byte_count % 2:
            raise RuntimeError(f"Byte count inválido: {byte_count}")

        regs: List[int] = []
        data = rx[3:-2]
        for i in range(0, len(data), 2):
            regs.append((data[i] << 8) | data[i + 1])
        return regs

    def write_multiple_registers(self, slave: int, start: int, values: List[int]) -> None:
        if not values:
            raise ValueError("Ao menos 1 registrador é necessário.")
        tx = self._build_write_request(slave, start, values)
        rx = self._exchange(tx)
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
