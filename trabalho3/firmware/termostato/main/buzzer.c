#include "buzzer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

#define PINO_BUZZER GPIO_NUM_33

void buzzer_init(void)
{
    gpio_reset_pin(PINO_BUZZER);
    gpio_set_direction(PINO_BUZZER, GPIO_MODE_OUTPUT);
    gpio_set_level(PINO_BUZZER, 0);
}

void buzzer_bip(int duracao_ms)
{
    gpio_set_level(PINO_BUZZER, 1);
    vTaskDelay(pdMS_TO_TICKS(duracao_ms));
    gpio_set_level(PINO_BUZZER, 0);
}
