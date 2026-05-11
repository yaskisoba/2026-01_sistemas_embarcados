import time
import threading
import RPi.GPIO as GPIO
from gpio_module import GPIOController

SEMAFORO_1 = [17, 18, 23]
SEMAFORO_2 = [24, 8, 7]

BOTOES = {
    'M1_Principal': 1,
    'M1_Travessia': 12,
    'M2_Principal': 25,
    'M2_Travessia': 22,
}

gpio = GPIOController()
pedestre = {k: False for k in BOTOES}
pedestre_lock = threading.Lock()


def atualizar_semaforo(pinos, codigo):
    for i in range(3):
        gpio.set_output(pinos[i], (codigo >> i) & 1)


def make_callback(nome):
    def cb(canal):
        with pedestre_lock:
            pedestre[nome] = True
        print(f"[BOTÃO] {nome} pressionado (GPIO {canal})")
    return cb


def consumir_pedestre(*nomes):
    with pedestre_lock:
        ativado = any(pedestre[n] for n in nomes)
        for n in nomes:
            pedestre[n] = False
    return ativado


def aguardar(segundos, *flags, minimo=0):
    time.sleep(minimo)
    inicio = time.time()
    while time.time() - inicio < (segundos - minimo):
        if flags and consumir_pedestre(*flags):
            return True
        time.sleep(0.05)
    return False


def ciclo_modelo1():
    while True:
        # Verde: 10s, aceita pedestre após 5s mínimos
        atualizar_semaforo(SEMAFORO_1, 0b001)
        print("[M1] VERDE")
        antecipado = aguardar(10, 'M1_Principal', 'M1_Travessia', minimo=5)
        if antecipado:
            print("[M1] Pedestre antecipou fechamento do verde")

        atualizar_semaforo(SEMAFORO_1, 0b010)
        print("[M1] AMARELO")
        aguardar(2)

        atualizar_semaforo(SEMAFORO_1, 0b100)
        print("[M1] VERMELHO")
        aguardar(10)


def ciclo_modelo2():
    while True:
        # Estado 1: Verde Principal — mín 10s, máx 20s
        atualizar_semaforo(SEMAFORO_2, 1)
        print("[M2] Estado 1 — Verde Principal")
        antecipado = aguardar(20, 'M2_Principal', minimo=10)
        if antecipado:
            print("[M2] Pedestre principal antecipou")

        # Estado 2: Amarelo Principal
        atualizar_semaforo(SEMAFORO_2, 2)
        print("[M2] Estado 2 — Amarelo Principal")
        aguardar(2)

        # Estado 4: Vermelho Total
        atualizar_semaforo(SEMAFORO_2, 4)
        print("[M2] Estado 4 — Vermelho Total")
        aguardar(2)

        # Estado 5: Verde Cruzamento — mín 5s, máx 10s
        atualizar_semaforo(SEMAFORO_2, 5)
        print("[M2] Estado 5 — Verde Cruzamento")
        antecipado = aguardar(10, 'M2_Travessia', minimo=5)
        if antecipado:
            print("[M2] Pedestre cruzamento antecipou")

        # Estado 6: Amarelo Cruzamento
        atualizar_semaforo(SEMAFORO_2, 6)
        print("[M2] Estado 6 — Amarelo Cruzamento")
        aguardar(2)

        # Estado 4: Vermelho Total
        atualizar_semaforo(SEMAFORO_2, 4)
        print("[M2] Estado 4 — Vermelho Total")
        aguardar(2)


def setup():
    for pino in SEMAFORO_1 + SEMAFORO_2:
        gpio.setup_output(pino)
    for nome, pino in BOTOES.items():
        gpio.setup_input(pino)
        gpio.add_interrupt(pino, GPIO.RISING, make_callback(nome), bouncetime=400)


if __name__ == '__main__':
    try:
        print("Iniciando Sistema de Controle de Tráfego...")
        setup()
        t1 = threading.Thread(target=ciclo_modelo1, daemon=True)
        t2 = threading.Thread(target=ciclo_modelo2, daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        gpio.cleanup()