#!/usr/bin/env python3
import argparse
import sys
import os

_PARTE2 = os.path.dirname(os.path.abspath(__file__))
_PARTE1 = os.path.join(_PARTE2, "..", "parte1")

if _PARTE2 not in sys.path:
    sys.path.insert(0, _PARTE2)
if _PARTE1 not in sys.path:
    sys.path.append(_PARTE1)

import config                              
from modbus_protocol import ModbusClient, RespostaMODBUS
import uart_protocol as _p1_proto          
from uart_protocol import UARTClient


MENU_PROTOCOLO = """
FSE 2026/1 - Entrega 2                
Escolha o protocolo:                    
[1] Simplificado (Parte 1 - sem CRC)   
[2] MODBUS (Parte 2 - com CRC)   
[0] Sair                                
"""

MENU_P1 = """
Parte 1 - Protocolo Simplificado 
[1] 0xA1 Solicitar inteiro               
[2] 0xA2 Solicitar float                 
[3] 0xA3 Solicitar string                
[4] 0xB1 Enviar inteiro                  
[5] 0xB2 Enviar float                    
[6] 0xB3 Enviar string                   
[7] Demo - todos os comandos             
[0] Voltar                               
"""

MENU_P2 = """
Parte 2 - MODBUS (matrícula 6 dígitos) 
[1] 0x23/0xA1 Solicitar inteiro          
[2] 0x23/0xA2 Solicitar float            
[3] 0x23/0xA3 Solicitar string           
[4] 0x16/0xB1 Enviar inteiro             
[5] 0x16/0xB2 Enviar float               
[6] 0x16/0xB3 Enviar string              
[7] Demo - todos os comandos             
[0] Voltar                               """

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


def _exibir(resp) -> None:
    status = "✓" if resp.sucesso else "✗"
    print(f"  [{status}] {resp}")


def _demo_p1(client: UARTClient) -> None:
    print("\n─── Demo Parte 1 ───")
    for label, fn, args in [
        ("[0xA1] int",        client.solicitar_int,    ()),
        ("[0xA2] float",      client.solicitar_float,  ()),
        ("[0xA3] string",     client.solicitar_string, ()),
        ("[0xB1] enviar 42",  client.enviar_int,       (42,)),
        ("[0xB2] enviar 3.14",client.enviar_float,     (3.14,)),
        ("[0xB3] enviar str", client.enviar_string,    ("FSE2026",)),
    ]:
        print(f"\n{label}:")
        _exibir(fn(*args))
    print("\nDemo concluída")


def submenu_p1(client: UARTClient) -> None:
    while True:
        print(MENU_P1)
        op = input("Escolha: ").strip()
        if op == "0":
            break
        elif op == "1":
            print("[0xA1] Solicitando inteiro...")
            _exibir(client.solicitar_int())
        elif op == "2":
            print("[0xA2] Solicitando float...")
            _exibir(client.solicitar_float())
        elif op == "3":
            print("[0xA3] Solicitando string...")
            _exibir(client.solicitar_string())
        elif op == "4":
            v = _input_int("  Inteiro a enviar: ")
            _exibir(client.enviar_int(v))
        elif op == "5":
            v = _input_float("  Float a enviar: ")
            _exibir(client.enviar_float(v))
        elif op == "6":
            t = input("  String a enviar: ")
            _exibir(client.enviar_string(t))
        elif op == "7":
            _demo_p1(client)
        else:
            print("  Opção inválida.")



def _demo_p2(client: ModbusClient) -> None:
    print("\nDemo Parte 2 (MODBUS)")
    for label, fn, args in [
        ("[0x23/0xA1] int", client.solicitar_int,    ()),
        ("[0x23/0xA2] float", client.solicitar_float,  ()),
        ("[0x23/0xA3] string", client.solicitar_string, ()),
        ("[0x16/0xB1] enviar 42", client.enviar_int, (42,)),
        ("[0x16/0xB2] enviar 3.14", client.enviar_float, (3.14,)),
        ("[0x16/0xB3] enviar str", client.enviar_string, ("FSE2026",)),
    ]:
        print(f"\n{label}:")
        _exibir(fn(*args))
    print("\nDemo concluída")


