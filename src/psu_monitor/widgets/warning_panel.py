"""Status/fault indicator widgets and soft-bounds warning banner."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..constants import (
    LBL_MODE,
    LBL_OCP,
    LBL_OTP,
    LBL_OVP,
    MODE_CC,
    MODE_CV,
    MODE_FAULT,
    MODE_STANDBY,
    MODE_UNKNOWN,
)

# LED state → background colour
_LED_COLORS = {
    "off": "#2a2a2a",
    "ok": "#004400",
    "active": "#00AA44",
    "warn": "#AA6600",
    "fault": "#AA0000",
}


class LedIndicator(QLabel):
    """Coloured rectangle that resembles a panel LED."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(52)
        self._state = "off"
        self._apply()

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self._apply()

    def _apply(self) -> None:
        bg = _LED_COLORS.get(self._state, _LED_COLORS["off"])
        self.setStyleSheet(
            f"QLabel {{"
            f"  background-color: {bg};"
            f"  color: #ffffff;"
            f"  border: 1px solid #555555;"
            f"  border-radius: 3px;"
            f"  padding: 2px 6px;"
            f"  font-weight: bold;"
            f"  font-size: 11px;"
            f"}}"
        )


class SoftBoundsWarning(QFrame):
    """Persistent amber banner shown when current is outside soft limits."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._lbl)
        self.hide()

    def show_warning(self, message: str) -> None:
        self._lbl.setText(message)
        self.setStyleSheet(
            "QFrame {"
            "  background-color: #BB6600;"
            "  border: 2px solid #FF8800;"
            "  border-radius: 4px;"
            "}"
            "QLabel {"
            "  color: #ffffff;"
            "  font-weight: bold;"
            "  background-color: transparent;"
            "}"
        )
        self.show()

    def clear_warning(self) -> None:
        self.hide()


class WarningPanel(QWidget):
    """Compact panel with hardware-fault LEDs, mode indicator, and soft-bounds banner."""

    _MODE_LABELS = {
        0: (MODE_STANDBY, "warn"),
        1: (MODE_CV, "active"),
        2: (MODE_CC, "active"),
        3: (MODE_FAULT, "fault"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # LED row
        led_row = QHBoxLayout()
        led_row.setSpacing(4)
        self._ovp_led = LedIndicator(LBL_OVP)
        self._ocp_led = LedIndicator(LBL_OCP)
        self._otp_led = LedIndicator(LBL_OTP)
        led_row.addWidget(self._ovp_led)
        led_row.addWidget(self._ocp_led)
        led_row.addWidget(self._otp_led)
        led_row.addStretch()

        self._mode_led = LedIndicator(MODE_UNKNOWN)
        self._mode_led.setMinimumWidth(70)
        led_row.addWidget(self._mode_led)

        root.addLayout(led_row)

        # Soft-bounds warning banner
        self._soft_warn = SoftBoundsWarning()
        root.addWidget(self._soft_warn)

    # ── Public API ─────────────────────────────────────────────────────────

    def update_faults(self, ovp: bool, ocp: bool, otp: bool, mode: int) -> None:
        self._ovp_led.set_state("fault" if ovp else "ok")
        self._ocp_led.set_state("fault" if ocp else "ok")
        self._otp_led.set_state("fault" if otp else "ok")

        label, state = self._MODE_LABELS.get(mode, (MODE_UNKNOWN, "off"))
        self._mode_led.setText(label)
        self._mode_led.set_state(state)

    def clear_faults(self) -> None:
        for led in (self._ovp_led, self._ocp_led, self._otp_led):
            led.set_state("off")
        self._mode_led.setText(MODE_UNKNOWN)
        self._mode_led.set_state("off")

    def show_soft_warning(self, message: str) -> None:
        self._soft_warn.show_warning(message)

    def clear_soft_warning(self) -> None:
        self._soft_warn.clear_warning()
