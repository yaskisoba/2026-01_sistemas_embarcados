import time
from gpio_module import GPIOController
import RPi.GPIO as GPIO

# Mapeamento de Pinos (Tabelas 1, 3 e 4)
SEMAFORO_1 = [17, 18, 23]
SEMAFORO_2 = [24, 8, 7]

BOTOES = {
    'C1_Principal': 1,
    'C1_Travessia': 12,
    'C2_Principal': 25,
    'C2_Travessia': 22
}

SENSORES = {
    'S1': {'A': 16, 'B': 20},
    'S2': {'A': 21, 'B': 27},
    'S3': {'A': 11, 'B': 0},
    'S4': {'A': 5, 'B': 6}
}

# Variáveis de Controle Global
gpio = GPIOController()
tempos_sensores = {s: 0 for s in SENSORES}
requisicao_pedestre = False

def atualizar_semaforo(pinos, codigo):
    """Converte código decimal 0-7 para 3 bits nos pinos GPIO."""
    for i in range(3):
        estado = (codigo >> i) & 1
        gpio.set_output(pinos[i], estado)

def callback_botao(canal):
    global requisicao_pedestre
    print(f"Botão {canal} pressionado! Solicitando travessia...")
    requisicao_pedestre = True

def callback_sensor_A(canal):
    for sensor, pinos in SENSORES.items():
        if pinos['A'] == canal:
            tempos_sensores[sensor] = time.time()

def callback_sensor_B(canal):
    tempo_fim = time.time()
    for sensor, pinos in SENSORES.items():
        if pinos['B'] == canal:
            tempo_ini = tempos_sensores[sensor]
            if tempo_ini > 0:
                dt = tempo_fim - tempo_ini
                # v = (d * 3.6) / dt | d = 2m
                velocidade = (2.0 * 3.6) / dt
                print(f"Velocidade {sensor}: {velocidade:.2f} km/h")
                if velocidade > 60:
                    print(">>> ALERTA: INFRAÇÃO DETECTADA (> 60 km/h)")
                tempos_sensores[sensor] = 0

def setup_sistema():
    # Configuração de Saídas (Semáforos)
    for pino in SEMAFORO_1 + SEMAFORO_2:
        gpio.setup_output(pino)

    # Configuração de Botões com Debounce
    for pino in BOTOES.values():
        gpio.setup_input(pino)
        gpio.add_interrupt(pino, GPIO.RISING, callback_botao, bouncetime=400)

    # Configuração de Sensores
    for pinos in SENSORES.values():
        gpio.setup_input(pinos['A'])
        gpio.setup_input(pinos['B'])
        gpio.add_interrupt(pinos['A'], GPIO.RISING, callback_sensor_A)
        gpio.add_interrupt(pinos['B'], GPIO.RISING, callback_sensor_B)

def ciclo_semaforo():
    global requisicao_pedestre
    while True:
        # ESTADO: VERDE PRINCIPAL (Código 1)
        atualizar_semaforo(SEMAFORO_1, 1)
        print("Sinal Verde (Principal) - Aguardando...")
        
        # Verde dura entre 15s (min) e 30s (max)
        for segundo in range(30):
            time.sleep(1)
            # Se apertarem o botão e já passou o tempo mínimo (15s), interrompe
            if requisicao_pedestre and segundo >= 15:
                print("Antecipando fechamento por pedestre!")
                break
        
        requisicao_pedestre = False # Reseta a flag

        # ESTADO: AMARELO (Código 2)
        atualizar_semaforo(SEMAFORO_1, 2)
        print("Sinal Amarelo - Atenção!")
        time.sleep(3) # Tempo fixo de amarelo

        # ESTADO: VERMELHO TOTAL (Código 4)
        atualizar_semaforo(SEMAFORO_1, 4)
        print("Sinal Vermelho - Pare!")
        time.sleep(2)

if __name__ == '__main__':
    try:
        print("Iniciando Sistema de Controle de Tráfego...")
        setup_sistema()
        ciclo_semaforo()
    except KeyboardInterrupt:
        print("\nEncerrando sistema...")
    finally:
        gpio.cleanup()