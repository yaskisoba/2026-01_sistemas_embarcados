idf_component_register(SRCS "conectividade.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi nvs_flash mqtt esp_event esp_netif)
