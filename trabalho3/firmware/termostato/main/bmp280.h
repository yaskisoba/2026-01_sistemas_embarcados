#pragma once
#include <stdbool.h>
#include "driver/i2c_master.h"

bool bmp280_init(i2c_master_bus_handle_t bus);
bool bmp280_tem_umidade(void);
void bmp280_ler(double *temp_c, double *press_hpa);
