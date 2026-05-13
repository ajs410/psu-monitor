"""Large numeric readout widgets for voltage, current, and power."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

_COLOR_NORMAL = "#00CC44"
_COLOR_WARN = "#DDCC00"
_COLOR_FAULT = "#CC2200"
_COLOR_INACTIVE = "#444444"


class NumericGauge(QFrame):
    """A large readout showing a single electrical quantity."""

    def __init__(self, title: str, unit: str, parent=None) -> None:
        super().__init__(parent)
        self._unit = unit
        self._active = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 6)
        root.setSpacing(0)

        # Title row
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold;")
        root.addWidget(title_lbl)

        # Value + unit row
        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self._value_lbl = QLabel("—")
        font = QFont("Courier New", 30, QFont.Weight.Bold)
        self._value_lbl.setFont(font)
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._value_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        value_row.addWidget(self._value_lbl)

        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet("color: #888888; font-size: 14px;")
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        unit_lbl.setFixedWidth(20)
        value_row.addWidget(unit_lbl)

        root.addLayout(value_row)
        self._set_color(_COLOR_INACTIVE)

    # ── Public API ─────────────────────────────────────────────────────────

    def set_value(self, value: float, state: str = "normal") -> None:
        """Update the displayed value.

        *state* must be one of ``"normal"``, ``"warn"``, ``"fault"``.
        """
        self._value_lbl.setText(f"{value:9.3f}")
        color_map = {
            "normal": _COLOR_NORMAL,
            "warn": _COLOR_WARN,
            "fault": _COLOR_FAULT,
        }
        self._set_color(color_map.get(state, _COLOR_NORMAL))
        self._active = True

    def clear(self) -> None:
        """Show placeholder when disconnected (greyed out)."""
        self._value_lbl.setText("     —")
        self._set_color(_COLOR_INACTIVE)
        self._active = False

    def set_active(self, active: bool) -> None:
        if not active:
            self.clear()

    # ── Internal ───────────────────────────────────────────────────────────

    def _set_color(self, color: str) -> None:
        self._value_lbl.setStyleSheet(f"color: {color};")
