#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

#define PINO_SDA GPIO_NUM_21
#define PINO_SCL GPIO_NUM_22

static const char *TAG = "bme280";

static i2c_master_dev_handle_t dev;
static bool tem_umidade;

static uint16_t dig_T1, dig_P1;
static int16_t dig_T2, dig_T3;
static int16_t dig_P2, dig_P3, dig_P4, dig_P5, dig_P6, dig_P7, dig_P8, dig_P9;
static uint8_t dig_H1, dig_H3;
static int16_t dig_H2, dig_H4, dig_H5;
static int8_t dig_H6;

static double t_fine;

static esp_err_t ler(uint8_t reg, uint8_t *dst, size_t n)
{
    return i2c_master_transmit_receive(dev, &reg, 1, dst, n, 100);
}

static void escrever(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    ESP_ERROR_CHECK(i2c_master_transmit(dev, buf, sizeof(buf), 100));
}

static void ler_calibracao(void)
{
    uint8_t c[26];
    ESP_ERROR_CHECK(ler(0x88, c, sizeof(c)));
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
    dig_H1 = c[25];

    if (tem_umidade) {
        uint8_t h[7];
        ESP_ERROR_CHECK(ler(0xE1, h, sizeof(h)));
        dig_H2 = h[0] | (h[1] << 8);
        dig_H3 = h[2];
        dig_H4 = (h[3] << 4) | (h[4] & 0x0F);
        dig_H5 = (h[5] << 4) | (h[4] >> 4);
        dig_H6 = (int8_t)h[6];
    }
}

static double compensar_temp(int32_t adc_T)
{
    double v1 = (adc_T / 16384.0 - dig_T1 / 1024.0) * dig_T2;
    double v2 = (adc_T / 131072.0 - dig_T1 / 8192.0);
    v2 = v2 * v2 * dig_T3;
    t_fine = v1 + v2;
    return t_fine / 5120.0;
}

static double compensar_press(int32_t adc_P)
{
    double v1 = t_fine / 2.0 - 64000.0;
    double v2 = v1 * v1 * dig_P6 / 32768.0;
    v2 = v2 + v1 * dig_P5 * 2.0;
    v2 = v2 / 4.0 + dig_P4 * 65536.0;
    v1 = (dig_P3 * v1 * v1 / 524288.0 + dig_P2 * v1) / 524288.0;
    v1 = (1.0 + v1 / 32768.0) * dig_P1;
    if (v1 == 0.0) return 0.0;
    double p = 1048576.0 - adc_P;
    p = (p - v2 / 4096.0) * 6250.0 / v1;
    v1 = dig_P9 * p * p / 2147483648.0;
    v2 = p * dig_P8 / 32768.0;
    p = p + (v1 + v2 + dig_P7) / 16.0;
    return p / 100.0;
}

static double compensar_umid(int32_t adc_H)
{
    double h = t_fine - 76800.0;
    h = (adc_H - (dig_H4 * 64.0 + dig_H5 / 16384.0 * h)) *
        (dig_H2 / 65536.0 * (1.0 + dig_H6 / 67108864.0 * h *
        (1.0 + dig_H3 / 67108864.0 * h)));
    h = h * (1.0 - dig_H1 * h / 524288.0);
    if (h > 100.0) h = 100.0;
    if (h < 0.0) h = 0.0;
    return h;
}

static bool detectar(i2c_master_bus_handle_t bus)
{
    const uint8_t enderecos[] = {0x76, 0x77};
    for (int i = 0; i < 2; i++) {
        if (i2c_master_probe(bus, enderecos[i], 50) != ESP_OK) continue;

        i2c_device_config_t cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = enderecos[i],
            .scl_speed_hz = 400000,
        };
        ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &cfg, &dev));

        uint8_t id = 0;
        if (ler(0xD0, &id, 1) == ESP_OK && (id == 0x60 || id == 0x58)) {
            tem_umidade = (id == 0x60);
            ESP_LOGI(TAG, "Sensor em 0x%02X, ID 0x%02X (%s).", enderecos[i], id,
                     tem_umidade ? "BME280 - com umidade" : "BMP280 - sem umidade");
            return true;
        }
        i2c_master_bus_rm_device(dev);
    }
    return false;
}

void app_main(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = I2C_NUM_0,
        .sda_io_num = PINO_SDA,
        .scl_io_num = PINO_SCL,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

    if (!detectar(bus)) {
        ESP_LOGE(TAG, "Nenhum BME280/BMP280 encontrado (conferir fiacao).");
        return;
    }

    ler_calibracao();
    escrever(0xF2, 0x01);
    escrever(0xF4, 0x27);
    escrever(0xF5, 0xA0);

    while (true) {
        uint8_t d[8];
        ESP_ERROR_CHECK(ler(0xF7, d, sizeof(d)));
        int32_t adc_P = ((int32_t)d[0] << 12) | ((int32_t)d[1] << 4) | (d[2] >> 4);
        int32_t adc_T = ((int32_t)d[3] << 12) | ((int32_t)d[4] << 4) | (d[5] >> 4);
        int32_t adc_H = ((int32_t)d[6] << 8) | d[7];

        double temp = compensar_temp(adc_T);
        double press = compensar_press(adc_P);

        if (tem_umidade) {
            double umid = compensar_umid(adc_H);
            ESP_LOGI(TAG, "T = %.2f C | UR = %.1f %% | P = %.1f hPa", temp, umid, press);
        } else {
            ESP_LOGI(TAG, "T = %.2f C | P = %.1f hPa (sem umidade)", temp, press);
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
