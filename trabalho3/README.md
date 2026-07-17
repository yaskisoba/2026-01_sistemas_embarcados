# Termostato Inteligente com ESP32

> **Trabalho Final — Fundamentos de Sistemas Embarcados (FGA-UnB), 2026/1**
> Implementação prática, com ESP32 e ESP-IDF, do termostato inteligente proposto no
> [Trabalho 2](../trabalho2/termostato-nest/README.md), inspirado no Nest Learning Thermostat.

## Integrantes

| Nome completo | Matrícula |
| --- | --- |
| Gustavo Alves de Souza | 211063111 |
| Yasmim Oliveira Rosa | 200029088 |

## Visão geral

Termostato que lê a temperatura e a umidade do ambiente, permite ajustar a
temperatura-alvo (*setpoint*) **localmente** (encoder rotativo) ou **remotamente**
(MQTT), decide automaticamente entre **aquecer, resfriar ou manter** por controle
de histerese, sinaliza o estado por **LED RGB** e **buzzer**, detecta **presença**
para entrar em modo de economia (*Auto-Away*) e exibe tudo em um **display OLED**.
O último alvo escolhido é preservado em memória não-volátil.

## Funcionalidades

- **Medição** de temperatura e pressão (BMP280) e de umidade (DHT11).
- **Controle por histerese** com três estados: *aquecendo*, *resfriando* e *conforto*.
- **Ajuste do setpoint** por três vias: encoder (±0,5 °C por clique), botão do
  encoder (retorna ao padrão de 22 °C) e comando remoto por MQTT.
- **Auto-Away**: sem presença detectada por 15 s, a faixa de conforto é alargada
  (modo econômico); retorna ao controle normal ao detectar movimento.
- **Sinalização**: LED RGB (vermelho = aquecendo, azul = resfriando, verde =
  conforto), LED de bordo (acende com presença) e buzzer (confirmações sonoras).
- **Display OLED** com temperatura, umidade, alvo, estado e indicador de conexão.
- **Monitoramento e controle remotos** por Wi-Fi/MQTT (telemetria + comandos).
- **Persistência** do setpoint em NVS, sobrevivendo a desligamentos.

## Controles

| Ação | Efeito |
| --- | --- |
| Girar o encoder | Ajusta o alvo em ±0,5 °C por clique |
| Apertar o botão do encoder | Retorna o alvo ao padrão (22 °C) |
| Publicar em `.../cmd` (MQTT) | Ajusta o alvo remotamente |
| Passar em frente ao PIR | Acende o LED de bordo; mantém o modo presente |
| Ausência por 15 s | Entra em modo econômico (bip + `ECO` na tela) |

## Arquitetura de software (FreeRTOS)

O framework é o **ESP-IDF v5.4** (sem Arduino). O firmware final,
[`firmware/termostato/`](firmware/termostato/), é organizado de forma **modular**
(cada periférico em um par `.c/.h`) e dividido em **tasks** independentes,
coordenadas por uma **fila** e por **mutexes**:

| Task | Responsabilidade | Prioridade |
| --- | --- | --- |
| `controle` | Histerese + Auto-Away; aciona LED/buzzer; salva o alvo na NVS | 7 |
| `entrada` | Lê o encoder e os comandos remotos; posta na fila | 6 |
| `sensores` | Lê BMP280 (temperatura/pressão) e DHT11 (umidade) | 5 |
| `display` | Desenha a tela OLED | 4 |
| `comunicacao` | Publica a telemetria por MQTT | 3 |

**Sincronização:**
- **Fila (`xQueueCreate`)** — `task_entrada` e o callback do MQTT convertem cada
  ajuste em um `comando_t` e o postam na fila; `task_controle` consome. Isso
  desacopla a origem do comando (encoder local ou nuvem) da lógica de controle.
- **Mutex do estado** — a struct `sistema_t` (temperatura, umidade, alvo, estado,
  presença) é lida e escrita por várias tasks; um `SemaphoreHandle_t` garante
  acesso exclusivo.
- **Mutex do I²C** — como `task_sensores` (BMP280) e `task_display` (OLED)
  compartilham o barramento, um segundo mutex serializa as transações.

