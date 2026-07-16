#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define PINO_BUZZER GPIO_NUM_33

#define BIP_MS 120
#define PAUSA_ENTRE_BIPS_MS 120
#define PAUSA_LONGA_MS 1500

static const char *TAG = "buzzer";

static void bip(uint32_t duracao_ms)
{
    gpio_set_level(PINO_BUZZER, 1);
    vTaskDelay(pdMS_TO_TICKS(duracao_ms));
    gpio_set_level(PINO_BUZZER, 0);
}

void app_main(void)
{
    gpio_reset_pin(PINO_BUZZER);
    gpio_set_direction(PINO_BUZZER, GPIO_MODE_OUTPUT);
    gpio_set_level(PINO_BUZZER, 0);

    ESP_LOGI(TAG, "Buzzer ativo no GPIO %d.", PINO_BUZZER);

    while (true) {
        ESP_LOGI(TAG, "bip bip");
        bip(BIP_MS);
        vTaskDelay(pdMS_TO_TICKS(PAUSA_ENTRE_BIPS_MS));
        bip(BIP_MS);

        vTaskDelay(pdMS_TO_TICKS(PAUSA_LONGA_MS));
    }
}
