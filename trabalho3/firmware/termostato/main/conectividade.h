#pragma once
#include <stdbool.h>

void conect_init(void);
bool conect_online(void);
void conect_publicar_status(const char *json);
bool conect_consumir_setpoint(float *valor);
