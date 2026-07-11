/*
 * Etapa 7 - Encoder rotativo KY-040 (ajuste do setpoint).
 * O encoder gera dois sinais (CLK e DT) em quadratura; a sequencia em
 * que eles mudam diz o sentido do giro. Em vez de olhar so uma borda,
 * usamos uma MAQUINA DE ESTADOS (metodo de Ben Buxton): ela acompanha
 * toda a sequencia de um clique e so conta quando o giro e completo e
 * valido, descartando o "tremor" (bounce) do contato sem depender de
 * tempo. Resultado: exatamente um passo por clique. Interrupcao nas
 * bordas de CLK e DT alimenta a maquina; o botao (SW) usa outra ISR.
 *
 * Ligacao (KY-040):
 *   CLK -> GPIO 18    DT -> GPIO 19    SW -> GPIO 23
 *   +   -> 3V3        GND -> GND
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

#define PINO_CLK GPIO_NUM_18
#define PINO_DT  GPIO_NUM_19
#define PINO_SW  GPIO_NUM_23

#define DEBOUNCE_BOTAO_US 200000

#define SETPOINT_MIN   10.0f
#define SETPOINT_MAX   35.0f
#define SETPOINT_PASSO 0.5f

static const char *TAG = "encoder";

/* Tabela de transicao de estados (passo completo). Colunas = (CLK<<1)|DT.
 * Bits 0x10 = giro horario concluido, 0x20 = anti-horario concluido. */
#define R_START     0x0
#define R_CW_FINAL  0x1
#define R_CW_BEGIN  0x2
#define R_CW_NEXT   0x3
#define R_CCW_BEGIN 0x4
#define R_CCW_FINAL 0x5
#define R_CCW_NEXT  0x6
#define DIR_CW  0x10
#define DIR_CCW 0x20

static const uint8_t ttable[7][4] = {
    {R_START,    R_CW_BEGIN,  R_CCW_BEGIN, R_START},
    {R_CW_NEXT,  R_START,     R_CW_FINAL,  R_START | DIR_CW},
    {R_CW_NEXT,  R_CW_BEGIN,  R_START,     R_START},
    {R_CW_NEXT,  R_CW_BEGIN,  R_CW_FINAL,  R_START},
    {R_CCW_NEXT, R_START,     R_CCW_BEGIN, R_START},
    {R_CCW_NEXT, R_CCW_FINAL, R_START,     R_START | DIR_CCW},
    {R_CCW_NEXT, R_CCW_FINAL, R_CCW_BEGIN, R_START},
};

static volatile uint8_t estado = R_START;
static volatile int passos = 0;
static volatile bool botao = false;
static volatile int64_t ultimo_botao_us = 0;

static void isr_encoder(void *arg)
{
    uint8_t pinos = (gpio_get_level(PINO_CLK) << 1) | gpio_get_level(PINO_DT);
    estado = ttable[estado & 0x0F][pinos];
    if ((estado & 0x30) == DIR_CW)  passos++;
    else if ((estado & 0x30) == DIR_CCW) passos--;
}

static void isr_sw(void *arg)
{
    int64_t agora = esp_timer_get_time();
    if (agora - ultimo_botao_us < DEBOUNCE_BOTAO_US) return;
    ultimo_botao_us = agora;
    botao = true;
}

void app_main(void)
{
    gpio_config_t entrada = {
        .pin_bit_mask = (1ULL << PINO_CLK) | (1ULL << PINO_DT) | (1ULL << PINO_SW),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&entrada);

    gpio_set_intr_type(PINO_CLK, GPIO_INTR_ANYEDGE);
    gpio_set_intr_type(PINO_DT, GPIO_INTR_ANYEDGE);
    gpio_set_intr_type(PINO_SW, GPIO_INTR_NEGEDGE);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(PINO_CLK, isr_encoder, NULL);
    gpio_isr_handler_add(PINO_DT, isr_encoder, NULL);
    gpio_isr_handler_add(PINO_SW, isr_sw, NULL);

    float setpoint = 22.0f;
    ESP_LOGI(TAG, "Gire o encoder. Setpoint inicial: %.1f C", setpoint);

    int tratados = 0;
    while (true) {
        int p = passos;
        while (tratados != p) {
            int dir = (p > tratados) ? 1 : -1;
            tratados += dir;
            setpoint += dir * SETPOINT_PASSO;
            if (setpoint < SETPOINT_MIN) setpoint = SETPOINT_MIN;
            if (setpoint > SETPOINT_MAX) setpoint = SETPOINT_MAX;
            ESP_LOGI(TAG, "%s -> setpoint = %.1f C",
                     dir > 0 ? "horario" : "anti-horario", setpoint);
        }

        if (botao) {
            botao = false;
            setpoint = 22.0f;
            ESP_LOGI(TAG, "BOTAO: setpoint resetado para %.1f C", setpoint);
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
