/*
 * Etapa 1 — Teste inicial do ambiente.
 * Pisca o LED que ja vem soldado na placa ESP32 DevKit (GPIO 2).
 * Nenhuma ligacao externa e necessaria.
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define LED_ONBOARD GPIO_NUM_2
#define INTERVALO_MS 500

static const char *TAG = "blink";

void app_main(void)
{
    gpio_reset_pin(LED_ONBOARD);
    gpio_set_direction(LED_ONBOARD, GPIO_MODE_OUTPUT);

    ESP_LOGI(TAG, "Ambiente OK! Piscando o LED da placa no GPIO %d.", LED_ONBOARD);

    bool aceso = false;
    while (true) {
        aceso = !aceso;
        gpio_set_level(LED_ONBOARD, aceso);
        ESP_LOGI(TAG, "LED %s", aceso ? "ACESO" : "apagado");
        vTaskDelay(pdMS_TO_TICKS(INTERVALO_MS));
    }
}