As tasks da aplicação são fixadas no **core 1** (`xTaskCreatePinnedToCore`),
deixando o **core 0** para a pilha de rede (Wi-Fi/MQTT, que roda em suas próprias
tasks do ESP-IDF). Isso evita que a seção crítica da leitura do DHT11 (que
desabilita interrupções por alguns ms) perturbe o Wi-Fi.

### Lógica de controle (máquina de estados)

`task_controle` implementa uma máquina de três estados, decidida por **histerese**
em torno do alvo, com uma folga (*banda*) que evita o chaveamento excessivo quando
a temperatura fica próxima do alvo:

- `temp < alvo − banda` → **AQUECENDO** (LED vermelho)
- `temp > alvo + banda` → **RESFRIANDO** (LED azul)
- dentro da faixa → **CONFORTO** (LED verde)

A banda é de **±0,5 °C** no modo normal. No **Auto-Away** (sem presença por 15 s)
ela alarga para **±3 °C**, fazendo o sistema relaxar o controle e economizar.

> O encoder rotativo também é lido por uma **máquina de estados de quadratura**
> (algoritmo de Ben Buxton), acionada por **interrupção** e com *debounce*, o que
> garante exatamente um passo por clique, sem repique do contato.

## Conectividade (MQTT)

O termostato publica o status e aceita comandos por MQTT usando o broker público
`broker.hivemq.com`. A conexão é **assíncrona**: se a rede cair, o controle local
continua funcionando — apenas a publicação é suspensa até reconectar.

- **Publica** (a cada ~3 s) no tópico `fse2026/gustavo/termostato/status`, em JSON:
  `{"temp":26.9,"umid":36,"alvo":22.0,"estado":"RESFRIANDO","presente":true}`
- **Assina** o tópico `fse2026/gustavo/termostato/cmd`; o payload é o novo alvo em
  °C (ex.: `24.5`), aplicado imediatamente ao setpoint.

Para monitorar/controlar, pode-se usar qualquer cliente MQTT (ex.: o cliente web
`http://www.hivemq.com/demos/websocket-client/`, host `broker.hivemq.com`):
assine `.../status` para ver a telemetria e publique em `.../cmd` para mudar o alvo.

As credenciais de Wi-Fi ficam em `secrets.h` (fora do versionamento; há um
`secrets.h.example` como modelo). A ESP32 só conecta em redes **2,4 GHz**. Ao
obter IP, o firmware fixa o DNS público `8.8.8.8`, o que torna a resolução do
endereço do broker confiável mesmo em roteadores/hotspots que não encaminham DNS.

## Persistência do setpoint (NVS)

O último alvo escolhido (pelo encoder, pelo botão ou pela nuvem) é salvo na
memória não-volátil (**NVS**) e restaurado no boot, sobrevivendo a desligamentos —
uma versão elementar do "aprendizado" proposto no Trabalho 2. Para evitar desgaste
da flash, a gravação é adiada ~2 s após a última mudança, de modo que uma girada
inteira do encoder resulte em uma única escrita.

## Hardware utilizado

| Componente | Função | Interface |
| --- | --- | --- |
| **ESP32 DevKit (30 pinos)** | Microcontrolador principal, Wi-Fi nativo | — |
| **BMP280** (GY-BMP280) | Temperatura e pressão | I²C |
| **DHT11** (módulo 3 pinos) | Umidade | GPIO (1 fio) |
| **PIR HC-SR501** | Detecção de presença (*Auto-Away*) | GPIO |
| **Encoder rotativo KY-040 + botão** | Ajuste do setpoint | GPIO |
| **Display OLED SSD1306 0,96"** | Exibição das leituras e do estado | I²C |
| **LED RGB (módulo WCMCU)** | Indicação visual de estado | GPIO / PWM |
| **Buzzer ativo** | Confirmações sonoras | GPIO |
| **2 protoboards** | Montagem do circuito | — |

## Mapa de pinos

