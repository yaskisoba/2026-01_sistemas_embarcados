/* Sensor de presenca PIR (HC-SR501). */
#pragma once
#include <stdbool.h>

void pir_init(void);
bool pir_movimento(void); /* true enquanto ha movimento detectado */
