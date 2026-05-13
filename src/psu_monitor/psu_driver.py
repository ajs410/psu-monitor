"""SCPI command abstractions for a single-channel DC power supply.

All methods must be called exclusively from the SerialWorker thread.
"""

from __future__ import annotations

import logging

import serial

log = logging.getLogger(__name__)

_MODE_MAP = {0: "STANDBY", 1: "CV", 2: "CC", 3: "FAULT"}


class MalformedResponseError(ValueError):
    """Raised when the device returns an unexpected or truncated response."""


class PSUDriver:
    """Thin SCPI wrapper over a ``serial.Serial`` instance."""

    def __init__(self, ser: serial.Serial, line_ending: str = "\n") -> None:
        self._ser = ser
        self.line_ending = line_ending  # '\n' or '\r\n'

    # ── Low-level helpers ──────────────────────────────────────────────────

    def _write(self, cmd: str) -> None:
        payload = (cmd + self.line_ending).encode("ascii")
        self._ser.write(payload)
        self._ser.flush()

    def _readline(self) -> str:
        raw = self._ser.readline()
        if not raw:
            raise serial.SerialTimeoutException(f"No response to last command")
        decoded = raw.decode("ascii", errors="replace").strip()
        log.debug("← %r", decoded)
        return decoded

    def _query(self, cmd: str) -> str:
        log.debug("→ %s", cmd)
        self._write(cmd)
        return self._readline()

    # ── Queries ────────────────────────────────────────────────────────────

    def idn(self) -> str:
        return self._query("*IDN?")

    def measure_all_info(self) -> dict:
        """Return a dict with volts, amps, watts, faults, and mode."""
        raw = self._query("MEAS:ALL:INFO?")
        # Device may return space- or comma-delimited fields
        parts = raw.replace(",", " ").split()
        if len(parts) < 7:
            raise MalformedResponseError(
                f"MEAS:ALL:INFO? returned {len(parts)} fields, expected 7: {raw!r}"
            )
        try:
            return {
                "volts": float(parts[0]),
                "amps": float(parts[1]),
                "watts": float(parts[2]),
                "ovp_fault": parts[3] in ("1", "ON"),
                "ocp_fault": parts[4] in ("1", "ON"),
                "otp_fault": parts[5] in ("1", "ON"),
                "mode": int(parts[6]),
                "mode_name": _MODE_MAP.get(int(parts[6]), "?"),
            }
        except (ValueError, IndexError) as exc:
            raise MalformedResponseError(raw) from exc

    def get_voltage_set(self) -> float:
        return float(self._query("VOLT?"))

    def get_current_set(self) -> float:
        return float(self._query("CURR?"))

    def get_output_state(self) -> bool:
        resp = self._query("OUTP?").strip().upper()
        return resp in ("1", "ON")

    def get_volt_limit(self) -> float:
        return float(self._query("VOLT:LIM?"))

    def get_curr_limit(self) -> float:
        return float(self._query("CURR:LIM?"))

    def get_all_setpoints(self) -> dict:
        """Query all setpoints in sequence; returns dict."""
        return {
            "v_set": self.get_voltage_set(),
            "i_set": self.get_current_set(),
            "v_lim": self.get_volt_limit(),
            "i_lim": self.get_curr_limit(),
            "output_on": self.get_output_state(),
        }

    # ── Set commands ───────────────────────────────────────────────────────

    def set_voltage(self, v: float) -> None:
        self._write(f"VOLT {v:.3f}")

    def set_current(self, a: float) -> None:
        self._write(f"CURR {a:.3f}")

    def set_volt_limit(self, v: float) -> None:
        self._write(f"VOLT:LIM {v:.3f}")

    def set_curr_limit(self, a: float) -> None:
        self._write(f"CURR:LIM {a:.3f}")

    def set_output(self, state: bool) -> None:
        self._write(f"OUTP {'ON' if state else 'OFF'}")

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        try:
            if self._ser.is_open:
                self._ser.close()
        except Exception:  # noqa: BLE001
            pass

    @property
    def port(self) -> str:
        return self._ser.port or ""
