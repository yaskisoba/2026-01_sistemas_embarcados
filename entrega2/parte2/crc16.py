def calcular_crc16(dados: bytes) -> int:
    crc = 0  
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF