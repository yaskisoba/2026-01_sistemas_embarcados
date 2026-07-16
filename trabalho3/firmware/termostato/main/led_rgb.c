#include "led_rgb.h"
#include "driver/ledc.h"
#include "driver/gpio.h"

#define PINO_R GPIO_NUM_25
#define PINO_G GPIO_NUM_26
#define PINO_B GPIO_NUM_27

#define CATODO_COMUM 0
#define FORCA_PINO GPIO_DRIVE_CAP_1

#define RESOLUCAO LEDC_TIMER_10_BIT
#define DUTY_MAX ((1 << 10) - 1)

static const gpio_num_t pinos[3] = {PINO_R, PINO_G, PINO_B};
static const ledc_channel_t canais[3] = {LEDC_CHANNEL_0, LEDC_CHANNEL_1, LEDC_CHANNEL_2};

void led_rgb_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = RESOLUCAO,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer);

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
        ledc_channel_config(&canal);
        gpio_set_drive_capability(pinos[i], FORCA_PINO);
    }
}

void led_rgb_cor(uint8_t r, uint8_t g, uint8_t b)
{
    const uint8_t intensidades[3] = {r, g, b};
    for (int i = 0; i < 3; i++) {
        uint32_t duty = (intensidades[i] * DUTY_MAX) / 255;
        if (!CATODO_COMUM) duty = DUTY_MAX - duty;
        ledc_set_duty(LEDC_LOW_SPEED_MODE, canais[i], duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, canais[i]);
    }
}
