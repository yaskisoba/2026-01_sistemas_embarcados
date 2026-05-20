import sys
import os
import struct
import logging
from dataclasses import dataclass
from typing import Optional

_PARTE2 = os.path.dirname(os.path.abspath(__file__))
_PARTE1 = os.path.join(_PARTE2, "..", "parte1")

if _PARTE2 not in sys.path:
    sys.path.insert(0, _PARTE2)
if _PARTE1 not in sys.path:
    sys.path.append(_PARTE1)

import config
from crc16 import calcular_crc16
from uart_protocol import UARTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_SUBCMDS_GET  = {config.CMD_GET_INT, config.CMD_GET_FLOAT, config.CMD_GET_STRING}
_SUBCMDS_SEND = {config.CMD_SEND_INT, config.CMD_SEND_FLOAT, config.CMD_SEND_STR}


def _hex(data: bytes) -> str:
    return " ".join(f"0x{b:02X}" for b in data)

def _imprimir_pacote(titulo: str, data: bytes) -> None:
    print(f"  {titulo} ({len(data)} bytes): {_hex(data)}")

def _matricula_bytes() -> bytes:
    return bytes(config.MATRICULA_6_DIGITOS)

def _ultimo_digito() -> int:
    return config.MATRICULA_6_DIGITOS[-1]


@dataclass
class RespostaMODBUS:
    subcmd: int
    sucesso: bool
    tx_bytes: bytes = b""
    rx_bytes: bytes = b""
    valor_int: Optional[int] = None
    valor_float: Optional[float] = None
    valor_str: Optional[str] = None
    erro: str = ""

    def __str__(self) -> str:
        if not self.sucesso:
            return f"[ERRO] SUB=0x{self.subcmd:02X} → {self.erro}"
        partes = [f"SUB=0x{self.subcmd:02X}"]
        if self.valor_int is not None:
            partes.append(f"int={self.valor_int}")
        if self.valor_float is not None:
            partes.append(f"float={self.valor_float:.6g}")
        if self.valor_str is not None:
            partes.append(f"str='{self.valor_str}'")
        return " | ".join(partes)


