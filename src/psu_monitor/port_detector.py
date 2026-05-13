"""COM port enumeration and CH340 detection helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import serial.tools.list_ports as lp

log = logging.getLogger(__name__)

# Target device uses a CH340 USB-to-Serial chip
CH340_VID = 0x1A86
CH340_PID = 0x7523
CH340_DESC_FRAGMENT = "CH340"


@dataclass
class PortInfo:
    port: str
    description: str
    hwid: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    is_ch340: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_ch340 = (
            CH340_DESC_FRAGMENT in (self.description or "").upper()
            or (self.vid == CH340_VID and self.pid == CH340_PID)
        )

    def display_label(self) -> str:
        """Human-readable label for the port-selector combo box."""
        desc = self.description or "Unknown device"
        marker = " ★" if self.is_ch340 else ""
        return f"{self.port}  —  {desc}{marker}"


def list_ports() -> list[PortInfo]:
    """Return all available serial ports."""
    result = []
    for p in lp.comports():
        result.append(
            PortInfo(
                port=p.device,
                description=p.description or "",
                hwid=p.hwid or "",
                vid=p.vid,
                pid=p.pid,
                serial_number=p.serial_number,
            )
        )
    result.sort(key=lambda p: (not p.is_ch340, p.port))
    return result


def find_ch340_ports() -> list[PortInfo]:
    return [p for p in list_ports() if p.is_ch340]


def port_set() -> set[str]:
    """Return the set of currently available port device names."""
    return {p.device for p in lp.comports()}
