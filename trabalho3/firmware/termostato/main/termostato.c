#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/i2c_master.h"
#include "driver/gpio.h"
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
#define PINO_LED_PRESENCA GPIO_NUM_2

#define SETPOINT_INICIAL 22.0f
#define SETPOINT_MIN 10.0f
#define SETPOINT_MAX 35.0f
#define SETPOINT_PASSO 0.5f
#define HISTERESE 0.5f
#define ECO_BANDA 3.0f
#define TIMEOUT_AUSENTE_MS 15000

typedef enum { AQUECENDO, RESFRIANDO, CONFORTO } estado_t;

typedef struct {
    float temp;
    int umidade;
    float pressao;
    float setpoint;
    estado_t estado;
    bool ausente;
} sistema_t;

typedef enum { CMD_DELTA, CMD_ABSOLUTO, CMD_BOTAO } tipo_cmd_t;
typedef struct { tipo_cmd_t tipo; float valor; } comando_t;

static const char *TAG = "termostato";

static sistema_t sis;
static bool tem_sensor;
static SemaphoreHandle_t mutex_estado;
static SemaphoreHandle_t mutex_i2c;
static QueueHandle_t fila_comandos;

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

static void task_sensores(void *arg)
{
    int ciclo = 0;
    while (true) {
        if (tem_sensor) {
            double t, p;
            xSemaphoreTake(mutex_i2c, portMAX_DELAY);
            bmp280_ler(&t, &p);
            xSemaphoreGive(mutex_i2c);
            xSemaphoreTake(mutex_estado, portMAX_DELAY);
            sis.temp = (float)t;
            sis.pressao = (float)p;
            xSemaphoreGive(mutex_estado);
        }
        if (ciclo % 3 == 0) {
            int u, tt;
            if (dht11_ler(&u, &tt) == 0) {
                xSemaphoreTake(mutex_estado, portMAX_DELAY);
                sis.umidade = u;
                xSemaphoreGive(mutex_estado);
            }
        }
        ciclo++;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void task_entrada(void *arg)
{
    while (true) {
        int passos = encoder_consumir_passos();
        if (passos != 0) {
            comando_t c = {CMD_DELTA, passos * SETPOINT_PASSO};
            xQueueSend(fila_comandos, &c, 0);
        }
        if (encoder_consumir_botao()) {
            comando_t c = {CMD_BOTAO, 0};
            xQueueSend(fila_comandos, &c, 0);
        }
        float sp;
        if (conect_consumir_setpoint(&sp)) {
            comando_t c = {CMD_ABSOLUTO, sp};
            xQueueSend(fila_comandos, &c, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

static void task_controle(void *arg)
{
    float setpoint = persistencia_carregar_setpoint(SETPOINT_INICIAL);
    xSemaphoreTake(mutex_estado, portMAX_DELAY);
    sis.setpoint = setpoint;
    xSemaphoreGive(mutex_estado);

    int64_t ultimo_movimento_us = esp_timer_get_time();
    bool sp_sujo = false;
    int64_t ultimo_ajuste_us = 0;
    bool ausente_ant = false;

    buzzer_bip(60);
    ESP_LOGI(TAG, "Termostato iniciado. Alvo = %.1f C", setpoint);

    while (true) {
        comando_t c;
        bool mudou = false, botao = false;
        while (xQueueReceive(fila_comandos, &c, 0) == pdTRUE) {
            if (c.tipo == CMD_DELTA)         { setpoint += c.valor; mudou = true; }
            else if (c.tipo == CMD_ABSOLUTO) { setpoint = c.valor;  mudou = true; }
            else if (c.tipo == CMD_BOTAO)    { botao = true; }
        }
        if (mudou) {
            if (setpoint < SETPOINT_MIN) setpoint = SETPOINT_MIN;
            if (setpoint > SETPOINT_MAX) setpoint = SETPOINT_MAX;
            buzzer_bip(20);
            sp_sujo = true;
            ultimo_ajuste_us = esp_timer_get_time();
            ESP_LOGI(TAG, "novo alvo = %.1f C", setpoint);
        }
        if (botao) {
            setpoint = SETPOINT_INICIAL;
            sp_sujo = true;
            ultimo_ajuste_us = esp_timer_get_time();
            buzzer_bip(20); vTaskDelay(pdMS_TO_TICKS(60)); buzzer_bip(20);
            ESP_LOGI(TAG, "botao: alvo resetado para %.1f C", setpoint);
        }

        if (sp_sujo && esp_timer_get_time() - ultimo_ajuste_us > 2000000) {
            persistencia_salvar_setpoint(setpoint);
            sp_sujo = false;
        }

        int64_t agora = esp_timer_get_time();
        bool movimento = pir_movimento();
        gpio_set_level(PINO_LED_PRESENCA, movimento);
        if (movimento) ultimo_movimento_us = agora;
        bool ausente = (agora - ultimo_movimento_us) > (int64_t)TIMEOUT_AUSENTE_MS * 1000;

        if (ausente != ausente_ant) {
            ausente_ant = ausente;
            buzzer_bip(40);
            ESP_LOGI(TAG, "%s", ausente ? "-> modo AUSENTE (eco)" : "-> presenca detectada");
        }

        float temp;
        xSemaphoreTake(mutex_estado, portMAX_DELAY);
        temp = sis.temp;
        xSemaphoreGive(mutex_estado);

        float banda = ausente ? ECO_BANDA : HISTERESE;
        estado_t estado = decidir_estado(temp, setpoint, banda);
        aplicar_estado(estado);

        xSemaphoreTake(mutex_estado, portMAX_DELAY);
        sis.setpoint = setpoint;
        sis.estado = estado;
        sis.ausente = ausente;
        xSemaphoreGive(mutex_estado);

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

static void task_display(void *arg)
{
    while (true) {
        sistema_t s;
        xSemaphoreTake(mutex_estado, portMAX_DELAY);
        s = sis;
        xSemaphoreGive(mutex_estado);

        char linha[24];
        ssd1306_limpar();
        ssd1306_texto(0, 4, "TERMOSTATO");
        ssd1306_texto(0, 104, conect_online() ? "ON" : "--");
        if (s.umidade >= 0) snprintf(linha, sizeof(linha), "T:%.1f^C U:%d%%", s.temp, s.umidade);
        else                snprintf(linha, sizeof(linha), "T:%.1f^C", s.temp);
        ssd1306_texto(2, 0, linha);
        snprintf(linha, sizeof(linha), "ALVO: %.1f^C", s.setpoint);
        ssd1306_texto(4, 0, linha);
        snprintf(linha, sizeof(linha), "%s%s", nome_estado(s.estado), s.ausente ? " ECO" : "");
        ssd1306_texto(6, 0, linha);

        xSemaphoreTake(mutex_i2c, portMAX_DELAY);
        ssd1306_flush();
        xSemaphoreGive(mutex_i2c);

        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

static void task_comunicacao(void *arg)
{
    while (true) {
        sistema_t s;
        xSemaphoreTake(mutex_estado, portMAX_DELAY);
        s = sis;
        xSemaphoreGive(mutex_estado);

        char json[160];
        snprintf(json, sizeof(json),
                 "{\"temp\":%.1f,\"umid\":%d,\"alvo\":%.1f,"
                 "\"estado\":\"%s\",\"presente\":%s}",
                 s.temp, s.umidade, s.setpoint, nome_estado(s.estado),
                 s.ausente ? "false" : "true");
        conect_publicar_status(json);

        ESP_LOGI(TAG, "T=%.1f alvo=%.1f %s -> %s %s", s.temp, s.setpoint,
                 s.ausente ? "[AUSENTE]" : "[PRESENTE]", nome_estado(s.estado),
                 conect_online() ? "(online)" : "(offline)");

        vTaskDelay(pdMS_TO_TICKS(3000));
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
    tem_sensor = bmp280_init(bus);
    dht11_init();
    led_rgb_init();
    buzzer_init();
    encoder_init();
    pir_init();
    gpio_reset_pin(PINO_LED_PRESENCA);
    gpio_set_direction(PINO_LED_PRESENCA, GPIO_MODE_OUTPUT);
    persistencia_init();
    conect_init();

    mutex_estado = xSemaphoreCreateMutex();
    mutex_i2c = xSemaphoreCreateMutex();
    fila_comandos = xQueueCreate(10, sizeof(comando_t));

    sis.temp = 0;
    sis.umidade = -1;
    sis.pressao = 0;
    sis.setpoint = SETPOINT_INICIAL;
    sis.estado = CONFORTO;
    sis.ausente = false;

    xTaskCreatePinnedToCore(task_controle,    "controle", 4096, NULL, 7, NULL, 1);
    xTaskCreatePinnedToCore(task_entrada,     "entrada",  3072, NULL, 6, NULL, 1);
    xTaskCreatePinnedToCore(task_sensores,    "sensores", 4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(task_display,     "display",  4096, NULL, 4, NULL, 1);
    xTaskCreatePinnedToCore(task_comunicacao, "comm",     4096, NULL, 3, NULL, 1);
}
