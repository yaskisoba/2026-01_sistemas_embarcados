/* Driver do DHT11 (umidade e temperatura) via protocolo de 1 fio. */
#pragma once

void dht11_init(void);
/* Retorna 0 em sucesso; negativo em erro. Umidade e temp em inteiro. */
int dht11_ler(int *umidade, int *temperatura);
