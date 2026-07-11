/* Encoder rotativo KY-040 (ajuste do setpoint). */
#pragma once
#include <stdbool.h>

void encoder_init(void);
int  encoder_consumir_passos(void); /* passos desde a ultima chamada (+/-) */
bool encoder_consumir_botao(void);  /* true se o botao foi pressionado */
