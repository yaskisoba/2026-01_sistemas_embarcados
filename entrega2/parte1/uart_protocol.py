import struct
import serial
import logging
from dataclasses import dataclass
from typing import Optional

from config import (
    MATRICULA_6_DIGITOS,
    UART_PORT, UART_BAUD, UART_TIMEOUT,
    CMD_GET_INT, CMD_GET_FLOAT, CMD_GET_STRING,
    CMD_SEND_INT, CMD_SEND_FLOAT, CMD_SEND_STR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)



def _matricula_bytes() -> bytes:
    if len(MATRICULA_6_DIGITOS) != 6:
        raise ValueError("MATRICULA_6_DIGITOS deve ter exatamente 6 elementos.")
    for d in MATRICULA_6_DIGITOS:
        if not (0 <= d <= 9):
            raise ValueError(f"Dígito inválido na matrícula: {d}. Use 0–9.")
    return bytes(reversed(MATRICULA_6_DIGITOS))


def _ultimo_digito() -> int:
    return MATRICULA_6_DIGITOS[-1]



@dataclass
class RespostaUART:
    comando: int
    sucesso: bool
    dados_brutos: bytes = b""
    valor_int: Optional[int] = None
    valor_float: Optional[float] = None
    valor_str: Optional[str] = None
    erro: str = ""

    def __str__(self) -> str:
        if not self.sucesso:
            return f"[ERRO] CMD=0x{self.comando:02X} → {self.erro}"
        partes = [f"CMD=0x{self.comando:02X}"]
        if self.valor_int is not None:
            partes.append(f"int={self.valor_int}")
        if self.valor_float is not None:
            partes.append(f"float={self.valor_float:.6g}")
        if self.valor_str is not None:
            partes.append(f"str='{self.valor_str}'")
        return " | ".join(partes)


class UARTClient:
    """Cliente UART Simplificado para a Raspberry Pi (Parte 1)."""

    def __init__(self, port: str = UART_PORT, baud: int = UART_BAUD,
                 timeout: float = UART_TIMEOUT):
        self.port    = port
        self.baud    = baud
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None


    def conectar(self) -> None:
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        log.info("UART aberta: %s @ %d baud", self.port, self.baud)

    def desconectar(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            log.info("UART fechada.")

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *_):
        self.desconectar()


    def _enviar(self, dados: bytes) -> None:
        hex_str = " ".join(f"0x{b:02X}" for b in dados)
        log.debug("TX (%d bytes): %s", len(dados), hex_str)
        self._ser.reset_input_buffer()
        self._ser.write(dados)

    def _receber(self, n_bytes: int) -> bytes:
        dados = self._ser.read(n_bytes)
        if len(dados) != n_bytes:
            raise TimeoutError(
                f"Timeout: esperava {n_bytes} bytes, recebeu {len(dados)}."
            )
        hex_str = " ".join(f"0x{b:02X}" for b in dados)
        log.debug("RX (%d bytes): %s", len(dados), hex_str)
        return dados


    @staticmethod
    def _pacote_solicitacao(cmd: int) -> bytes:
        return bytes([cmd]) + _matricula_bytes()

    @staticmethod
    def _pacote_envio_int(valor: int) -> bytes:
        return (bytes([CMD_SEND_INT])
                + struct.pack("<i", valor)
                + _matricula_bytes())

    @staticmethod
    def _pacote_envio_float(valor: float) -> bytes:
        return (bytes([CMD_SEND_FLOAT])
                + struct.pack("<f", valor)
                + _matricula_bytes())

    @staticmethod
    def _pacote_envio_str(texto: str) -> bytes:
        encoded = texto.encode("utf-8")
        n = len(encoded)
        if n > 255:
            raise ValueError("String muito longa (máx. 255 bytes).")
        return (bytes([CMD_SEND_STR, n])
                + encoded
                + _matricula_bytes())


    def solicitar_int(self) -> RespostaUART:
        cmd = CMD_GET_INT
        try:
            self._enviar(self._pacote_solicitacao(cmd))
            raw = self._receber(4)
            valor = struct.unpack("<i", raw)[0]
            log.info("A1 → int recebido: %d", valor)
            return RespostaUART(cmd, True, raw, valor_int=valor)
        except Exception as e:
            log.error("A1 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))

    def solicitar_float(self) -> RespostaUART:
        cmd = CMD_GET_FLOAT
        try:
            self._enviar(self._pacote_solicitacao(cmd))
            raw = self._receber(4)
            valor = struct.unpack("<f", raw)[0]
            log.info("A2 → float recebido: %.6g", valor)
            return RespostaUART(cmd, True, raw, valor_float=valor)
        except Exception as e:
            log.error("A2 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))

    def solicitar_string(self) -> RespostaUART:
        cmd = CMD_GET_STRING
        try:
            self._enviar(self._pacote_solicitacao(cmd))
            n_raw = self._receber(1)
            n = n_raw[0]
            raw_str = self._receber(n)
            texto = raw_str.decode("utf-8", errors="replace")
            log.info("A3 → string recebida (%d bytes): '%s'", n, texto)
            return RespostaUART(cmd, True, n_raw + raw_str, valor_str=texto)
        except Exception as e:
            log.error("A3 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))


    def enviar_int(self, valor: int) -> RespostaUART:
        cmd = CMD_SEND_INT
        try:
            self._enviar(self._pacote_envio_int(valor))
            raw = self._receber(4)
            resultado = struct.unpack("<i", raw)[0]
            esperado  = valor * _ultimo_digito()
            log.info("B1 → enviado: %d | resposta: %d (esperado: %d)",
                     valor, resultado, esperado)
            return RespostaUART(cmd, True, raw, valor_int=resultado)
        except Exception as e:
            log.error("B1 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))

    def enviar_float(self, valor: float) -> RespostaUART:
        cmd = CMD_SEND_FLOAT
        try:
            self._enviar(self._pacote_envio_float(valor))
            raw = self._receber(4)
            resultado = struct.unpack("<f", raw)[0]
            esperado  = valor * _ultimo_digito()
            log.info("B2 → enviado: %.6g | resposta: %.6g (esperado: %.6g)",
                     valor, resultado, esperado)
            return RespostaUART(cmd, True, raw, valor_float=resultado)
        except Exception as e:
            log.error("B2 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))

    def enviar_string(self, texto: str) -> RespostaUART:
        cmd = CMD_SEND_STR
        try:
            self._enviar(self._pacote_envio_str(texto))
            n_raw = self._receber(1)
            n = n_raw[0]
            raw_str = self._receber(n)
            resposta = raw_str.decode("utf-8", errors="replace")
            esperado = f"Resposta da UART: {texto}"
            log.info("B3 → enviado: '%s' | resposta: '%s'", texto, resposta)
            if resposta != esperado:
                log.warning("Resposta diferente do esperado: '%s'", esperado)
            return RespostaUART(cmd, True, n_raw + raw_str, valor_str=resposta)
        except Exception as e:
            log.error("B3 falhou: %s", e)
            return RespostaUART(cmd, False, erro=str(e))
