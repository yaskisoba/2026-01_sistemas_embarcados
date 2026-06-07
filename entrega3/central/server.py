from __future__ import annotations

import argparse
import json
import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from common.lpr_camera import LPRCameraService
from common.messages import LineBuffer, decode_message, encode_message
from common.modbus_rtu import ModbusRTUClient
from common.persistence import atomic_save_json, load_json


log = logging.getLogger(__name__)

# §5.2 / critérios de avaliação: registradores de emergência 0–9 + night_mode (10)
EMERGENCY_REG_COUNT = 10
NIGHT_MODE_REG = 10
SYSTEM_STATE_REG_COUNT = 11


@dataclass
class SensorRuntime:
    sensor_id: int
    count_total: int = 0
    flow_cars_min: float = 0.0
    avg_speed_interval_kmh: float = 0.0


@dataclass
class IntersectionRuntime:
    intersection_id: int
    mode: str = "unknown"
    connected: bool = False
    last_update_ts: str = ""
    sensors: Dict[int, SensorRuntime] = field(default_factory=dict)
    infractions: int = 0


@dataclass
class DistConn:
    sock: socket.socket
    addr: tuple
    intersection_id: int
    name: str
    lock: threading.Lock = field(default_factory=threading.Lock)


class CentralServer:
    def __init__(self, cfg: Dict) -> None:
        self.cfg = cfg
        self.listen_host = cfg["tcp_host"]
        self.listen_port = int(cfg["tcp_port"])
        self.telemetry_interval_s = float(cfg.get("telemetry_interval_s", 2.0))

        self._running = threading.Event()
        self._running.set()
        self._connections: Dict[int, DistConn] = {}
        self._connections_lock = threading.Lock()

        self._state_lock = threading.Lock()
        self._state: Dict[int, IntersectionRuntime] = {
            1: IntersectionRuntime(intersection_id=1),
            2: IntersectionRuntime(intersection_id=2),
        }

        data_dir = Path(cfg.get("data_dir", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = str(data_dir / "state.json")
        self._fines_log = str(data_dir / "multas.log")

        persisted = load_json(self._state_file, default={})
        self._load_persisted_state(persisted)

        self._modbus = ModbusRTUClient(
            port=cfg["rs485_port"],
            baudrate=int(cfg.get("rs485_baud", 115200)),
            timeout_s=float(cfg.get("rs485_timeout_s", 0.3)),
            retries=int(cfg.get("rs485_retries", 3)),
            matricula_6=str(cfg["matricula_6"]),
        )
        log.info(
            "MODBUS 0x20: %d registradores | matrícula=%s | porta=%s",
            EMERGENCY_REG_COUNT,
            cfg["matricula_6"],
            cfg["rs485_port"],
        )
        self._lpr = LPRCameraService(self._modbus)

        self._camera_by_sensor = {int(k): int(v, 16) if isinstance(v, str) else int(v) for k, v in cfg["camera_by_sensor"].items()}

        self._night_mode = bool(persisted.get("night_mode", False))

        self._overspeed_queue: "queue.Queue[dict]" = queue.Queue()

        self._system_state_addr = 0x20
        self._system_state_reg_count = EMERGENCY_REG_COUNT
        self._system_state_start = 0
        self._use_unit_read_fallback = False
        self._estado_sistema: Optional[Dict] = None
        self._last_night_mode_read: Optional[int] = None
        self._last_emergency_route: Optional[tuple[tuple[int, ...], int]] = None
        self._last_modbus_state_error: Optional[str] = None
        self._modbus_last_error_at = 0.0

    def _load_persisted_state(self, persisted: Dict) -> None:
        items = persisted.get("intersections", {})
        for k, raw in items.items():
            iid = int(k)
            if iid not in self._state:
                continue
            obj = self._state[iid]
            obj.mode = raw.get("mode", obj.mode)
            obj.infractions = int(raw.get("infractions", 0))
            for sid_str, sraw in raw.get("sensors", {}).items():
                sid = int(sid_str)
                obj.sensors[sid] = SensorRuntime(
                    sensor_id=sid,
                    count_total=int(sraw.get("count_total", 0)),
                    flow_cars_min=float(sraw.get("flow_cars_min", 0.0)),
                    avg_speed_interval_kmh=float(sraw.get("avg_speed_interval_kmh", 0.0)),
                )

    def run(self) -> None:
        self._probe_modbus_at_startup()
        workers = [
            threading.Thread(target=self._tcp_server_loop, daemon=True),
            threading.Thread(target=self._modbus_state_loop, daemon=True),
            threading.Thread(target=self._overspeed_worker_loop, daemon=True),
            threading.Thread(target=self._persist_loop, daemon=True),
            threading.Thread(target=self._cli_loop, daemon=True),
        ]
        for t in workers:
            t.start()

        while self._running.is_set():
            time.sleep(0.5)

    def _tcp_server_loop(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.listen_host, self.listen_port))
        server.listen(8)
        server.settimeout(1.0)

        log.info("Servidor Central escutando em %s:%d", self.listen_host, self.listen_port)

        while self._running.is_set():
            try:
                sock, addr = server.accept()
            except socket.timeout:
                continue
            except Exception:
                log.exception("Erro no accept")
                continue

            th = threading.Thread(target=self._handle_dist_socket, args=(sock, addr), daemon=True)
            th.start()

    def _handle_dist_socket(self, sock: socket.socket, addr: tuple) -> None:
        sock.settimeout(0.5)
        buf = LineBuffer()
        conn: Optional[DistConn] = None

        try:
            while self._running.is_set():
                chunk = self._recv_chunk(sock)
                if chunk is None:
                    continue
                if not chunk:
                    break
                conn = self._consume_dist_chunk(sock, addr, buf, chunk, conn)

        except Exception as exc:
            log.warning("Conexão distribuída encerrada (%s): %s", addr, exc)
        finally:
            self._cleanup_connection(conn, sock)
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _recv_chunk(sock: socket.socket) -> bytes | None:
        try:
            return sock.recv(4096)
        except socket.timeout:
            return None

    def _consume_dist_chunk(
        self,
        sock: socket.socket,
        addr: tuple,
        buf: LineBuffer,
        chunk: bytes,
        conn: Optional[DistConn],
    ) -> Optional[DistConn]:
        buf.feed(chunk)
        while True:
            line = buf.pop_line()
            if line is None:
                return conn
            msg = decode_message(line)
            conn = self._process_dist_message(sock, addr, msg, conn)

    def _process_dist_message(
        self,
        sock: socket.socket,
        addr: tuple,
        msg: Dict,
        conn: Optional[DistConn],
    ) -> Optional[DistConn]:
        msg_type = msg.get("type")
        if msg_type == "hello":
            return self._register_connection(sock, addr, msg)
        if msg_type == "telemetry":
            self._on_telemetry(msg)
            return conn
        if msg_type == "overspeed":
            self._overspeed_queue.put(msg)
            return conn
        return conn

    def _register_connection(self, sock: socket.socket, addr: tuple, msg: Dict) -> DistConn:
        iid = int(msg["intersection_id"])
        name = str(msg.get("name", f"cross-{iid}"))
        conn = DistConn(sock=sock, addr=addr, intersection_id=iid, name=name)
        with self._connections_lock:
            self._connections[iid] = conn
        with self._state_lock:
            self._state[iid].connected = True
        log.info("Conexão registrada: C%d (%s)", iid, addr)
        self._send_command({"action": "set_night_mode", "enabled": self._night_mode}, target=iid)
        return conn

    def _cleanup_connection(self, conn: Optional[DistConn], sock: socket.socket) -> None:
        if conn is None:
            return
        with self._connections_lock:
            old = self._connections.get(conn.intersection_id)
            if old and old.sock is sock:
                del self._connections[conn.intersection_id]
        with self._state_lock:
            self._state[conn.intersection_id].connected = False

    def _on_telemetry(self, msg: Dict) -> None:
        iid = int(msg["intersection_id"])
        interval_total = 0
        with self._state_lock:
            cross = self._state[iid]
            cross.mode = msg.get("mode", cross.mode)
            cross.last_update_ts = msg.get("timestamp", "")
            for s in msg.get("sensors", []):
                sid = int(s["sensor_id"])
                st = cross.sensors.get(sid)
                if st is None:
                    st = SensorRuntime(sensor_id=sid)
                    cross.sensors[sid] = st

                st.count_total = int(s.get("count_total", st.count_total))
                count_interval = int(s.get("count_interval", 0))
                interval_total += count_interval
                st.flow_cars_min = count_interval * (60.0 / self.telemetry_interval_s)
                st.avg_speed_interval_kmh = float(s.get("avg_speed_interval_kmh", 0.0))

        if interval_total > 0:
            parts = []
            for s in msg.get("sensors", []):
                count_interval = int(s.get("count_interval", 0))
                if count_interval > 0:
                    avg = float(s.get("avg_speed_interval_kmh", 0.0))
                    parts.append(f"S{s['sensor_id']}:{count_interval}@{avg:.0f}km/h")
            log.info("Telemetria C%d: %s", iid, ", ".join(parts))

    def _send_command(self, command: Dict, target: int | str = "all") -> None:
        payload = {"type": "command", "target": target}
        payload.update(command)
        raw = encode_message(payload)

        with self._connections_lock:
            if target == "all":
                targets = list(self._connections.values())
            else:
                c = self._connections.get(int(target))
                targets = [c] if c else []

        for conn in targets:
            if conn is None:
                continue
            try:
                with conn.lock:
                    conn.sock.sendall(raw)
            except Exception as exc:
                log.warning("Falha ao enviar comando para C%d: %s", conn.intersection_id, exc)

    def _probe_modbus_at_startup(self) -> None:
        try:
            regs = self._fetch_device_state_block()
            estado = self._parse_device_state(regs)
            self._estado_sistema = dict(estado)
            log.info(
                "MODBUS 0x20 OK na inicialização: active=%s intersection=%s "
                "signal_group=%s night=%s",
                estado["active"],
                estado["intersection_id"],
                estado["signal_group"],
                estado["night_mode"],
            )
            self._sync_traffic_controller_state(estado)
        except Exception as exc:
            log.warning("MODBUS 0x20 indisponível na inicialização: %s", exc)

    def _fetch_device_state_block(self) -> List[int]:
        if self._use_unit_read_fallback:
            return self._fetch_device_state_unit_reads()

        counts = [self._system_state_reg_count]
        for candidate in (EMERGENCY_REG_COUNT, SYSTEM_STATE_REG_COUNT):
            if candidate not in counts:
                counts.append(candidate)

        last_error: Exception | None = None
        for count in counts:
            try:
                regs = self._modbus.read_holding_registers(
                    self._system_state_addr,
                    self._system_state_start,
                    count,
                )
                self._system_state_reg_count = len(regs)
                while len(regs) < SYSTEM_STATE_REG_COUNT:
                    regs.append(0)
                return regs
            except Exception as exc:
                last_error = exc
                if "0x02" not in str(exc) and "Illegal Data Address" not in str(exc):
                    break

        try:
            regs = self._fetch_device_state_unit_reads()
            self._use_unit_read_fallback = True
            log.info("Dispositivo 0x20: fallback para leitura unitária")
            return regs
        except Exception:
            pass

        try:
            regs = self._fetch_device_state_offset_one()
            self._system_state_start = 1
            self._use_unit_read_fallback = True
            log.info("MODBUS 0x20: registradores passaram a ser lidos a partir do offset 1")
            while len(regs) < SYSTEM_STATE_REG_COUNT:
                regs.append(0)
            return regs
        except Exception:
            if last_error is not None:
                raise last_error
            raise

    def _fetch_device_state_unit_reads(self) -> List[int]:
        regs: List[int] = []
        for offset in range(EMERGENCY_REG_COUNT):
            regs.append(
                self._modbus.read_holding_registers(
                    self._system_state_addr,
                    self._system_state_start + offset,
                    1,
                )[0]
            )
        try:
            regs.append(
                self._modbus.read_holding_registers(
                    self._system_state_addr,
                    self._system_state_start + NIGHT_MODE_REG,
                    1,
                )[0]
            )
        except Exception:
            regs.append(0)
        return regs

    def _fetch_device_state_offset_one(self) -> List[int]:
        try:
            return self._modbus.read_holding_registers(
                self._system_state_addr,
                1,
                self._system_state_reg_count,
            )
        except Exception as block_error:
            if "0x02" not in str(block_error) and "Illegal Data Address" not in str(block_error):
                raise

        regs: List[int] = []
        for offset in range(EMERGENCY_REG_COUNT):
            regs.append(
                self._modbus.read_holding_registers(
                    self._system_state_addr,
                    1 + offset,
                    1,
                )[0]
            )
        return regs

    @staticmethod
    def _parse_device_state(registers: List[int]) -> Dict:
        if len(registers) < EMERGENCY_REG_COUNT:
            raise RuntimeError(
                f"Resposta 0x20 incompleta: esperado {EMERGENCY_REG_COUNT}, recebido {len(registers)}"
            )
        return {
            "active": registers[0],
            "road": registers[1],
            "direction": registers[2],
            "intersection_id": registers[3],
            "vehicle_type": registers[4],
            "signal_group": registers[5],
            "timed_out": registers[6],
            "unattended_count": registers[7],
            "elapsed_s_x10": registers[8],
            "max_time_s_x10": registers[9],
            "night_mode": registers[NIGHT_MODE_REG] if len(registers) > NIGHT_MODE_REG else 0,
        }

    def _resolve_emergency(self, estado: Dict) -> Optional[tuple[tuple[int, ...], int]]:
        if not estado["active"] or estado["signal_group"] not in (1, 2):
            return None
        intersection_id = int(estado["intersection_id"])
        road = int(estado["road"])
        if intersection_id in (1, 2):
            return ((intersection_id,), int(estado["signal_group"]))
        if intersection_id == 0 and road == 1:
            return ((1, 2), int(estado["signal_group"]))
        return None

    def _sync_traffic_controller_state(self, estado: Dict) -> None:
        night_mode = 1 if estado["night_mode"] else 0
        if night_mode != self._last_night_mode_read:
            self._night_mode = bool(night_mode)
            self._last_night_mode_read = night_mode
            self._send_command({"action": "set_night_mode", "enabled": self._night_mode}, target="all")
            log.info("Modo noturno %s (MODBUS)", "ativado" if night_mode else "desativado")

        emergencia = self._resolve_emergency(estado)
        if emergencia == self._last_emergency_route:
            return

        if emergencia is None:
            self._send_command({"action": "set_emergency", "active": False}, target="all")
            self._last_emergency_route = None
            log.info("Emergência desativada (MODBUS)")
            return

        cruzamentos, signal_group = emergencia
        anteriores = set(self._last_emergency_route[0]) if self._last_emergency_route else set()
        for iid in anteriores - set(cruzamentos):
            self._send_command({"action": "set_emergency", "active": False}, target=iid)
        for iid in cruzamentos:
            self._send_command(
                {"action": "set_emergency", "active": True, "signal_group": signal_group},
                target=iid,
            )
        self._last_emergency_route = emergencia
        via = "principal" if signal_group == 1 else "auxiliar"
        log.info(
            "Emergência ativada (MODBUS): cruzamentos %s, via %s",
            list(cruzamentos),
            via,
        )

    def _modbus_state_loop(self) -> None:
        poll_s = float(self.cfg.get("emergency_poll_s", 0.3))
        while self._running.is_set():
            try:
                regs = self._fetch_device_state_block()
                estado = self._parse_device_state(regs)
                if estado != self._estado_sistema:
                    log.info(
                        "Estado simulador: active=%s road=%s intersection=%s "
                        "signal_group=%s night=%s timed_out=%s unattended=%s",
                        estado["active"],
                        estado["road"],
                        estado["intersection_id"],
                        estado["signal_group"],
                        estado["night_mode"],
                        estado["timed_out"],
                        estado["unattended_count"],
                    )
                    self._estado_sistema = dict(estado)
                self._sync_traffic_controller_state(estado)
                self._last_modbus_state_error = None
            except Exception as exc:
                erro = str(exc)
                now = time.monotonic()
                if erro != self._last_modbus_state_error or now - self._modbus_last_error_at >= 30.0:
                    log.warning("Falha no polling MODBUS de estado (0x20): %s", exc)
                    self._last_modbus_state_error = erro
                    self._modbus_last_error_at = now

            time.sleep(poll_s)

    def _overspeed_worker_loop(self) -> None:
        while self._running.is_set():
            try:
                event = self._overspeed_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                iid = int(event["intersection_id"])
                sensor_id = int(event["sensor_id"])
                speed = float(event["speed_kmh"])
                ts = str(event.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")))

                log.warning(
                    "Excesso de velocidade C%d sensor %d: %.1f km/h — acionando LPR",
                    iid,
                    sensor_id,
                    speed,
                )

                camera_addr = self._camera_by_sensor[sensor_id]
                result = self._lpr.capture(camera_addr)

                if result.ok:
                    fine_value = self._calc_fine(speed)
                    self._append_fine_log(
                        timestamp=ts,
                        intersection_id=iid,
                        sensor_id=sensor_id,
                        speed=speed,
                        camera_addr=camera_addr,
                        plate=result.plate,
                        confidence=result.confidence,
                        fine_value=fine_value,
                    )
                    with self._state_lock:
                        self._state[iid].infractions += 1
                else:
                    log.warning("Falha captura LPR sensor=%d status=%d", sensor_id, result.status)
            except Exception:
                log.exception("Erro processando overspeed")

    @staticmethod
    def _calc_fine(speed_kmh: float) -> float:
        over = speed_kmh - 60.0
        if over <= 0:
            return 0.0
        if over <= 20:
            return 130.16
        if over <= 40:
            return 195.23
        return 880.41

    def _append_fine_log(
        self,
        timestamp: str,
        intersection_id: int,
        sensor_id: int,
        speed: float,
        camera_addr: int,
        plate: str,
        confidence: int,
        fine_value: float,
    ) -> None:
        line = (
            f"{timestamp} | C{intersection_id} | S{sensor_id} | {speed:.2f} km/h | "
            f"0x{camera_addr:02X} | {plate} | {confidence}% | R$ {fine_value:.2f}\n"
        )
        with open(self._fines_log, "a", encoding="utf-8") as f:
            f.write(line)

    def _persist_loop(self) -> None:
        while self._running.is_set():
            self._save_state()
            time.sleep(2.0)

    def _save_state(self) -> None:
        with self._state_lock:
            dump = {
                "night_mode": self._night_mode,
                "intersections": {
                    str(iid): {
                        "mode": st.mode,
                        "infractions": st.infractions,
                        "sensors": {
                            str(sid): {
                                "count_total": s.count_total,
                                "flow_cars_min": s.flow_cars_min,
                                "avg_speed_interval_kmh": s.avg_speed_interval_kmh,
                            }
                            for sid, s in st.sensors.items()
                        },
                    }
                    for iid, st in self._state.items()
                },
            }
        atomic_save_json(self._state_file, dump)

    def _cli_loop(self) -> None:
        help_text = (
            "\nComandos:\n"
            "  status\n"
            "  modbus\n"
            "  multas\n"
            "  night on|off\n"
            "  emergency off\n"
            "  emergency <1|2|all> [principal|auxiliar]\n"
            "  manual <1|2> <0..7>\n"
            "  auto <1|2|all>\n"
            "  quit\n"
        )
        print(help_text)

        while self._running.is_set():
            try:
                cmd = input("central> ").strip()
            except EOFError:
                return

            if not self._process_cli_command(cmd):
                print(help_text)

    def _process_cli_command(self, cmd: str) -> bool:
        if not cmd:
            return True
        if cmd == "status":
            self._print_status()
            return True
        if cmd == "modbus":
            self._print_modbus_state()
            return True
        if cmd == "multas":
            self._print_fines_history()
            return True
        if cmd == "quit":
            self._running.clear()
            return True

        parts = cmd.split()
        if self._process_night_cmd(parts):
            return True
        if self._process_emergency_cmd(parts):
            return True
        if self._process_manual_cmd(parts):
            return True
        if self._process_auto_cmd(parts):
            return True
        return False

    def _process_night_cmd(self, parts: List[str]) -> bool:
        if len(parts) != 2 or parts[0] != "night":
            return False
        enabled = parts[1].lower() == "on"
        self._night_mode = enabled
        self._last_night_mode_read = 1 if enabled else 0
        self._send_command({"action": "set_night_mode", "enabled": enabled}, target="all")
        log.info("Modo noturno %s (terminal)", "ativado" if enabled else "desativado")
        return True

    def _process_emergency_cmd(self, parts: List[str]) -> bool:
        if not parts or parts[0] != "emergency":
            return False
        if len(parts) == 2 and parts[1].lower() == "off":
            self._last_emergency_route = None
            self._send_command({"action": "set_emergency", "active": False}, target="all")
            log.info("Emergência desativada (terminal)")
            return True
        if len(parts) < 2:
            return False

        target = parts[1].lower()
        signal_group = 2 if len(parts) >= 3 and parts[2].lower() in ("aux", "auxiliar") else 1
        if target == "all":
            targets = [1, 2]
        elif target in ("1", "2"):
            targets = [int(target)]
        else:
            return False

        for iid in targets:
            self._send_command(
                {"action": "set_emergency", "active": True, "signal_group": signal_group},
                target=iid,
            )
        self._last_emergency_route = (tuple(targets), signal_group)
        via = "principal" if signal_group == 1 else "auxiliar"
        log.info("Emergência ativada (terminal): C%s via %s", target, via)
        return True

    def _process_manual_cmd(self, parts: List[str]) -> bool:
        if len(parts) != 3 or parts[0] != "manual":
            return False
        iid = int(parts[1])
        code = int(parts[2])
        self._send_command({"action": "set_manual_code", "code": code}, target=iid)
        return True

    def _process_auto_cmd(self, parts: List[str]) -> bool:
        if len(parts) != 2 or parts[0] != "auto":
            return False
        target = parts[1]
        if target == "all":
            self._send_command({"action": "resume_automatic"}, target="all")
            return True
        self._send_command({"action": "resume_automatic"}, target=int(target))
        return True

    def _print_modbus_state(self) -> None:
        try:
            regs = self._fetch_device_state_block()
            estado = self._parse_device_state(regs)
            self._estado_sistema = dict(estado)
            print("\n==== MODBUS 0x20 (leitura imediata) ====")
            print(f"active={estado['active']} road={estado['road']} direction={estado['direction']}")
            print(
                f"intersection={estado['intersection_id']} vehicle={estado['vehicle_type']} "
                f"signal_group={estado['signal_group']}"
            )
            print(
                f"night={estado['night_mode']} timed_out={estado['timed_out']} "
                f"unattended={estado['unattended_count']}"
            )
            print(f"registradores brutos: {regs}")
            print("=========================================\n")
        except Exception as exc:
            print(f"\nMODBUS 0x20 indisponível: {exc}\n")

    def _print_status(self) -> None:
        with self._state_lock:
            print("\n==== Estado Consolidado ====")
            print(f"Modo noturno: {'ON' if self._night_mode else 'OFF'}")
            if self._estado_sistema:
                e = self._estado_sistema
                print(
                    f"MODBUS 0x20: active={e['active']} intersection={e['intersection_id']} "
                    f"signal_group={e['signal_group']} night={e['night_mode']}"
                )
                print(
                    f"  timed_out={e['timed_out']} unattended={e['unattended_count']} "
                    f"elapsed={e['elapsed_s_x10'] / 10:.1f}s "
                    f"max_time={e['max_time_s_x10'] / 10:.1f}s"
                )
            elif self._last_modbus_state_error:
                print(f"MODBUS 0x20: erro — {self._last_modbus_state_error}")
            else:
                print("MODBUS 0x20: ainda sem leitura")
            for iid in (1, 2):
                c = self._state[iid]
                print(
                    f"Cruzamento {iid} | conectado={c.connected} | modo={c.mode} | "
                    f"infrações={c.infractions} | atualização={c.last_update_ts}"
                )
                for sid in sorted(c.sensors):
                    s = c.sensors[sid]
                    print(
                        f"  Sensor {sid}: fluxo={s.flow_cars_min:.1f} carros/min | "
                        f"vel. média={s.avg_speed_interval_kmh:.1f} km/h | total={s.count_total}"
                    )
            print("============================\n")

    def _print_fines_history(self) -> None:
        print("\n==== Histórico de multas ====")
        path = Path(self._fines_log)
        if not path.exists():
            print("Nenhuma multa registrada.")
            print("=============================\n")
            return

        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            print("Nenhuma multa registrada.")
            print("=============================\n")
            return

        recent = lines[-10:]
        for idx, line in enumerate(recent, start=1):
            print(f"{idx}. {line}")
        print("=============================\n")


def load_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Entrega 3 — Servidor Central")
    p.add_argument("--config", required=True, help="Caminho do JSON de configuração")
    p.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(args.config)
    app = CentralServer(cfg)

    try:
        app.run()
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário")


if __name__ == "__main__":
    main()
