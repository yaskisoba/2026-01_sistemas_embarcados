/*
 * Etapa 10a - Teste de conectividade Wi-Fi + MQTT.
 * Antes de integrar no termostato, valida a rede isoladamente:
 *   1) conecta ao Wi-Fi (hotspot 2,4 GHz)
 *   2) conecta ao broker MQTT publico
 *   3) publica um contador em TOPICO_STATUS a cada 2 s
 *   4) escuta TOPICO_CMD e mostra no log o que chegar
 *
 * As credenciais ficam em secrets.h (fora do Git); os topicos e o
 * broker, em config.h.
 */
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "secrets.h"
#include "config.h"

static const char *TAG = "conect";
static EventGroupHandle_t eventos_wifi;
#define WIFI_OK BIT0
static esp_mqtt_client_handle_t mqtt;

static void wifi_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi caiu; tentando reconectar...");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "Wi-Fi conectado! IP: " IPSTR, IP2STR(&e->ip_info.ip));
        xEventGroupSetBits(eventos_wifi, WIFI_OK);
    }
}

static void wifi_iniciar(void)
{
    eventos_wifi = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_handler, NULL, NULL));

    wifi_config_t wc = {0};
    strncpy((char *)wc.sta.ssid, WIFI_SSID, sizeof(wc.sta.ssid) - 1);
    strncpy((char *)wc.sta.password, WIFI_PASS, sizeof(wc.sta.password) - 1);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "Conectando ao Wi-Fi '%s'...", WIFI_SSID);
}

static void mqtt_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t e = (esp_mqtt_event_handle_t)data;
    switch ((esp_mqtt_event_id_t)id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT conectado ao broker.");
            esp_mqtt_client_subscribe(mqtt, TOPICO_CMD, 0);
            esp_mqtt_client_publish(mqtt, TOPICO_STATUS, "ola do termostato", 0, 1, 0);
            break;
        case MQTT_EVENT_DATA:
            ESP_LOGI(TAG, "CMD recebido [%.*s]: %.*s",
                     e->topic_len, e->topic, e->data_len, e->data);
            break;
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "MQTT desconectado.");
            break;
        default:
            break;
    }
}

static void mqtt_iniciar(void)
{
    esp_mqtt_client_config_t cfg = {.broker.address.uri = MQTT_BROKER_URI};
    mqtt = esp_mqtt_client_init(&cfg);
    esp_mqtt_client_register_event(mqtt, ESP_EVENT_ANY_ID, mqtt_handler, NULL);
    esp_mqtt_client_start(mqtt);
    ESP_LOGI(TAG, "Conectando ao broker %s...", MQTT_BROKER_URI);
}

void app_main(void)
{
    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    wifi_iniciar();
    xEventGroupWaitBits(eventos_wifi, WIFI_OK, false, true, portMAX_DELAY);
    mqtt_iniciar();

    int contador = 0;
    char msg[64];
    while (true) {
        snprintf(msg, sizeof(msg), "{\"contador\":%d}", contador++);
        esp_mqtt_client_publish(mqtt, TOPICO_STATUS, msg, 0, 1, 0);
        ESP_LOGI(TAG, "publicado em %s: %s", TOPICO_STATUS, msg);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
