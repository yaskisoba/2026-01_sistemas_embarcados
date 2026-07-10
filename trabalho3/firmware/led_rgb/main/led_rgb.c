/*
 * Etapa 2 - LED RGB com PWM (LEDC).
 * Percorre as tres cores que sinalizam o estado do termostato:
 *   vermelho = aquecendo | azul = resfriando | verde = eco
 *
 * Ligacao (modulo RGB WCMCU de ANODO COMUM):
 *   R -> GPIO 25    G -> GPIO 26    B -> GPIO 27    (-) -> 3V3
 * Apesar de o pino comum ser marcado "-", este modulo e de anodo
 * comum: o comum vai no 3V3 e cada cor acende no nivel baixo.
 *
 * Este modulo NAO tem resistores embutidos. Enquanto nao houver
 * resistores de 220-330 ohm em serie com cada cor, a corrente e
 * limitada por software: os pinos ficam no modo de menor forca
 * (GPIO_DRIVE_CAP_0), que segura a corrente em ~5 mA e protege tanto
 * o LED quanto o pino. Ao adicionar os resistores, troque por
 * GPIO_DRIVE_CAP_DEFAULT para recuperar o brilho pleno.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"

/* Sem resistores externos -> pino fraco. Com resistores -> _DEFAULT.
 * CAP_0 ~5 mA (mais seguro) | CAP_1 ~10 mA (mais brilho, ainda seguro). */
#define FORCA_PINO GPIO_DRIVE_CAP_1

#define PINO_R GPIO_NUM_25
#define PINO_G GPIO_NUM_26
#define PINO_B GPIO_NUM_27

/* Este modulo WCMCU e de ANODO COMUM: o pino "-" (apesar do nome) vai
 * no 3V3 e as cores acendem no nivel baixo. Por isso 0. */
#define CATODO_COMUM 0

#define RESOLUCAO LEDC_TIMER_10_BIT
#define DUTY_MAX ((1 << 10) - 1)
#define FREQUENCIA_HZ 5000

/* Um tick do FreeRTOS = 10 ms por padrao; valores menores arredondam
 * para zero e a animacao roda rapido demais para ser vista. */
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
        /* Aplicado depois do LEDC, que reconfigura o pino ao rotea-lo. */
        ESP_ERROR_CHECK(gpio_set_drive_capability(pinos[i], FORCA_PINO));
    }
}

/* Intensidade de cada cor de 0 a 255. */
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

/* Acende e apaga a cor gradualmente, confirmando que o PWM funciona. */
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
