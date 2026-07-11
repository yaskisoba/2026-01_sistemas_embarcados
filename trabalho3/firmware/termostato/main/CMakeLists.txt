idf_component_register(SRCS "termostato.c" "ssd1306.c" "bmp280.c" "dht11.c"
                            "led_rgb.c" "buzzer.c" "encoder.c" "pir.c"
                            "conectividade.c" "persistencia.c"
                       INCLUDE_DIRS "."
                       REQUIRES driver esp_timer esp_wifi nvs_flash mqtt
                                esp_event esp_netif)
