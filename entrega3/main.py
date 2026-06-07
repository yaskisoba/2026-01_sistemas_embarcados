import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

_SERVICES = (
    ([sys.executable, "main_central.py", "--config", "config/central.json"], 0.0),
    ([sys.executable, "main_distributed.py", "--config", "config/distributed_1.json"], 0.3),
    ([sys.executable, "main_distributed.py", "--config", "config/distributed_2.json"], 0.0),
)


def launch_all_services() -> None:
    children: list[subprocess.Popen] = []
    print("=== Entrega 3 — Controle de Trânsito ===")
    print("Iniciando central e cruzamentos...")

    for cmd, delay in _SERVICES:
        if delay:
            time.sleep(delay)
        children.append(subprocess.Popen(cmd, cwd=_ROOT))

    print(f"{len(children)} processos ativos (Ctrl+C encerra tudo)")

    try:
        while True:
            for proc in children:
                code = proc.poll()
                if code is not None:
                    print(f"Processo encerrou (código {code}); finalizando os demais")
                    return
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nEncerrando processos filhos...")
    finally:
        for proc in children:
            if proc.poll() is None:
                proc.terminate()
        for proc in children:
            if proc.poll() is None:
                proc.wait()


if __name__ == "__main__":
    launch_all_services()
