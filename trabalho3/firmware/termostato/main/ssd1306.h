#pragma once
#include "driver/i2c_master.h"

void ssd1306_init(i2c_master_bus_handle_t bus);
void ssd1306_limpar(void);
void ssd1306_texto(int pagina, int x, const char *s);
void ssd1306_flush(void);
