/* Configuracao de MQTT (nao sensivel, pode versionar). */
#pragma once

/* Broker publico de teste (sem instalacao, sem autenticacao). */
#define MQTT_BROKER_URI "mqtt://broker.hivemq.com"

/* Prefixo unico para nao colidir com outros usuarios do broker publico. */
#define TOPICO_STATUS "fse2026/gustavo/termostato/status"
#define TOPICO_CMD    "fse2026/gustavo/termostato/cmd"
