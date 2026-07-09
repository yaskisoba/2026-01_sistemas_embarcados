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

- [ ] Ambiente ESP-IDF configurado
- [ ] Teste inicial (blink)
- [ ] LED RGB
- [ ] Buzzer
- [ ] Display OLED (I²C)
- [ ] Sensor BME280 (I²C)
- [ ] Encoder rotativo
- [ ] Sensor de presença PIR
- [ ] Lógica de controle (histerese + Auto-Away)
- [ ] Conectividade Wi-Fi / MQTT

## Mapa de pinos

_A definir conforme a montagem avança._