| Periférico | Pino(s) na ESP32 | Observações |
| --- | --- | --- |
| LED de bordo | `GPIO 2` | Acende com presença detectada pelo PIR |
| Barramento I²C | `SDA = GPIO 21` · `SCL = GPIO 22` | Compartilhado pelo OLED e pelo BMP280 |
| LED RGB | `R = GPIO 25` · `G = GPIO 26` · `B = GPIO 27` | Saídas com PWM (periférico LEDC) |
| Buzzer | `GPIO 33` | Saída digital simples |
| Encoder rotativo | `CLK = GPIO 18` · `DT = GPIO 19` · `SW = GPIO 23` | Usam pull-up interno |
| Sensor PIR | `OUT = GPIO 13` · `VCC = VIN (5V)` | Pull-down interno; alimentado em 5 V |
| DHT11 | `DATA = GPIO 4` | Protocolo de 1 fio bidirecional |

### Notas de projeto

- **LED RGB (módulo WCMCU):** apesar de o pino comum ser marcado `-`, o módulo é
  de **anodo comum** — o comum vai no `3V3` e cada cor acende em nível baixo
  (`CATODO_COMUM 0` no firmware). Como o módulo não possui resistores embutidos e
  não foram usados resistores externos, a corrente é limitada **por software**,
  reduzindo a força de saída dos pinos para `GPIO_DRIVE_CAP_1` (~10 mA), o
  suficiente para acionar o LED com segurança.
- **Sensor BMP280 (não BME280):** o módulo, apesar de vendido como "BME280",
  identificou-se via I²C (registrador `0xD0`) com ID `0x58`, correspondente ao
  **BMP280** — mede temperatura e pressão, mas não umidade. Endereço `0x76`
  (`SDO`→GND). A umidade é fornecida pelo **DHT11**.
- **DHT11:** o protocolo de 1 fio exige um resistor de *pull-up* (4,7–10 kΩ) entre
  `DATA` e `VCC`. Usamos o **módulo de 3 pinos**, que já traz esse resistor na
  placa, dispensando componente externo.
- **PIR HC-SR501:** alimentado em **5 V** (pino `VIN`), pois não opera de forma
  confiável em 3,3 V; a saída, porém, é de 3,3 V, segura para o GPIO. Fica no
  **GPIO 13** com pull-down interno — assim, sem sinal, a leitura vai a "sem
  presença" em vez de flutuar em nível alto.

### Restrições de GPIO consideradas

- Os **GPIOs 6–11** são reservados à memória flash e não podem ser usados.
- Os **GPIOs 34–39** são somente de entrada e não têm pull-up/pull-down internos.
- Os **GPIOs 0, 2, 12 e 15** são *strapping pins* (influenciam o boot); foram
  evitados, exceto o GPIO 2 (LED de bordo).
- O **ADC2** deixa de funcionar com o Wi-Fi ativo; nenhum sensor analógico foi
  alocado nele.

## Como compilar e gravar

**Pré-requisito:** [ESP-IDF v5.4](https://docs.espressif.com/projects/esp-idf/en/v5.4/esp32/get-started/)
instalado.

```bash
# 1. Configurar as credenciais de Wi-Fi (rede 2,4 GHz)
cp firmware/termostato/main/secrets.h.example firmware/termostato/main/secrets.h
#    editar secrets.h e preencher WIFI_SSID e WIFI_PASS

# 2. Ativar o ambiente ESP-IDF (a cada novo terminal)
. $HOME/esp/esp-idf/export.sh

# 3. Compilar, gravar e abrir o monitor serial (com a placa conectada por USB)
cd firmware/termostato
idf.py -p PORTA flash monitor
```

Substitua `PORTA` pela porta serial da placa: `/dev/ttyUSB0` (Linux),
`/dev/cu.usbserial-XXXX` (macOS) ou `COMx` (Windows). Para sair do monitor,
pressione `Ctrl + ]`.

## Estrutura do repositório

Cada periférico foi validado em um **projeto isolado** antes da integração; o
firmware final reúne todos os módulos:

```
firmware/
├── blink/        # teste inicial do ambiente
├── led_rgb/      # LED RGB (PWM)
├── buzzer/       # buzzer ativo
├── oled/         # display SSD1306
├── bme280/       # sensor BMP280 (I²C)
├── dht11/        # sensor de umidade
├── encoder/      # encoder rotativo
├── pir/          # sensor de presença
├── conectividade/# teste de Wi-Fi + MQTT
├── painel/       # integração dos sensores no OLED
└── termostato/   # FIRMWARE FINAL (integra tudo, com FreeRTOS)
```
