#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

#define PINO_SDA GPIO_NUM_21
#define PINO_SCL GPIO_NUM_22
#define ENDERECO_OLED 0x3C
#define OLED_W 128

static const char *TAG = "oled";

static i2c_master_dev_handle_t dev;
static uint8_t fb[OLED_W * 64 / 8];

typedef struct { char c; uint8_t col[5]; } glifo_t;
static const glifo_t FONTE[] = {
    {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
    {':', {0x00, 0x36, 0x36, 0x00, 0x00}},
    {'.', {0x00, 0x60, 0x60, 0x00, 0x00}},
    {'^', {0x00, 0x07, 0x05, 0x07, 0x00}},
    {'0', {0x3E, 0x51, 0x49, 0x45, 0x3E}},
    {'1', {0x00, 0x42, 0x7F, 0x40, 0x00}},
    {'2', {0x42, 0x61, 0x51, 0x49, 0x46}},
    {'3', {0x21, 0x41, 0x45, 0x4B, 0x31}},
    {'4', {0x18, 0x14, 0x12, 0x7F, 0x10}},
    {'5', {0x27, 0x45, 0x45, 0x45, 0x39}},
    {'6', {0x3C, 0x4A, 0x49, 0x49, 0x30}},
    {'7', {0x01, 0x71, 0x09, 0x05, 0x03}},
    {'8', {0x36, 0x49, 0x49, 0x49, 0x36}},
    {'9', {0x06, 0x49, 0x49, 0x29, 0x1E}},
    {'A', {0x7E, 0x11, 0x11, 0x11, 0x7E}},
    {'C', {0x3E, 0x41, 0x41, 0x41, 0x22}},
    {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
    {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
    {'M', {0x7F, 0x02, 0x0C, 0x02, 0x7F}},
    {'N', {0x7F, 0x04, 0x08, 0x10, 0x7F}},
    {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
    {'P', {0x7F, 0x09, 0x09, 0x09, 0x06}},
    {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
    {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
    {'T', {0x01, 0x01, 0x7F, 0x01, 0x01}},
    {'V', {0x1F, 0x20, 0x40, 0x20, 0x1F}},
};

static const uint8_t init_seq[] = {
    0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14,
    0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1,
    0xDB, 0x40, 0xA4, 0xA6, 0xAF,
};

static void oled_cmd(uint8_t c)
{
    uint8_t buf[2] = {0x00, c};
    ESP_ERROR_CHECK(i2c_master_transmit(dev, buf, sizeof(buf), 100));
}

static void oled_flush(void)
{
    oled_cmd(0x21); oled_cmd(0x00); oled_cmd(0x7F);
    oled_cmd(0x22); oled_cmd(0x00); oled_cmd(0x07);

    uint8_t linha[1 + OLED_W];
    linha[0] = 0x40;
    for (int pag = 0; pag < 8; pag++) {
        memcpy(&linha[1], &fb[pag * OLED_W], OLED_W);
        ESP_ERROR_CHECK(i2c_master_transmit(dev, linha, sizeof(linha), 100));
    }
}

static void oled_limpar(void) { memset(fb, 0x00, sizeof(fb)); }

static const uint8_t *glifo(char c)
{
    for (size_t i = 0; i < sizeof(FONTE) / sizeof(FONTE[0]); i++) {
        if (FONTE[i].c == c) return FONTE[i].col;
    }
    return FONTE[0].col;
}

static void oled_texto(int pagina, int x, const char *s)
{
    for (; *s && x + 5 < OLED_W; s++, x += 6) {
        const uint8_t *g = glifo(*s);
        for (int i = 0; i < 5; i++) {
            fb[pagina * OLED_W + x + i] = g[i];
        }
    }
}

static void oled_init(void)
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

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = ENDERECO_OLED,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dev_cfg, &dev));

    for (size_t i = 0; i < sizeof(init_seq); i++) oled_cmd(init_seq[i]);
}

void app_main(void)
{
    oled_init();
    ESP_LOGI(TAG, "OLED pronto. Desenhando previa do termostato.");

    int contador = 0;
    while (true) {
        char linha[24];

        oled_limpar();
        oled_texto(0, 22, "TERMOSTATO");
        oled_texto(2, 0, "TEMP:  24.5^C");
        oled_texto(4, 0, "ALVO:  22.0^C");
        snprintf(linha, sizeof(linha), "CONT:  %d", contador);
        oled_texto(6, 0, linha);
        oled_flush();

        ESP_LOGI(TAG, "contador = %d", contador);
        contador++;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
