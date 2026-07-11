/*
 * Termostato inteligente - controle com Auto-Away (etapa 9).
 * Integra os perifericos ja validados para formar o termostato:
 *   BMP280 -> temperatura | encoder -> setpoint | LED RGB -> estado
 *   OLED -> tela | buzzer -> confirmacao | DHT11 -> umidade
 *   PIR   -> presenca (modo Auto-Away)
 *
 * Controle por HISTERESE (faixa de conforto de +/- banda):
 *   T < alvo - banda -> AQUECENDO  (vermelho)
 *   T > alvo + banda -> RESFRIANDO (azul)
 *   caso contrario   -> CONFORTO   (verde)
 *
 * Auto-Away: sem movimento (PIR) por TIMEOUT_AUSENTE_MS, o termostato
 * entra em modo ausente e ALARGA a faixa de conforto (ECO_BANDA), para
 * relaxar o controle e economizar. Ao detectar movimento, volta ao
 * normal (banda apertada = HISTERESE).
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "ssd1306.h"
#include "bmp280.h"
#include "dht11.h"
#include "led_rgb.h"
#include "buzzer.h"
#include "encoder.h"
#include "pir.h"
#include "conectividade.h"
#include "persistencia.h"

#define PINO_SDA GPIO_NUM_21
#define PINO_SCL GPIO_NUM_22

#define SETPOINT_INICIAL 22.0f
#define SETPOINT_MIN     10.0f
#define SETPOINT_MAX     35.0f
#define SETPOINT_PASSO    0.5f
#define HISTERESE         0.5f   /* faixa de conforto com presenca */
#define ECO_BANDA         3.0f   /* faixa alargada no modo ausente */
#define TIMEOUT_AUSENTE_MS 15000 /* demo; no mundo real seria minutos */

typedef enum { AQUECENDO, RESFRIANDO, CONFORTO } estado_t;
static const char *TAG = "termostato";

static estado_t decidir_estado(float temp, float alvo, float banda)
{
    if (temp < alvo - banda) return AQUECENDO;
    if (temp > alvo + banda) return RESFRIANDO;
    return CONFORTO;
}

static void aplicar_estado(estado_t e)
{
    switch (e) {
        case AQUECENDO:  led_rgb_cor(255, 0, 0); break;
        case RESFRIANDO: led_rgb_cor(0, 0, 255); break;
        case CONFORTO:   led_rgb_cor(0, 255, 0); break;
    }
}

static const char *nome_estado(estado_t e)
{
    switch (e) {
        case AQUECENDO:  return "AQUECENDO";
        case RESFRIANDO: return "RESFRIANDO";
        default:         return "CONFORTO";
    }
}

