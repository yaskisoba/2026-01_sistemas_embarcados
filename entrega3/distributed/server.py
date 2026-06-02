from __future__ import annotations

import argparse
import json
import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from common.gpio_hal import GPIOAdapter
from common.messages import LineBuffer, decode_message, encode_message
from common.traffic_math import speed_kmh_from_delta


log = logging.getLogger(__name__)


@dataclass
class SensorStats:
    sensor_id: int
    pin_a: int
    pin_b: int
    count_total: int = 0
    count_since_last: int = 0
    sum_speed_since_last: float = 0.0
    last_a_ts: Optional[float] = None


class IntersectionController:
    def __init__(self, cfg: Dict, overspeed_queue: "queue.Queue[dict]") -> None:
        self.cfg = cfg
        self.intersection_id: int = int(cfg["intersection_id"])
        self.gpio = GPIOAdapter(force_mock=bool(cfg.get("force_mock_gpio", False)))
        self.output_bits: List[int] = list(cfg["semaphore_bits"])
        self.buttons: Dict[str, int] = dict(cfg["buttons"])

        self._overspeed_queue = overspeed_queue
        self._running = threading.Event()
        self._running.set()
        self._lock = threading.Lock()

        self._mode: str = "normal"  # normal, night, emergency, manual
        self._night_enabled = False
        self._emergency_active = False
        self._emergency_signal_group = 1
        self._manual_code: Optional[int] = None

        self._ped_main_req = False
        self._ped_cross_req = False

        self._sensors: Dict[int, SensorStats] = {}
        for s in cfg["sensors"]:
            st = SensorStats(sensor_id=int(s["id"]), pin_a=int(s["pin_a"]), pin_b=int(s["pin_b"]))
            self._sensors[st.sensor_id] = st

        self._thread = threading.Thread(target=self._control_loop, daemon=True)

    def setup(self) -> None:
        for pin in self.output_bits:
            self.gpio.setup_output(pin)
            self.gpio.write(pin, 0)

        for name, pin in self.buttons.items():
            self.gpio.setup_input(pin, pull_down=True)
            self.gpio.add_rising_callback(pin, self._mk_button_cb(name), debounce_ms=350)

        for sensor in self._sensors.values():
            self.gpio.setup_input(sensor.pin_a, pull_down=True)
            self.gpio.setup_input(sensor.pin_b, pull_down=True)
            self.gpio.add_rising_callback(sensor.pin_a, self._mk_sensor_a_cb(sensor.sensor_id), debounce_ms=20)
            self.gpio.add_rising_callback(sensor.pin_b, self._mk_sensor_b_cb(sensor.sensor_id), debounce_ms=20)

    def start(self) -> None:
        self.setup()
        self._thread.start()
        log.info(
            "Cruzamento %d iniciado (GPIO mock=%s)",
            self.intersection_id,
            self.gpio.is_mock,
        )

    def stop(self) -> None:
        self._running.clear()
        self._thread.join(timeout=2)
        self.gpio.cleanup()

    def _mk_button_cb(self, name: str):
        def cb(_: int) -> None:
            with self._lock:
                if "principal" in name.lower():
                    self._ped_main_req = True
                else:
                    self._ped_cross_req = True
            log.info("[C%d] Botão pressionado: %s", self.intersection_id, name)

        return cb

    def _mk_sensor_a_cb(self, sensor_id: int):
        def cb(_: int) -> None:
            with self._lock:
                self._sensors[sensor_id].last_a_ts = time.monotonic()

        return cb

    def _mk_sensor_b_cb(self, sensor_id: int):
        def cb(_: int) -> None:
            now = time.monotonic()
            with self._lock:
                sensor = self._sensors[sensor_id]
                if sensor.last_a_ts is None:
                    return
                delta_s = now - sensor.last_a_ts
                sensor.last_a_ts = None
                speed = speed_kmh_from_delta(delta_s)
                sensor.count_total += 1
                sensor.count_since_last += 1
                sensor.sum_speed_since_last += speed

            if speed > 60.0:
                payload = {
                    "type": "overspeed",
                    "intersection_id": self.intersection_id,
                    "sensor_id": sensor_id,
                    "speed_kmh": round(speed, 2),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                self._overspeed_queue.put(payload)
                log.warning("[C%d] Excesso de velocidade no sensor %d: %.1f km/h", self.intersection_id, sensor_id, speed)

        return cb

    def _write_code(self, code: int) -> None:
        for i, pin in enumerate(self.output_bits):
            bit = (code >> i) & 0x1
            self.gpio.write(pin, bit)

    def _wait_with_preemption(self, min_s: float, max_s: float, can_anticipate: bool, check_main_req: bool) -> None:
        start = time.monotonic()
        while self._running.is_set():
            time.sleep(0.05)
            with self._lock:
                mode_changed = self._mode != "normal"
                if check_main_req:
                    ped_req = self._ped_main_req
                else:
                    ped_req = self._ped_cross_req
            if mode_changed:
                return

            elapsed = time.monotonic() - start
            if elapsed >= max_s:
                return
            if can_anticipate and elapsed >= min_s and ped_req:
                return

    def _consume_ped_flags(self) -> None:
        with self._lock:
            self._ped_main_req = False
            self._ped_cross_req = False

    def _control_loop(self) -> None:
        while self._running.is_set():
            with self._lock:
                mode = self._mode
                emergency_signal_group = self._emergency_signal_group
                manual_code = self._manual_code

            if mode == "night":
                self._write_code(0)
                self._sleep_interruptible(1.0)
                self._write_code(4)
                self._sleep_interruptible(1.0)
                continue

            if mode == "emergency":
                self._write_code(1 if emergency_signal_group == 1 else 5)
                self._sleep_interruptible(0.2)
                continue

            if mode == "manual":
                self._write_code(4 if manual_code is None else manual_code)
                self._sleep_interruptible(0.2)
                continue

            self._consume_ped_flags()

            self._write_code(1)
            self._wait_with_preemption(min_s=15, max_s=30, can_anticipate=True, check_main_req=False)

            self._write_code(2)
            self._sleep_interruptible(3)

            self._write_code(4)
            self._sleep_interruptible(2)

            self._write_code(5)
            self._wait_with_preemption(min_s=5, max_s=10, can_anticipate=True, check_main_req=True)

            self._write_code(6)
            self._sleep_interruptible(3)

            self._write_code(4)
            self._sleep_interruptible(2)

    def _sleep_interruptible(self, secs: float) -> None:
        end = time.monotonic() + secs
        while self._running.is_set() and time.monotonic() < end:
            time.sleep(0.05)
            with self._lock:
                if self._mode != "normal" and secs > 0.3:
                    return

    def _fallback_mode(self) -> str:
        return "night" if self._night_enabled else "normal"

    def _apply_set_night_mode(self, cmd: Dict) -> None:
        enabled = bool(cmd.get("enabled", False))
        self._night_enabled = enabled
        self._mode = "night" if enabled else "normal"

    def _apply_set_emergency(self, cmd: Dict) -> None:
        active = bool(cmd.get("active", False))
        signal_group = int(cmd.get("signal_group", 1))
        self._emergency_active = active
        self._emergency_signal_group = signal_group
        self._mode = "emergency" if active else self._fallback_mode()

    def _apply_set_manual_code(self, cmd: Dict) -> None:
        code = cmd.get("code")
        if code is None:
            self._manual_code = None
            self._mode = self._fallback_mode()
            return
        self._manual_code = int(code)
        self._mode = "manual"

    def _apply_resume_automatic(self) -> None:
        self._manual_code = None
        self._emergency_active = False
        self._mode = self._fallback_mode()

    def apply_command(self, cmd: Dict) -> None:
        action = cmd.get("action")
        with self._lock:
            if action == "set_night_mode":
                self._apply_set_night_mode(cmd)
                return
            if action == "set_emergency":
                self._apply_set_emergency(cmd)
                return
            if action == "set_manual_code":
                self._apply_set_manual_code(cmd)
                return
            if action == "resume_automatic":
                self._apply_resume_automatic()

    def snapshot_sensors(self) -> List[Dict]:
        out = []
        with self._lock:
            for sensor in self._sensors.values():
                avg_speed = 0.0
                if sensor.count_since_last > 0:
                    avg_speed = sensor.sum_speed_since_last / sensor.count_since_last

                out.append(
                    {
                        "sensor_id": sensor.sensor_id,
                        "count_total": sensor.count_total,
                        "count_interval": sensor.count_since_last,
                        "avg_speed_interval_kmh": round(avg_speed, 2),
                    }
                )

                sensor.count_since_last = 0
                sensor.sum_speed_since_last = 0.0
        return out

    def current_mode(self) -> str:
        with self._lock:
            return self._mode


class DistributedNode:
    def __init__(self, cfg: Dict) -> None:
        self.cfg = cfg
        self.intersection_id = int(cfg["intersection_id"])
        self.central_host = cfg["central_host"]
        self.central_port = int(cfg["central_port"])
        self.telemetry_interval_s = float(cfg.get("telemetry_interval_s", 2.0))
        self.reconnect_delay_s = float(cfg.get("reconnect_delay_s", 1.0))

        self._overspeed_queue: "queue.Queue[dict]" = queue.Queue()
        self.controller = IntersectionController(cfg=cfg, overspeed_queue=self._overspeed_queue)
        self._running = True

    def run(self) -> None:
        self.controller.start()
        try:
            while self._running:
                self._connect_and_stream()
                time.sleep(self.reconnect_delay_s)
        finally:
            self.controller.stop()

    def _connect_and_stream(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((self.central_host, self.central_port))
            sock.settimeout(0.5)
            log.info("[C%d] Conectado ao central %s:%d", self.intersection_id, self.central_host, self.central_port)

            hello = {
                "type": "hello",
                "intersection_id": self.intersection_id,
                "name": self.cfg.get("name", f"cross-{self.intersection_id}"),
            }
            sock.sendall(encode_message(hello))

            rx_thread = threading.Thread(target=self._receive_loop, args=(sock,), daemon=True)
            rx_thread.start()

            last_tel = 0.0
            while self._running:
                now = time.monotonic()
                while True:
                    try:
                        alert = self._overspeed_queue.get_nowait()
                    except queue.Empty:
                        break
                    sock.sendall(encode_message(alert))

                if now - last_tel >= self.telemetry_interval_s:
                    telemetry = {
                        "type": "telemetry",
                        "intersection_id": self.intersection_id,
                        "mode": self.controller.current_mode(),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "sensors": self.controller.snapshot_sensors(),
                    }
                    sock.sendall(encode_message(telemetry))
                    last_tel = now

                time.sleep(0.05)

        except Exception as exc:
            log.warning("[C%d] Desconectado do central: %s", self.intersection_id, exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _receive_loop(self, sock: socket.socket) -> None:
        buf = LineBuffer()
        while self._running:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    return
                self._consume_incoming_chunk(buf, chunk)
            except socket.timeout:
                continue
            except Exception:
                return

    def _consume_incoming_chunk(self, buf: LineBuffer, chunk: bytes) -> None:
        buf.feed(chunk)
        while True:
            line = buf.pop_line()
            if line is None:
                return
            self._handle_incoming_line(line)

    def _handle_incoming_line(self, line: bytes) -> None:
        msg = decode_message(line)
        if msg.get("type") != "command":
            return
        target = msg.get("target", "all")
        if target in ("all", self.intersection_id):
            self.controller.apply_command(msg)


def load_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Servidor Distribuído - Trabalho 1 (FSE)")
    p.add_argument("--config", required=True, help="Caminho do JSON de configuração do cruzamento")
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
    node = DistributedNode(cfg)

    try:
        node.run()
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário")


if __name__ == "__main__":
    main()
