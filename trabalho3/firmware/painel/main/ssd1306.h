/* Driver minimo do OLED SSD1306 (128x64, I2C). */
#pragma once
#include "driver/i2c_master.h"

/* Usa um barramento I2C ja criado (compartilhado com outros dispositivos). */
void ssd1306_init(i2c_master_bus_handle_t bus);
void ssd1306_limpar(void);
void ssd1306_texto(int pagina, int x, const char *s); /* pagina 0..7, x em px */
void ssd1306_flush(void);
