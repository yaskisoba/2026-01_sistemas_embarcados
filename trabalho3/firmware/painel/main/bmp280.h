/* Driver do BMP280/BME280 (I2C). */
#pragma once
#include <stdbool.h>
#include "driver/i2c_master.h"

/* Detecta e inicializa o sensor no barramento dado. true se encontrado. */
bool bmp280_init(i2c_master_bus_handle_t bus);
bool bmp280_tem_umidade(void);           /* true se BME280 */
void bmp280_ler(double *temp_c, double *press_hpa);
