# Trabalho 3 — Termostato Inteligente com ESP32

> **Fundamentos de Sistemas Embarcados (FGA-UnB) — 2026/1**
> Implementação prática do termostato inteligente proposto no [Trabalho 2](../trabalho2/termostato-nest/README.md), inspirado no Nest Learning Thermostat.

## Integrantes

| Nome completo | Matrícula |
| --- | --- |
| Gustavo Alves de Souza | 211063111 |
| Yasmim Oliveira Rosa | 200029088 |

## Visão geral

Termostato que lê temperatura e umidade do ambiente, permite ajustar a temperatura-alvo (*setpoint*) por um encoder rotativo, aciona uma carga indicadora conforme o estado (aquecendo / resfriando / eco) e detecta presença para entrar em modo de economia (*Auto-Away*), com monitoramento remoto por Wi-Fi/MQTT.

## Hardware utilizado

| Componente | Função | Interface |
| --- | --- | --- |
| **ESP32 DevKit (30 pinos)** | Microcontrolador principal, Wi-Fi nativo | — |
| **BME280** (GY-BME280) | Temperatura, umidade e pressão | I²C |
| **DHT11** | Temperatura e umidade (redundância / opcional) | GPIO |
| **PIR HC-SR501** | Detecção de presença (*Auto-Away*) | GPIO |
| **Encoder Rotativo + Botão** | Ajuste do setpoint e navegação de menu | GPIO |
| **Display OLED** | Exibição de leituras e menus | I²C |
| **LED RGB** | Indicação visual de estado | GPIO / PWM |
| **Buzzer** | Alertas sonoros | GPIO |
| **2 protoboards** | Montagem do circuito | — |

## Software

- **Framework:** ESP-IDF v5.4 (FreeRTOS)
- **Firmware:** [`firmware/`](firmware/)

## Estado do projeto

- [x] Ambiente ESP-IDF configurado
- [x] Teste inicial (blink)
- [x] LED RGB
- [x] Buzzer
- [x] Display OLED (I²C)
- [x] Sensor BMP280 (I²C) — temperatura e pressão
- [x] Sensor DHT11 — umidade
- [ ] Encoder rotativo
- [ ] Sensor de presença PIR
- [ ] Lógica de controle (histerese + Auto-Away)
- [ ] Conectividade Wi-Fi / MQTT

## Mapa de pinos

| Periférico | Pino(s) na ESP32 | Observações |
| --- | --- | --- |
| LED de bordo | `GPIO 2` | Já soldado na placa; usado no teste inicial |
| Barramento I²C | `SDA = GPIO 21` · `SCL = GPIO 22` | Compartilhado pelo display OLED e pelo BME280 |
| LED RGB | `R = GPIO 25` · `G = GPIO 26` · `B = GPIO 27` | Saídas com PWM (periférico LEDC) |
| Buzzer | `GPIO 33` | Saída digital simples |
| Encoder rotativo | `CLK = GPIO 18` · `DT = GPIO 19` · `SW = GPIO 23` | Exigem pull-up interno |
| Sensor PIR | `GPIO 34` | Pino somente de entrada |
| DHT11 | `GPIO 4` | Protocolo de 1 fio bidirecional |

> **Nota sobre o módulo LED RGB (WCMCU):** apesar do pino comum ser
> marcado `-`, este módulo é de **anodo comum** — o comum vai no `3V3`
> (não no `GND`) e cada cor acende no nível baixo. Como não há resistores
> embutidos nem no kit, a corrente é limitada por software ajustando a
> força dos pinos (`GPIO_DRIVE_CAP_1`). Para a montagem final, usar
> resistores de 220–330 Ω em série com cada cor e voltar a força ao padrão.

> **Nota sobre o OLED (SSD1306 0,96"):** endereço I²C `0x3C`. É um display
> *dual color* por hardware — as 2 primeiras páginas (16 px do topo) são
> amarelas e o restante azul, fixo, não controlável por software. A UI do
> termostato usa a faixa amarela para o título e a área azul para os dados.

> **Nota sobre o sensor (BMP280, não BME280):** o módulo adquirido, apesar
> de vendido como "BME280", identificou-se via I²C (registrador `0xD0`) com
> ID `0x58`, que corresponde ao **BMP280** — mede temperatura e pressão, mas
> **não umidade**. Endereço `0x76` (`SDO`→GND). A leitura de pressão (~880 hPa)
> é coerente com a altitude de Brasília (~1170 m), o que valida as fórmulas de
> compensação. A umidade passa a ser fornecida pelo **DHT11** (GPIO 4).

> **Nota sobre o DHT11 (pull-up):** o protocolo de 1 fio exige um resistor de
> *pull-up* (4,7–10 kΩ) entre `DATA` e `VCC`; o pull-up interno da ESP32 (~45 kΩ)
> é fraco demais para o sensor "cru". Usamos o **módulo de 3 pinos**
> (`VCC`/`DATA`/`GND`), que já traz esse resistor embutido na placa — por isso as
> leituras são estáveis sem componente externo. (O sensor de 4 pinos avulso
> precisaria do resistor externo, conforme orientação do professor.)

### Critérios de escolha

A distribuição acima respeita as restrições elétricas da ESP32:

- Os **GPIOs 6 a 11** estão ligados à memória flash e não podem ser usados.
- Os **GPIOs 34, 35, 36 e 39** são *somente entrada* e não possuem resistores de pull-up/pull-down internos. Por isso o PIR ocupa o GPIO 34 (ele já entrega um sinal push-pull de 3,3 V e dispensa pull-up), enquanto o encoder, que depende de pull-up interno, fica em pinos bidirecionais.
- Os **GPIOs 0, 2, 12 e 15** são *strapping pins*: seus níveis no momento do boot alteram o modo de inicialização do chip. Foram evitados, com exceção do GPIO 2, que já aciona o LED de bordo.
- O **ADC2** deixa de funcionar quando o rádio Wi-Fi está ativo. Nenhum sensor analógico foi alocado nele, o que mantém a etapa de conectividade MQTT viável.
