/*
 * Painel do termostato: le os sensores e mostra tudo no OLED.
 * Integra, num so firmware, os tres perifericos ja validados:
 *   - OLED SSD1306 (I2C, 0x3C)  -> saida
 *   - BMP280       (I2C, 0x76)  -> temperatura e pressao
 *   - DHT11        (GPIO 4)     -> umidade
 * O OLED e o BMP280 compartilham o mesmo barramento I2C (SDA 21, SCL 22).
 *
 * Layout da tela (faixa amarela no topo = titulo):
 *   TERMOSTATO
 *   TEMP: xx.x C
 *   UMID: xx %
 *   PRES: xxxx HPA
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "ssd1306.h"
#include "bmp280.h"
#include "dht11.h"

#define PINO_SDA GPIO_NUM_21
#define PINO_SCL GPIO_NUM_22

static const char *TAG = "painel";

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

    ssd1306_init(bus);
    dht11_init();
    bool tem_sensor = bmp280_init(bus);
    if (!tem_sensor) ESP_LOGE(TAG, "BMP280 nao encontrado!");

    int umidade = -1; /* mantem a ultima leitura valida do DHT11 */

    while (true) {
        double temp = 0, press = 0;
        if (tem_sensor) bmp280_ler(&temp, &press);

        int u, t;
        if (dht11_ler(&u, &t) == 0) umidade = u;

        char linha[24];
        ssd1306_limpar();
        ssd1306_texto(0, 22, "TERMOSTATO");

        snprintf(linha, sizeof(linha), "TEMP: %.1f^C", temp);
        ssd1306_texto(2, 0, linha);

        if (umidade >= 0) snprintf(linha, sizeof(linha), "UMID: %d %%", umidade);
        else              snprintf(linha, sizeof(linha), "UMID: --");
        ssd1306_texto(4, 0, linha);

        snprintf(linha, sizeof(linha), "PRES: %.0f HPA", press);
        ssd1306_texto(6, 0, linha);

        ssd1306_flush();

        ESP_LOGI(TAG, "T=%.1fC U=%d%% P=%.0fhPa", temp, umidade, press);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
