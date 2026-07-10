/*
 * Etapa 6 - Sensor DHT11 (umidade e temperatura) via protocolo de 1 fio.
 * O DHT11 nao usa I2C: ele responde a um pulso de inicio enviando 40
 * bits como pulsos de larguras diferentes (curto = 0, longo = 1). O
 * firmware cronometra cada pulso em microssegundos. A leitura ocorre
 * dentro de uma secao critica para o RTOS nao interromper no meio e
 * baguncar a temporizacao.
 *
 * Ligacao (modulo DHT11, 3 pinos):
 *   VCC/+ -> 3V3    DATA/OUT/S -> GPIO 4    GND/- -> GND
 * Modulos costumam ter o resistor de pull-up embutido; para o sensor
 * "pelado" de 4 pinos, o pull-up interno abaixo ajuda.
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "esp_log.h"

#define PINO_DHT GPIO_NUM_4

static const char *TAG = "dht11";
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

/* Espera o pino chegar em 'nivel'; retorna a duracao em us ou -1 se estourar. */
static int esperar_nivel(int nivel, int timeout_us)
{
    int64_t inicio = esp_timer_get_time();
    while (gpio_get_level(PINO_DHT) != nivel) {
        if (esp_timer_get_time() - inicio > timeout_us) return -1;
    }
    return (int)(esp_timer_get_time() - inicio);
}

/* Le o DHT11. Retorna 0 em sucesso; negativo em erro. */
static int dht11_ler(int *umidade, int *temperatura)
{
    uint8_t dados[5] = {0};

    /* Pulso de inicio: puxa a linha baixa por ~20 ms (fora da secao critica). */
    gpio_set_direction(PINO_DHT, GPIO_MODE_OUTPUT);
    gpio_set_level(PINO_DHT, 0);
    vTaskDelay(pdMS_TO_TICKS(20));

    portENTER_CRITICAL(&mux);

    gpio_set_level(PINO_DHT, 1);
    esp_rom_delay_us(30);
    gpio_set_direction(PINO_DHT, GPIO_MODE_INPUT);

    int erro = 0;
    /* Resposta do sensor: ~80 us baixo, ~80 us alto. */
    if (esperar_nivel(0, 100) < 0) erro = -1;
    else if (esperar_nivel(1, 100) < 0) erro = -2;
    else if (esperar_nivel(0, 100) < 0) erro = -3;

    if (!erro) {
        for (int i = 0; i < 40 && !erro; i++) {
            if (esperar_nivel(1, 100) < 0) { erro = -4; break; }  /* 50 us baixo */
            int dur = esperar_nivel(0, 100);                      /* mede o alto */
            if (dur < 0) { erro = -5; break; }
            dados[i / 8] <<= 1;
            if (dur > 45) dados[i / 8] |= 1;  /* alto longo = bit 1 */
        }
    }

    portEXIT_CRITICAL(&mux);

    if (erro) return erro;

    /* Verificacao de integridade (checksum). */
    uint8_t soma = dados[0] + dados[1] + dados[2] + dados[3];
    if (soma != dados[4]) return -6;

    *umidade = dados[0];      /* parte inteira (%) */
    *temperatura = dados[2];  /* parte inteira (C) */
    return 0;
}

void app_main(void)
{
    gpio_reset_pin(PINO_DHT);
    gpio_set_pull_mode(PINO_DHT, GPIO_PULLUP_ONLY);

    ESP_LOGI(TAG, "Lendo DHT11 no GPIO %d.", PINO_DHT);

    while (true) {
        int umid, temp;
        int r = dht11_ler(&umid, &temp);
        if (r == 0) {
            ESP_LOGI(TAG, "UR = %d %% | T = %d C", umid, temp);
        } else {
            ESP_LOGW(TAG, "falha na leitura (codigo %d)", r);
        }
        vTaskDelay(pdMS_TO_TICKS(2000));  /* DHT11 pede >=1 s entre leituras */
    }
}