def submenu_p2(client: ModbusClient) -> None:
    while True:
        print(MENU_P2)
        op = input("Escolha: ").strip()
        if op == "0":
            break
        elif op == "1":
            print("[0x23/0xA1] Solicitando inteiro...")
            _exibir(client.solicitar_int())
        elif op == "2":
            print("[0x23/0xA2] Solicitando float...")
            _exibir(client.solicitar_float())
        elif op == "3":
            print("[0x23/0xA3] Solicitando string...")
            _exibir(client.solicitar_string())
        elif op == "4":
            v = _input_int("  Inteiro a enviar: ")
            _exibir(client.enviar_int(v))
        elif op == "5":
            v = _input_float("  Float a enviar: ")
            _exibir(client.enviar_float(v))
        elif op == "6":
            t = input("  String a enviar: ")
            _exibir(client.enviar_string(t))
        elif op == "7":
            _demo_p2(client)
        else:
            print("  Opção inválida.")


def loop_principal(port: str, baud: int, timeout: float) -> None:
   
    while True:
        print(MENU_PROTOCOLO)
        op = input("Escolha: ").strip()

        if op == "0":
            print("Encerrando.")
            break
        elif op == "1":
            with UARTClient(port=port, baud=baud, timeout=timeout) as p1_client:
                submenu_p1(p1_client)
        elif op == "2":
            with ModbusClient(port=port, baud=baud, timeout=timeout) as p2_client:
                submenu_p2(p2_client)
        else:
            print("  Opção inválida.")


def loop_auto(port: str, baud: int, timeout: float) -> None:
    print("\n═══ Modo automático: Parte 1 + Parte 2 ═══\n")
    with UARTClient(port=port, baud=baud, timeout=timeout) as p1, \
         ModbusClient(port=port, baud=baud, timeout=timeout) as p2:
        _demo_p1(p1)
        _demo_p2(p2)



def parse_args():
    p = argparse.ArgumentParser(
        description="FSE 2026/1 — Entrega 2 (Parte 1 + Parte 2 MODBUS)"
    )
    p.add_argument("--port",      default=config.UART_PORT,
                   help="Porta serial (default: %(default)s)")
    p.add_argument("--baud",      type=int, default=config.UART_BAUD,
                   help="Baudrate (default: %(default)s)")
    p.add_argument("--timeout",   type=float, default=config.UART_TIMEOUT,
                   help="Timeout em segundos (default: %(default)s)")
    p.add_argument("--matricula", type=str,
                   help="6 últimos dígitos da matrícula (ex: 654321)")
    p.add_argument("--auto",      action="store_true",
                   help="Executa os 12 comandos automaticamente e sai")
    return p.parse_args()


def _aplicar_matricula(arg: str) -> None:
    if len(arg) != 6 or not arg.isdigit():
        print(f"Erro: --matricula deve ter 6 dígitos numéricos (recebido: '{arg}').")
        sys.exit(1)
    digitos = [int(c) for c in arg]
    config.MATRICULA_6_DIGITOS[:] = digitos
    import importlib
    p1_cfg_name = None
    for mod_name, mod in sys.modules.items():
        if mod_name.endswith("config") and hasattr(mod, "CMD_GET_INT") \
                and mod is not config:
            p1_cfg_name = mod_name
            break
    if p1_cfg_name:
        sys.modules[p1_cfg_name].MATRICULA_6_DIGITOS[:] = digitos
    print(f"Matrícula configurada: {arg}  →  bytes {digitos}")


def main() -> None:
    args = parse_args()

    if args.matricula:
        _aplicar_matricula(args.matricula)
    elif all(d == 0 for d in config.MATRICULA_6_DIGITOS):
        print("AVISO: matrícula não configurada. "
              "Edite MATRICULA_6_DIGITOS em config.py ou use --matricula XXXXXX")

    mat_str = "".join(str(d) for d in config.MATRICULA_6_DIGITOS)
    print(f"Porta: {args.port}  |  Baud: {args.baud}  |  Matrícula: {mat_str}")

    try:
        if args.auto:
            loop_auto(args.port, args.baud, args.timeout)
        else:
            loop_principal(args.port, args.baud, args.timeout)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    except Exception as e:
        print(f"Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
