/* Conectividade Wi-Fi + MQTT do termostato.
 * Nao bloqueia: se a rede cair, o controle local continua funcionando. */
#pragma once
#include <stdbool.h>

void conect_init(void);                    /* inicia Wi-Fi e MQTT (assincrono) */
bool conect_online(void);                  /* true se o MQTT esta conectado */
void conect_publicar_status(const char *json);
bool conect_consumir_setpoint(float *valor); /* true se chegou novo alvo remoto */
