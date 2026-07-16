#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define FORCA_PINO GPIO_DRIVE_CAP_1

#define PINO_R GPIO_NUM_25
#define PINO_G GPIO_NUM_26
#define PINO_B GPIO_NUM_27

#define CATODO_COMUM 0

#define RESOLUCAO LEDC_TIMER_10_BIT
#define DUTY_MAX ((1 << 10) - 1)
#define FREQUENCIA_HZ 5000

#define PASSO_FADE_MS 10

static const char *TAG = "led_rgb";

static const gpio_num_t pinos[3] = {PINO_R, PINO_G, PINO_B};
static const ledc_channel_t canais[3] = {LEDC_CHANNEL_0, LEDC_CHANNEL_1, LEDC_CHANNEL_2};

static void led_rgb_iniciar(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = RESOLUCAO,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = FREQUENCIA_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    for (int i = 0; i < 3; i++) {
        ledc_channel_config_t canal = {
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = canais[i],
            .timer_sel = LEDC_TIMER_0,
            .intr_type = LEDC_INTR_DISABLE,
            .gpio_num = pinos[i],
            .duty = 0,
            .hpoint = 0,
        };
        ESP_ERROR_CHECK(ledc_channel_config(&canal));
        ESP_ERROR_CHECK(gpio_set_drive_capability(pinos[i], FORCA_PINO));
    }
}

static void led_rgb_cor(uint8_t r, uint8_t g, uint8_t b)
{
    const uint8_t intensidades[3] = {r, g, b};

    for (int i = 0; i < 3; i++) {
        uint32_t duty = (intensidades[i] * DUTY_MAX) / 255;
        if (!CATODO_COMUM) {
            duty = DUTY_MAX - duty;
        }
        ESP_ERROR_CHECK(ledc_set_duty(LEDC_LOW_SPEED_MODE, canais[i], duty));
        ESP_ERROR_CHECK(ledc_update_duty(LEDC_LOW_SPEED_MODE, canais[i]));
    }
}

static void led_rgb_respirar(uint8_t r, uint8_t g, uint8_t b)
{
    for (int nivel = 0; nivel <= 255; nivel += 5) {
        led_rgb_cor((r * nivel) / 255, (g * nivel) / 255, (b * nivel) / 255);
        vTaskDelay(pdMS_TO_TICKS(PASSO_FADE_MS));
    }
    for (int nivel = 255; nivel >= 0; nivel -= 5) {
        led_rgb_cor((r * nivel) / 255, (g * nivel) / 255, (b * nivel) / 255);
        vTaskDelay(pdMS_TO_TICKS(PASSO_FADE_MS));
    }
}

void app_main(void)
{
    led_rgb_iniciar();
    ESP_LOGI(TAG, "LED RGB nos GPIOs %d (R), %d (G) e %d (B).", PINO_R, PINO_G, PINO_B);

    while (true) {
        ESP_LOGI(TAG, "vermelho - aquecendo");
        led_rgb_respirar(255, 0, 0);

        ESP_LOGI(TAG, "azul - resfriando");
        led_rgb_respirar(0, 0, 255);

        ESP_LOGI(TAG, "verde - eco");
        led_rgb_respirar(0, 255, 0);
    }
}
