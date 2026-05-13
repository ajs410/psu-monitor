"""QThread worker that owns the serial port and runs the poll loop.

All serial I/O happens exclusively in this thread.
The UI communicates via Signals (inbound) and a thread-safe command queue (outbound).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from enum import Enum, auto
from typing import Any

import serial
from PySide6.QtCore import QThread, Signal

from .psu_driver import MalformedResponseError, PSUDriver

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_TIMEOUTS = 5
SETPOINT_POLL_EVERY_N = 10  # fetch setpoints once per N measurement polls
COMMAND_CHECK_INTERVAL_S = 0.05  # wake up to check queue at most this often


class CmdType(Enum):
    CONNECT = auto()
    DISCONNECT = auto()
    SET_VOLTAGE = auto()
    SET_CURRENT = auto()
    SET_VOLT_LIMIT = auto()
    SET_CURR_LIMIT = auto()
    SET_OUTPUT = auto()
    SET_POLL_INTERVAL = auto()
    SET_LINE_ENDING = auto()
    QUERY_SETPOINTS = auto()


class SerialWorker(QThread):
    """Polling thread for the PSU serial connection."""

    # Emitted on each successful measurement poll
    measurements_ready = Signal(float, float, float, dict)  # V, A, W, status_dict

    # Emitted whenever setpoints are refreshed (V_set, I_set, V_lim, I_lim, output_on)
    setpoints_ready = Signal(float, float, float, float, bool)

    # Emitted once after a successful connect with the raw *IDN? response
    idn_ready = Signal(str)

    # Connection state changes
    connection_status_changed = Signal(bool, str)  # connected, message

    # Non-fatal errors (logged to status bar)
    error_occurred = Signal(str)

    # Increments on each timeout; resets on success
    timeout_count_changed = Signal(int)

    # Emitted after MAX_CONSECUTIVE_TIMEOUTS failures to prompt user
    reconnect_required = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cmd_queue: queue.Queue[tuple[CmdType, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._driver: PSUDriver | None = None
        self._poll_interval_s = 0.5
        self._paused = False
        self._consecutive_timeouts = 0
        self._poll_counter = 0

    # ── Public API (called from UI thread) ─────────────────────────────────

    def request_connect(self, port: str, baud: int = 115200, line_ending: str = "\n") -> None:
        self._cmd_queue.put((CmdType.CONNECT, (port, baud, line_ending)))

    def request_disconnect(self) -> None:
        self._cmd_queue.put((CmdType.DISCONNECT, None))

    def request_reconnect(self) -> None:
        """Resume paused polling without re-opening the port."""
        self._paused = False
        self._consecutive_timeouts = 0

    def send_set_voltage(self, v: float) -> None:
        self._cmd_queue.put((CmdType.SET_VOLTAGE, v))

    def send_set_current(self, a: float) -> None:
        self._cmd_queue.put((CmdType.SET_CURRENT, a))

    def send_set_volt_limit(self, v: float) -> None:
        self._cmd_queue.put((CmdType.SET_VOLT_LIMIT, v))

    def send_set_curr_limit(self, a: float) -> None:
        self._cmd_queue.put((CmdType.SET_CURR_LIMIT, a))

    def send_set_output(self, state: bool) -> None:
        self._cmd_queue.put((CmdType.SET_OUTPUT, state))

    def send_set_poll_interval(self, ms: int) -> None:
        self._cmd_queue.put((CmdType.SET_POLL_INTERVAL, ms / 1000.0))

    def send_set_line_ending(self, le: str) -> None:
        self._cmd_queue.put((CmdType.SET_LINE_ENDING, le))

    def send_query_setpoints(self) -> None:
        self._cmd_queue.put((CmdType.QUERY_SETPOINTS, None))

    def stop(self) -> None:
        self._stop_event.set()

    # ── Thread entry point ─────────────────────────────────────────────────

    def run(self) -> None:
        last_poll = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            if not self._paused and self._driver and (now - last_poll) >= self._poll_interval_s:
                self._do_poll()
                last_poll = time.monotonic()

            # Wait for a command or the next check interval
            deadline = last_poll + self._poll_interval_s
            remaining = max(0.0, min(deadline - time.monotonic(), COMMAND_CHECK_INTERVAL_S))
            try:
                cmd_type, payload = self._cmd_queue.get(timeout=remaining)
                self._process_command(cmd_type, payload)
            except queue.Empty:
                pass

        # Clean up on thread exit
        if self._driver:
            self._driver.close()
        log.debug("SerialWorker thread exited")

    # ── Command processing (worker thread) ─────────────────────────────────

    def _process_command(self, cmd_type: CmdType, payload: Any) -> None:
        if cmd_type == CmdType.CONNECT:
            port, baud, le = payload
            self._do_connect(port, baud, le)
        elif cmd_type == CmdType.DISCONNECT:
            self._do_disconnect()
        elif cmd_type == CmdType.SET_POLL_INTERVAL:
            self._poll_interval_s = payload
        elif cmd_type == CmdType.SET_LINE_ENDING:
            if self._driver:
                self._driver.line_ending = payload
        elif cmd_type == CmdType.QUERY_SETPOINTS:
            self._do_poll_setpoints()
        elif self._driver:
            # Device-write commands only make sense when connected
            try:
                if cmd_type == CmdType.SET_VOLTAGE:
                    self._driver.set_voltage(payload)
                elif cmd_type == CmdType.SET_CURRENT:
                    self._driver.set_current(payload)
                elif cmd_type == CmdType.SET_VOLT_LIMIT:
                    self._driver.set_volt_limit(payload)
                elif cmd_type == CmdType.SET_CURR_LIMIT:
                    self._driver.set_curr_limit(payload)
                elif cmd_type == CmdType.SET_OUTPUT:
                    self._driver.set_output(payload)
                # Refresh setpoints after any write so the UI stays in sync
                self._do_poll_setpoints()
            except serial.SerialException as exc:
                self._handle_serial_error(exc)

    def _do_connect(self, port: str, baud: int, line_ending: str) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=1.0,
                write_timeout=1.0,
            )
            self._driver = PSUDriver(ser, line_ending=line_ending)
            self._consecutive_timeouts = 0
            self._paused = False
            self._poll_counter = 0
            self.connection_status_changed.emit(True, port)
            # Query IDN so the status bar shows model/serial immediately
            try:
                idn = self._driver.idn()
                if idn:
                    self.idn_ready.emit(idn)
            except Exception:  # noqa: BLE001
                pass
            # Immediately fetch setpoints so the UI shows current device state
            self._do_poll_setpoints()
        except serial.SerialException as exc:
            self._driver = None
            self.connection_status_changed.emit(False, str(exc))

    def _do_disconnect(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
        self._paused = False
        self._consecutive_timeouts = 0
        self.connection_status_changed.emit(False, "Disconnected by user")

    # ── Poll helpers ───────────────────────────────────────────────────────

    def _do_poll(self) -> None:
        try:
            info = self._driver.measure_all_info()
        except serial.SerialTimeoutException:
            self._handle_timeout()
            return
        except MalformedResponseError as exc:
            log.warning("Malformed: %s", exc)
            self.error_occurred.emit(f"Malformed response (skipped): {exc}")
            return
        except serial.SerialException as exc:
            self._handle_serial_error(exc)
            return

        # Success — reset timeout counter
        if self._consecutive_timeouts > 0:
            self._consecutive_timeouts = 0
            self.timeout_count_changed.emit(0)

        status = {k: v for k, v in info.items() if k not in ("volts", "amps", "watts")}
        self.measurements_ready.emit(info["volts"], info["amps"], info["watts"], status)

        self._poll_counter += 1
        if self._poll_counter % SETPOINT_POLL_EVERY_N == 0:
            self._do_poll_setpoints()

    def _do_poll_setpoints(self) -> None:
        if not self._driver:
            return
        try:
            sp = self._driver.get_all_setpoints()
            self.setpoints_ready.emit(
                sp["v_set"], sp["i_set"], sp["v_lim"], sp["i_lim"], sp["output_on"]
            )
        except (serial.SerialException, ValueError, MalformedResponseError) as exc:
            log.debug("Setpoint poll failed: %s", exc)

    # ── Error handling ─────────────────────────────────────────────────────

    def _handle_timeout(self) -> None:
        self._consecutive_timeouts += 1
        self.timeout_count_changed.emit(self._consecutive_timeouts)
        self.error_occurred.emit(
            f"Timeout #{self._consecutive_timeouts} on {self._driver.port if self._driver else '?'}"
        )
        if self._consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
            self._paused = True
            self.connection_status_changed.emit(False, "Polling paused — too many timeouts")
            self.reconnect_required.emit()

    def _handle_serial_error(self, exc: serial.SerialException) -> None:
        log.error("Serial error: %s", exc)
        if self._driver:
            self._driver.close()
            self._driver = None
        self.connection_status_changed.emit(False, str(exc))
