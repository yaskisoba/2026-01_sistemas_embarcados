#include "conectividade.h"
#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "nvs_flash.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "secrets.h"
#include "config.h"

static const char *TAG = "conect";
static esp_mqtt_client_handle_t mqtt;
static volatile bool online = false;

static volatile bool tem_novo_sp = false;
static volatile float novo_sp = 0;

static void wifi_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "Wi-Fi conectado! IP: " IPSTR, IP2STR(&e->ip_info.ip));
        esp_netif_dns_info_t dns = {0};
        dns.ip.type = ESP_IPADDR_TYPE_V4;
        dns.ip.u_addr.ip4.addr = esp_ip4addr_aton("8.8.8.8");
        esp_netif_set_dns_info(e->esp_netif, ESP_NETIF_DNS_MAIN, &dns);
    }
}

static void mqtt_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t e = (esp_mqtt_event_handle_t)data;
    switch ((esp_mqtt_event_id_t)id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT conectado.");
            online = true;
            esp_mqtt_client_subscribe(mqtt, TOPICO_CMD, 0);
            break;
        case MQTT_EVENT_DISCONNECTED:
            online = false;
            break;
        case MQTT_EVENT_DATA: {
            char buf[16] = {0};
            int n = e->data_len < 15 ? e->data_len : 15;
            memcpy(buf, e->data, n);
            float v = strtof(buf, NULL);
            if (v > 0) { novo_sp = v; tem_novo_sp = true; }
            ESP_LOGI(TAG, "alvo remoto recebido: %.1f", v);
            break;
        }
        default:
            break;
    }
}

void conect_init(void)
{
    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

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

    esp_mqtt_client_config_t mcfg = {.broker.address.uri = MQTT_BROKER_URI};
    mqtt = esp_mqtt_client_init(&mcfg);
    esp_mqtt_client_register_event(mqtt, ESP_EVENT_ANY_ID, mqtt_handler, NULL);
    esp_mqtt_client_start(mqtt);
    ESP_LOGI(TAG, "Conectividade iniciada (Wi-Fi '%s').", WIFI_SSID);
}

bool conect_online(void) { return online; }

void conect_publicar_status(const char *json)
{
    if (online) esp_mqtt_client_publish(mqtt, TOPICO_STATUS, json, 0, 0, 0);
}

bool conect_consumir_setpoint(float *valor)
{
    if (!tem_novo_sp) return false;
    *valor = novo_sp;
    tem_novo_sp = false;
    return true;
}
