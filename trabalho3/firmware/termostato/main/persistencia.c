#include "persistencia.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "esp_log.h"

#define NAMESPACE "termostato"
#define CHAVE "setpoint"

static const char *TAG = "persist";

void persistencia_init(void)
{
    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
}

float persistencia_carregar_setpoint(float padrao)
{
    nvs_handle_t h;
    if (nvs_open(NAMESPACE, NVS_READONLY, &h) != ESP_OK) return padrao;
    int32_t v = 0;
    esp_err_t r = nvs_get_i32(h, CHAVE, &v);
    nvs_close(h);
    if (r != ESP_OK) return padrao;
    float sp = v / 10.0f;
    ESP_LOGI(TAG, "setpoint restaurado da NVS: %.1f C", sp);
    return sp;
}

void persistencia_salvar_setpoint(float setpoint)
{
    nvs_handle_t h;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_i32(h, CHAVE, (int32_t)(setpoint * 10.0f + 0.5f));
    nvs_commit(h);
    nvs_close(h);
    ESP_LOGI(TAG, "setpoint salvo na NVS: %.1f C", setpoint);
}
