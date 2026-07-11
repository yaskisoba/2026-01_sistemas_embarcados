/*
 * Etapa 8 - Sensor de presenca PIR (HC-SR501).
 * O PIR entrega a saida em nivel ALTO enquanto detecta movimento e
 * BAIXO quando nao ha. Vira a base do modo Auto-Away do termostato:
 * sem movimento por um tempo -> recua o setpoint (economia).
 *
 * Ligacao:
 *   VCC -> VIN (5V, vindo do USB)    OUT -> GPIO 13    GND -> GND
 * Usamos o GPIO 13 com PULL-DOWN interno: se o fio de OUT ficar solto,
 * o pino e puxado para baixo (le "sem presenca") em vez de flutuar em
 * alto. Isso torna a leitura confiavel e ajuda a diagnosticar mau contato.
 *
 * O HC-SR501 nao tem LED proprio, entao espelhamos a deteccao no LED
 * de bordo da placa (GPIO 2): acende quando ha presenca, apaga quando nao.
 *
 * Observacoes do HC-SR501:
 *   - Ao ligar, ele tem um aquecimento de ~30-60 s em que pode dar
 *     leituras falsas. Espere estabilizar antes de confiar.
 *   - Os dois potenciometros ajustam sensibilidade e o tempo que a
 *     saida fica alta apos detectar (padrao ~5-8 s).
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define PINO_PIR GPIO_NUM_13
#define PINO_LED GPIO_NUM_2   /* LED de bordo: espelha a deteccao */

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
        gpio_set_level(PINO_LED, nivel);   /* espelha no LED de bordo */
        if (nivel != anterior) {
            if (nivel) ESP_LOGW(TAG, ">>> PRESENCA DETECTADA (deteccao #%lld)", ++contador);
            else       ESP_LOGI(TAG, "    sem movimento");
            anterior = nivel;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