void app_main(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = I2C_NUM_0,
        .sda_io_num = PINO_SDA,
        .scl_io_num = PINO_SCL,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

    ssd1306_init(bus);
    bool tem_sensor = bmp280_init(bus);
    dht11_init();
    led_rgb_init();
    buzzer_init();
    encoder_init();
    pir_init();
    persistencia_init();
    conect_init(); /* Wi-Fi + MQTT (assincrono, nao trava o controle) */

    /* Restaura o ultimo alvo salvo (sobrevive ao desligamento). */
    float setpoint = persistencia_carregar_setpoint(SETPOINT_INICIAL);
    float temp = 0;
    int umidade = -1;
    bool ausente = false;
    int64_t ultimo_movimento_us = esp_timer_get_time();

    /* Salvamento adiado: grava o alvo na NVS ~2 s apos a ultima mudanca,
     * para uma girada inteira do encoder virar uma unica gravacao. */
    bool sp_alterado = false;
    int64_t ultimo_ajuste_us = 0;

    buzzer_bip(60);
    ESP_LOGI(TAG, "Termostato iniciado. Alvo = %.1f C", setpoint);

    int ciclo = 0;
    while (true) {
        /* Encoder: ajusta o setpoint e confirma com um bip curto. */
        int passos = encoder_consumir_passos();
        if (passos != 0) {
            setpoint += passos * SETPOINT_PASSO;
            if (setpoint < SETPOINT_MIN) setpoint = SETPOINT_MIN;
            if (setpoint > SETPOINT_MAX) setpoint = SETPOINT_MAX;
            buzzer_bip(20);
            sp_alterado = true;
            ultimo_ajuste_us = esp_timer_get_time();
            ESP_LOGI(TAG, "novo alvo = %.1f C", setpoint);
        }
        if (encoder_consumir_botao()) {
            buzzer_bip(20); vTaskDelay(pdMS_TO_TICKS(60)); buzzer_bip(20);
        }

        /* Alvo remoto (via MQTT): ajusta o setpoint pela nuvem. */
        float sp_remoto;
        if (conect_consumir_setpoint(&sp_remoto)) {
            setpoint = sp_remoto;
            if (setpoint < SETPOINT_MIN) setpoint = SETPOINT_MIN;
            if (setpoint > SETPOINT_MAX) setpoint = SETPOINT_MAX;
            buzzer_bip(20);
            sp_alterado = true;
            ultimo_ajuste_us = esp_timer_get_time();
            ESP_LOGI(TAG, "alvo ajustado remotamente = %.1f C", setpoint);
        }

        /* Salva o alvo na NVS ~2 s apos a ultima mudanca (evita desgaste). */
        if (sp_alterado && esp_timer_get_time() - ultimo_ajuste_us > 2000000) {
            persistencia_salvar_setpoint(setpoint);
            sp_alterado = false;
        }

        /* Presenca -> Auto-Away. */
        int64_t agora = esp_timer_get_time();
        if (pir_movimento()) ultimo_movimento_us = agora;
        bool ausente_novo = (agora - ultimo_movimento_us) > (int64_t)TIMEOUT_AUSENTE_MS * 1000;
        if (ausente_novo != ausente) {
            ausente = ausente_novo;
            ESP_LOGI(TAG, "%s", ausente ? "-> modo AUSENTE (eco)" : "-> presenca detectada");
            buzzer_bip(40);
        }

        /* Sensores: temperatura a cada ~1 s, umidade a cada ~3 s. */
        if (tem_sensor && ciclo % 10 == 0) {
            double t, p;
            bmp280_ler(&t, &p);
            temp = (float)t;
        }
        if (ciclo % 30 == 0) {
            int u, tt;
            if (dht11_ler(&u, &tt) == 0) umidade = u;
        }

        /* Controle por histerese (faixa depende do modo). */
        float banda = ausente ? ECO_BANDA : HISTERESE;
        estado_t estado = decidir_estado(temp, setpoint, banda);
        aplicar_estado(estado);

        /* Tela. */
        char linha[24];
        ssd1306_limpar();
        ssd1306_texto(0, 4, "TERMOSTATO");
        ssd1306_texto(0, 104, conect_online() ? "ON" : "--");
        if (umidade >= 0) snprintf(linha, sizeof(linha), "T:%.1f^C U:%d%%", temp, umidade);
        else              snprintf(linha, sizeof(linha), "T:%.1f^C", temp);
        ssd1306_texto(2, 0, linha);
        snprintf(linha, sizeof(linha), "ALVO: %.1f^C", setpoint);
        ssd1306_texto(4, 0, linha);
        snprintf(linha, sizeof(linha), "%s%s", nome_estado(estado), ausente ? " ECO" : "");
        ssd1306_texto(6, 0, linha);
        ssd1306_flush();

        if (ciclo % 10 == 0)
            ESP_LOGI(TAG, "T=%.1f alvo=%.1f %s -> %s %s", temp, setpoint,
                     ausente ? "[AUSENTE]" : "[PRESENTE]", nome_estado(estado),
                     conect_online() ? "(online)" : "(offline)");

        /* Publica o status na nuvem a cada ~3 s (se conectado). */
        if (ciclo % 30 == 0) {
            char json[160];
            snprintf(json, sizeof(json),
                     "{\"temp\":%.1f,\"umid\":%d,\"alvo\":%.1f,"
                     "\"estado\":\"%s\",\"presente\":%s}",
                     temp, umidade, setpoint, nome_estado(estado),
                     ausente ? "false" : "true");
            conect_publicar_status(json);
        }

        ciclo++;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
