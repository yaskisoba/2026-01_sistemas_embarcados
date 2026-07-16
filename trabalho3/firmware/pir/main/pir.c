#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define PINO_PIR GPIO_NUM_13
#define PINO_LED GPIO_NUM_2

static const char *TAG = "pir";

void app_main(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << PINO_PIR),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&cfg);

    gpio_reset_pin(PINO_LED);
    gpio_set_direction(PINO_LED, GPIO_MODE_OUTPUT);

    ESP_LOGI(TAG, "PIR no GPIO %d. Aguarde ~30-60 s de aquecimento.", PINO_PIR);
    ESP_LOGI(TAG, "Fique parado; depois mexa na frente do sensor.");

    int anterior = -1;
    int64_t contador = 0;
    while (true) {
        int nivel = gpio_get_level(PINO_PIR);
        gpio_set_level(PINO_LED, nivel);
        if (nivel != anterior) {
            if (nivel) ESP_LOGW(TAG, ">>> PRESENCA DETECTADA (deteccao #%lld)", ++contador);
            else       ESP_LOGI(TAG, "    sem movimento");
            anterior = nivel;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
