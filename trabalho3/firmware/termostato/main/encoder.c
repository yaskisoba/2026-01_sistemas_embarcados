#include "encoder.h"
#include "driver/gpio.h"
#include "esp_timer.h"

#define PINO_CLK GPIO_NUM_18
#define PINO_DT  GPIO_NUM_19
#define PINO_SW  GPIO_NUM_23
#define DEBOUNCE_BOTAO_US 200000

/* Maquina de estados de quadratura (Ben Buxton): 1 passo por clique. */
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

void encoder_init(void)
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
}

int encoder_consumir_passos(void)
{
    int p = passos;
    passos = 0;
    return p;
}

bool encoder_consumir_botao(void)
{
    if (!botao) return false;
    botao = false;
    return true;
}
