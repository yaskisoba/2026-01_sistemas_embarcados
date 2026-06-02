import json
from typing import Any, Dict, Optional


Message = Dict[str, Any]


def encode_message(message: Message) -> bytes:
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def decode_message(raw: bytes) -> Message:
    return json.loads(raw.decode("utf-8"))


class LineBuffer:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)

    def pop_line(self) -> Optional[bytes]:
        idx = self._buffer.find(b"\n")
        if idx < 0:
            return None
        line = bytes(self._buffer[:idx])
        del self._buffer[: idx + 1]
        if not line:
            return None
        return line
