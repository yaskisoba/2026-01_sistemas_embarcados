#include "dht11.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"

#define PINO_DHT GPIO_NUM_4

static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

static int esperar_nivel(int nivel, int timeout_us)
{
    int64_t inicio = esp_timer_get_time();
    while (gpio_get_level(PINO_DHT) != nivel) {
        if (esp_timer_get_time() - inicio > timeout_us) return -1;
    }
    return (int)(esp_timer_get_time() - inicio);
}

void dht11_init(void)
{
    gpio_reset_pin(PINO_DHT);
    gpio_set_pull_mode(PINO_DHT, GPIO_PULLUP_ONLY);
}

int dht11_ler(int *umidade, int *temperatura)
{
    uint8_t dados[5] = {0};

    gpio_set_direction(PINO_DHT, GPIO_MODE_OUTPUT);
    gpio_set_level(PINO_DHT, 0);
    vTaskDelay(pdMS_TO_TICKS(20));

    portENTER_CRITICAL(&mux);
    gpio_set_level(PINO_DHT, 1);
    esp_rom_delay_us(30);
    gpio_set_direction(PINO_DHT, GPIO_MODE_INPUT);

    int erro = 0;
    if (esperar_nivel(0, 100) < 0) erro = -1;
    else if (esperar_nivel(1, 100) < 0) erro = -2;
    else if (esperar_nivel(0, 100) < 0) erro = -3;

    if (!erro) {
        for (int i = 0; i < 40; i++) {
            if (esperar_nivel(1, 100) < 0) { erro = -4; break; }
            int dur = esperar_nivel(0, 100);
            if (dur < 0) { erro = -5; break; }
            dados[i / 8] <<= 1;
            if (dur > 45) dados[i / 8] |= 1;
        }
    }
    portEXIT_CRITICAL(&mux);

    if (erro) return erro;

    uint8_t soma = dados[0] + dados[1] + dados[2] + dados[3];
    if (soma != dados[4]) return -6;

    *umidade = dados[0];
    *temperatura = dados[2];
    return 0;
}
