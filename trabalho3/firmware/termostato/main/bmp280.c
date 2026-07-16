#include "bmp280.h"

static i2c_master_dev_handle_t dev;
static bool tem_umidade;

static uint16_t dig_T1, dig_P1;
static int16_t dig_T2, dig_T3;
static int16_t dig_P2, dig_P3, dig_P4, dig_P5, dig_P6, dig_P7, dig_P8, dig_P9;
static double t_fine;

static esp_err_t ler(uint8_t reg, uint8_t *dst, size_t n)
{
    return i2c_master_transmit_receive(dev, &reg, 1, dst, n, 100);
}

static void escrever(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    i2c_master_transmit(dev, buf, sizeof(buf), 100);
}

static void ler_calibracao(void)
{
    uint8_t c[26];
    ler(0x88, c, sizeof(c));
    dig_T1 = c[0] | (c[1] << 8);
    dig_T2 = c[2] | (c[3] << 8);
    dig_T3 = c[4] | (c[5] << 8);
    dig_P1 = c[6] | (c[7] << 8);
    dig_P2 = c[8] | (c[9] << 8);
    dig_P3 = c[10] | (c[11] << 8);
    dig_P4 = c[12] | (c[13] << 8);
    dig_P5 = c[14] | (c[15] << 8);
    dig_P6 = c[16] | (c[17] << 8);
    dig_P7 = c[18] | (c[19] << 8);
    dig_P8 = c[20] | (c[21] << 8);
    dig_P9 = c[22] | (c[23] << 8);
}

bool bmp280_init(i2c_master_bus_handle_t bus)
{
    const uint8_t enderecos[] = {0x76, 0x77};
    for (int i = 0; i < 2; i++) {
        if (i2c_master_probe(bus, enderecos[i], 50) != ESP_OK) continue;
        i2c_device_config_t cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = enderecos[i],
            .scl_speed_hz = 400000,
        };
        i2c_master_bus_add_device(bus, &cfg, &dev);

        uint8_t id = 0;
        if (ler(0xD0, &id, 1) == ESP_OK && (id == 0x60 || id == 0x58)) {
            tem_umidade = (id == 0x60);
            ler_calibracao();
            escrever(0xF4, 0x27);
            escrever(0xF5, 0xA0);
            return true;
        }
        i2c_master_bus_rm_device(dev);
    }
    return false;
}

bool bmp280_tem_umidade(void) { return tem_umidade; }

void bmp280_ler(double *temp_c, double *press_hpa)
{
    uint8_t d[6];
    ler(0xF7, d, sizeof(d));
    int32_t adc_P = ((int32_t)d[0] << 12) | ((int32_t)d[1] << 4) | (d[2] >> 4);
    int32_t adc_T = ((int32_t)d[3] << 12) | ((int32_t)d[4] << 4) | (d[5] >> 4);

    double v1 = (adc_T / 16384.0 - dig_T1 / 1024.0) * dig_T2;
    double v2 = (adc_T / 131072.0 - dig_T1 / 8192.0);
    v2 = v2 * v2 * dig_T3;
    t_fine = v1 + v2;
    *temp_c = t_fine / 5120.0;

    v1 = t_fine / 2.0 - 64000.0;
    v2 = v1 * v1 * dig_P6 / 32768.0;
    v2 = v2 + v1 * dig_P5 * 2.0;
    v2 = v2 / 4.0 + dig_P4 * 65536.0;
    v1 = (dig_P3 * v1 * v1 / 524288.0 + dig_P2 * v1) / 524288.0;
    v1 = (1.0 + v1 / 32768.0) * dig_P1;
    if (v1 == 0.0) { *press_hpa = 0.0; return; }
    double p = 1048576.0 - adc_P;
    p = (p - v2 / 4096.0) * 6250.0 / v1;
    v1 = dig_P9 * p * p / 2147483648.0;
    v2 = p * dig_P8 / 32768.0;
    p = p + (v1 + v2 + dig_P7) / 16.0;
    *press_hpa = p / 100.0;
}
