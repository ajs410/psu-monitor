"""Tab-separated CSV data logger with per-row flush."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_HEADER = "\t".join(
    [
        "timestamp_iso",
        "elapsed_s",
        "voltage_v",
        "current_a",
        "power_w",
        "voltage_set",
        "current_set",
        "output_on",
        "mode",
        "ovp_fault",
        "ocp_fault",
        "otp_fault",
        "note",
    ]
)


class DataLogger:
    """Write measurement rows to a tab-delimited file.

    All methods are safe to call from any thread (they hold no Qt objects).
    """

    def __init__(self) -> None:
        self._fh = None
        self._start_mono: float | None = None
        self._row_count = 0
        self._flush_every = 1
        self._rows_since_flush = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self, filepath: Path | str, session_note: str = "", flush_every: int = 1) -> None:
        """Open (or overwrite) *filepath* and write a header."""
        self.stop()
        self._fh = open(filepath, "w", newline="", encoding="utf-8")  # noqa: SIM115
        self._flush_every = max(1, flush_every)
        self._start_mono = time.monotonic()
        self._row_count = 0
        self._rows_since_flush = 0

        ts = datetime.now().isoformat(timespec="milliseconds")
        self._fh.write(f"# PSU Monitor session started {ts}\n")
        if session_note:
            self._fh.write(f"# Note: {session_note}\n")
        self._fh.write(_HEADER + "\n")
        self._fh.flush()
        log.info("Logging started → %s", filepath)

    def stop(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass
        self._fh = None
        self._start_mono = None
        log.info("Logging stopped after %d rows", self._row_count)

    # ── Data writing ───────────────────────────────────────────────────────

    def log(
        self,
        volts: float,
        amps: float,
        watts: float,
        v_set: float,
        i_set: float,
        output_on: bool,
        mode: int,
        ovp: bool,
        ocp: bool,
        otp: bool,
        note: str = "",
    ) -> None:
        if self._fh is None:
            return
        elapsed = time.monotonic() - (self._start_mono or 0.0)
        ts = datetime.now().isoformat(timespec="milliseconds")
        row = "\t".join(
            [
                ts,
                f"{elapsed:.3f}",
                f"{volts:.4f}",
                f"{amps:.4f}",
                f"{watts:.4f}",
                f"{v_set:.4f}",
                f"{i_set:.4f}",
                "1" if output_on else "0",
                str(mode),
                "1" if ovp else "0",
                "1" if ocp else "0",
                "1" if otp else "0",
                note.replace("\t", " "),
            ]
        )
        self._fh.write(row + "\n")
        self._row_count += 1
        self._rows_since_flush += 1
        if self._rows_since_flush >= self._flush_every:
            self._fh.flush()
            self._rows_since_flush = 0

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._fh is not None

    @property
    def row_count(self) -> int:
        return self._row_count

    @property
    def elapsed_seconds(self) -> float:
        if self._start_mono is None:
            return 0.0
        return time.monotonic() - self._start_mono
