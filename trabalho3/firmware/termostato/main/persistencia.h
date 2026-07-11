/* Persistencia do setpoint na memoria nao-volatil (NVS).
 * Guarda a temperatura-alvo para que ela sobreviva ao desligamento. */
#pragma once

void  persistencia_init(void);
float persistencia_carregar_setpoint(float padrao); /* le o alvo salvo, ou o padrao */
void  persistencia_salvar_setpoint(float setpoint);
