#!/usr/bin/env python3

import argparse
import sys
import config
from uart_protocol import UARTClient


MENU = """
  Protocolo UART Simplificado - Parte 1   

[1] 0xA1 - Solicitar inteiro              
[2] 0xA2 - Solicitar float                
[3] 0xA3 - Solicitar string                
[4] 0xB1 - Enviar inteiro                  
[5] 0xB2 - Enviar float                    
[6] 0xB3 - Enviar string                   
[7] Executar todos os comandos (demo)      
[0] Sair                                  
"""


def _input_int(prompt: str) -> int:
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("  Valor inválido. Digite um inteiro.")


def _input_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt))
        except ValueError:
            print("  Valor inválido. Digite um número.")


def _exibir_resultado(resp) -> None:
    status = "✓" if resp.sucesso else "✗"
    print(f"  [{status}] {resp}")


def executar_todos(client: UARTClient) -> None:
    """Executa os 6 comandos em sequência com valores padrão."""
    print("\n─── Demo: executando todos os comandos ───")

    print("\n[0xA1] Solicitar inteiro:")
    _exibir_resultado(client.solicitar_int())

    print("\n[0xA2] Solicitar float:")
    _exibir_resultado(client.solicitar_float())

    print("\n[0xA3] Solicitar string:")
    _exibir_resultado(client.solicitar_string())

    print("\n[0xB1] Enviar inteiro (valor=42):")
    _exibir_resultado(client.enviar_int(42))

    print("\n[0xB2] Enviar float (valor=3.14):")
    _exibir_resultado(client.enviar_float(3.14))

    print("\n[0xB3] Enviar string ('FSE2026'):")
    _exibir_resultado(client.enviar_string("FSE2026"))

    print("\n─── Demo concluída ───")


def loop_interativo(client: UARTClient) -> None:
    while True:
        print(MENU)
        escolha = input("Escolha: ").strip()

        if escolha == "0":
            print("Encerrando.")
            break
        elif escolha == "1":
            print("[0xA1] Solicitando inteiro...")
            _exibir_resultado(client.solicitar_int())
        elif escolha == "2":
            print("[0xA2] Solicitando float...")
            _exibir_resultado(client.solicitar_float())
        elif escolha == "3":
            print("[0xA3] Solicitando string...")
            _exibir_resultado(client.solicitar_string())
        elif escolha == "4":
            valor = _input_int("  Digite o inteiro a enviar: ")
            _exibir_resultado(client.enviar_int(valor))
        elif escolha == "5":
            valor = _input_float("  Digite o float a enviar: ")
            _exibir_resultado(client.enviar_float(valor))
        elif escolha == "6":
            texto = input("  Digite a string a enviar: ")
            _exibir_resultado(client.enviar_string(texto))
        elif escolha == "7":
            executar_todos(client)
        else:
            print("  Opção inválida.")



def parse_args():
    parser = argparse.ArgumentParser(
        description="Cliente UART Simplificado — Parte 1 (FSE 2026/1)"
    )
    parser.add_argument("--port",
                        default=config.UART_PORT,
                        help="Porta serial (default: %(default)s)")
    parser.add_argument("--baud",
                        type=int, default=config.UART_BAUD,
                        help="Baudrate (default: %(default)s)")
    parser.add_argument("--timeout",
                        type=float, default=config.UART_TIMEOUT,
                        help="Timeout em segundos (default: %(default)s)")
    parser.add_argument("--matricula",
                        type=str,
                        help="6 últimos dígitos da matrícula (ex: 654321)")
    parser.add_argument("--auto",
                        action="store_true",
                        help="Executa todos os comandos automaticamente e sai")
    return parser.parse_args()


def aplicar_matricula(arg: str) -> None:
    """Sobrescreve MATRICULA_6_DIGITOS em config com os dígitos passados."""
    if len(arg) != 6 or not arg.isdigit():
        print(f"Erro: --matricula deve ter exatamente 6 dígitos numéricos (recebido: '{arg}').")
        sys.exit(1)
    config.MATRICULA_6_DIGITOS = [int(c) for c in arg]
    print(f"Matrícula configurada: {arg}  →  bytes {config.MATRICULA_6_DIGITOS}")


def main():
    args = parse_args()

    if args.matricula:
        aplicar_matricula(args.matricula)
    elif all(d == 0 for d in config.MATRICULA_6_DIGITOS):
        print("AVISO: matrícula não configurada. "
              "Edite MATRICULA_6_DIGITOS em config.py ou use --matricula XXXXXX")

    print(f"Porta: {args.port}  |  Baud: {args.baud}  |  "
          f"Matrícula (6 díg.): {''.join(str(d) for d in config.MATRICULA_6_DIGITOS)}")

    try:
        with UARTClient(port=args.port, baud=args.baud, timeout=args.timeout) as client:
            if args.auto:
                executar_todos(client)
            else:
                loop_interativo(client)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    except Exception as e:
        print(f"Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
