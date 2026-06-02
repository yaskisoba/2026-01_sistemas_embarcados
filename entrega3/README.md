# Entrega 3 — Trabalho 1 (FSE 2026/1)

Implementação em Python de um sistema distribuído para controle de cruzamentos com:

- **Servidor Central** (TCP + MODBUS RS485)
- **2 Servidores Distribuídos** (GPIO + TCP)
- Controle de semáforos, botões de pedestre, sensores de velocidade e câmeras LPR

## Arquitetura do código

```text
entrega3/
  central/
    server.py                 # Servidor Central
  distributed/
    server.py                 # Nó distribuído de um cruzamento
  common/
    gpio_hal.py               # Adaptador GPIO (RPi.GPIO com fallback mock)
    messages.py               # Protocolo JSON por linha (TCP)
    modbus_rtu.py             # Cliente MODBUS RTU (0x03 e 0x10)
    lpr_camera.py             # Fluxo de captura das câmeras LPR
    persistence.py            # Persistência JSON atômica
    traffic_math.py           # Cálculo de velocidade
  config/
    central.json
    distributed_1.json
    distributed_2.json
  main_central.py
  main_distributed.py
  requirements.txt
```

## Requisitos

- Python 3.10+
- Raspberry Pi OS (para GPIO real)
- RS485 em `/dev/serial0` (ou ajuste no JSON)

## Instalação

```bash
cd entrega3
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuração

### 1) Matrícula (obrigatória para MODBUS)

Edite [config/central.json](config/central.json) no campo `matricula_6`.

Exemplo:

```json
"matricula_6": "654321"
```

A implementação envia os 6 dígitos **antes do CRC** em bytes crus e em ordem reversa, como solicitado.

### 2) Endereços e portas

- Central TCP: [config/central.json](config/central.json)
- Distribuídos: [config/distributed_1.json](config/distributed_1.json) e [config/distributed_2.json](config/distributed_2.json)

Se os processos estiverem em máquinas diferentes, ajuste `central_host` nos distribuídos.

### 3) Modo mock de GPIO (para teste fora da Raspberry)

Nos arquivos de distribuído, use:

```json
"force_mock_gpio": true
```

## Execução

> Inicie em terminais separados (a ordem não importa; há reconexão automática).

### Terminal 1 — Servidor Central

```bash
cd entrega3
python3 main_central.py --config config/central.json --log-level INFO
```

### Terminal 2 — Distribuído Cruzamento 1

```bash
cd entrega3
python3 main_distributed.py --config config/distributed_1.json --log-level INFO
```

### Terminal 3 — Distribuído Cruzamento 2

```bash
cd entrega3
python3 main_distributed.py --config config/distributed_2.json --log-level INFO
```

## Interface do Servidor Central (terminal)

Comandos:

- `status`
- `night on` / `night off`
- `manual <1|2> <0..7>`
- `auto <1|2|all>`
- `quit`

## Requisitos atendidos no código

1. **Servidores Distribuídos**
   - Temporização dos semáforos (normal, noturno e emergência)
   - Botões de pedestre com debounce
   - Sensores de velocidade por borda de subida A/B
   - Alerta imediato de excesso de velocidade (> 60 km/h)
   - Telemetria periódica (2 s) para o central

2. **Servidor Central**
   - Conexão TCP com 2 distribuídos
   - Polling MODBUS do estado (0x20)
   - Comandos de noite/emergência para os cruzamentos afetados
   - Acionamento de câmera LPR por sensor (0x11..0x14)
   - Log persistente de multas em [data/multas.log](data/multas.log)
   - Persistência de estado em [data/state.json](data/state.json)

3. **Comunicação e robustez**
   - Inicialização independente dos serviços
   - Reconexão automática TCP
   - Tentativas e recuperação no MODBUS RTU

## Formato de log de multas

Cada linha em [data/multas.log](data/multas.log):

```text
timestamp | cruzamento | sensor | velocidade (km/h) | câmera MODBUS | placa | confiança (%) | valor
```

Exemplo:

```text
2026-06-01 10:30:00 | C1 | S2 | 78.34 km/h | 0x12 | ABC1D23 | 93% | R$ 195.23
```

## Observações

- O cálculo de velocidade usa $v = \frac{2}{\Delta t} \times 3{,}6$.
- Para modo noturno, o distribuído alterna códigos `0` e `4` a cada 1 s.
- Em emergência (`active=1` em 0x20), o central aplica `signal_group` no(s) cruzamento(s) afetado(s) até `active=0`.