class ModbusClient(UARTClient):

    def _construir_pacote(self, subcmd: int, dados_payload: bytes = b"") -> bytes:
        func  = config.FUNC_GET if subcmd in _SUBCMDS_GET else config.FUNC_SEND
        corpo = bytes([config.MODBUS_ADDR, func, subcmd]) + dados_payload + _matricula_bytes()
        crc   = calcular_crc16(corpo)
        return corpo + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    @staticmethod
    def _verificar_crc(corpo: bytes, crc_bytes: bytes) -> None:
        calc = calcular_crc16(corpo)
        recv = crc_bytes[0] | (crc_bytes[1] << 8)
        if calc != recv:
            raise ValueError(f"CRC inválido — calculado=0x{calc:04X}, recebido=0x{recv:04X}")

    def _receber_resposta_fixo(self, n_dados: int) -> tuple[bytes, bytes]:
        header = self._receber(3)  # addr + func + subcmd
        addr, func, subcmd = header

        if func & 0x80:
            exc   = self._receber(1)
            crc_b = self._receber(2)
            self._verificar_crc(header + exc, crc_b)
            raise RuntimeError(f"Erro MODBUS: FUNC=0x{func:02X}, exceção=0x{exc[0]:02X}")

        dados = self._receber(n_dados)
        crc_b = self._receber(2)
        self._verificar_crc(header + dados, crc_b)
        return header + dados + crc_b, dados

    def _receber_resposta_string(self) -> tuple[bytes, bytes]:
        header = self._receber(3)  # addr + func + subcmd
        addr, func, subcmd = header

        if func & 0x80:
            exc   = self._receber(1)
            crc_b = self._receber(2)
            self._verificar_crc(header + exc, crc_b)
            raise RuntimeError(f"Erro MODBUS: FUNC=0x{func:02X}, exceção=0x{exc[0]:02X}")

        len_b = self._receber(1)
        n     = len_b[0]
        str_b = self._receber(n)
        crc_b = self._receber(2)
        raw   = header + len_b + str_b + crc_b
        self._verificar_crc(header + len_b + str_b, crc_b)
        return raw, len_b + str_b

    def _enviar_e_imprimir(self, pacote: bytes) -> None:
        _imprimir_pacote("TX", pacote)
        self._enviar(pacote)

    @staticmethod
    def _decodificar_header(raw: bytes) -> str:
        addr, func, subcmd = raw[0], raw[1], raw[2]
        ok = "ERRO" if (func & 0x80) else "OK"
        return (f"    ADDR=0x{addr:02X}  FUNC=0x{func:02X}  SUBCMD=0x{subcmd:02X}  [{ok}]  "
                f"dados={_hex(raw[3:-2])}  CRC={_hex(raw[-2:])}")

    def solicitar_int(self) -> RespostaMODBUS:
        subcmd = config.CMD_GET_INT
        try:
            pkt = self._construir_pacote(subcmd)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_fixo(4)
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            valor = struct.unpack("<i", dados)[0]
            log.info("0x23/0xA1 → int=%d", valor)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_int=valor)
        except Exception as e:
            log.error("0xA1 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))

    def solicitar_float(self) -> RespostaMODBUS:
        subcmd = config.CMD_GET_FLOAT
        try:
            pkt = self._construir_pacote(subcmd)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_fixo(4)
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            valor = struct.unpack("<f", dados)[0]
            log.info("0x23/0xA2 → float=%.6g", valor)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_float=valor)
        except Exception as e:
            log.error("0xA2 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))

    def solicitar_string(self) -> RespostaMODBUS:
        subcmd = config.CMD_GET_STRING
        try:
            pkt = self._construir_pacote(subcmd)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_string()
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            n     = dados[0]
            texto = dados[1:].decode("utf-8", errors="replace")
            log.info("0x23/0xA3 → str(%d)='%s'", n, texto)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_str=texto)
        except Exception as e:
            log.error("0xA3 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))

    def enviar_int(self, valor: int) -> RespostaMODBUS:
        subcmd = config.CMD_SEND_INT
        try:
            payload = struct.pack("<i", valor)
            pkt     = self._construir_pacote(subcmd, payload)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_fixo(4)
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            resultado = struct.unpack("<i", dados)[0]
            log.info("0x16/0xB1 → enviado=%d  resposta=%d", valor, resultado)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_int=resultado)
        except Exception as e:
            log.error("0xB1 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))

    def enviar_float(self, valor: float) -> RespostaMODBUS:
        subcmd = config.CMD_SEND_FLOAT
        try:
            payload = struct.pack("<f", valor)
            pkt     = self._construir_pacote(subcmd, payload)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_fixo(4)
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            resultado = struct.unpack("<f", dados)[0]
            log.info("0x16/0xB2 → enviado=%.6g  resposta=%.6g", valor, resultado)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_float=resultado)
        except Exception as e:
            log.error("0xB2 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))

    def enviar_string(self, texto: str) -> RespostaMODBUS:
        subcmd = config.CMD_SEND_STR
        try:
            encoded = texto.encode("utf-8")
            n       = len(encoded)
            if n > 255:
                raise ValueError("String muito longa (máx. 255 bytes).")
            payload = bytes([n]) + encoded
            pkt     = self._construir_pacote(subcmd, payload)
            self._enviar_e_imprimir(pkt)
            raw, dados = self._receber_resposta_string()
            _imprimir_pacote("RX", raw)
            print(self._decodificar_header(raw))
            resposta = dados[1:].decode("utf-8", errors="replace")
            log.info("0x16/0xB3 → enviado='%s'  resposta='%s'", texto, resposta)
            return RespostaMODBUS(subcmd, True, pkt, raw, valor_str=resposta)
        except Exception as e:
            log.error("0xB3 falhou: %s", e)
            return RespostaMODBUS(subcmd, False, erro=str(e))