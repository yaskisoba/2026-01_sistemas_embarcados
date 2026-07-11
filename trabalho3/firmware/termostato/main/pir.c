#include "pir.h"
#include "driver/gpio.h"

#define PINO_PIR GPIO_NUM_13 /* pull-down interno: sem sinal -> le baixo */

void pir_init(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << PINO_PIR),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&cfg);
}

bool pir_movimento(void)
{
    return gpio_get_level(PINO_PIR);
}
