"""Settings panel for soft current bounds, debounce, and log flush interval."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
)

from ..constants import LBL_DEBOUNCE, LBL_FLUSH_ROWS, LBL_MAX_AMPS, LBL_MIN_AMPS, LBL_SOFT_BOUNDS


class SettingsPanel(QGroupBox):
    """Editable settings for soft current bounds and logging behaviour."""

    bounds_changed = Signal(object, object, int)  # (min_a | None, max_a | None, debounce)

    def __init__(self, config, parent=None) -> None:
        super().__init__(LBL_SOFT_BOUNDS, parent)
        self._config = config

        form = QFormLayout(self)
        form.setContentsMargins(8, 8, 8, 8)

        # Min current
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(-1.0, 100.0)
        self._min_spin.setDecimals(3)
        self._min_spin.setSuffix(" A")
        self._min_spin.setSpecialValueText("— (off)")
        self._min_spin.setValue(config.get("soft_current_min") or -1.0)
        self._min_spin.editingFinished.connect(self._emit)
        form.addRow(LBL_MIN_AMPS, self._min_spin)

        # Max current
        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(-1.0, 100.0)
        self._max_spin.setDecimals(3)
        self._max_spin.setSuffix(" A")
        self._max_spin.setSpecialValueText("— (off)")
        self._max_spin.setValue(config.get("soft_current_max") or -1.0)
        self._max_spin.editingFinished.connect(self._emit)
        form.addRow(LBL_MAX_AMPS, self._max_spin)

        # Debounce count
        self._debounce_spin = QSpinBox()
        self._debounce_spin.setRange(1, 100)
        self._debounce_spin.setValue(config.get("debounce_count", 3))
        self._debounce_spin.editingFinished.connect(self._emit)
        form.addRow(LBL_DEBOUNCE, self._debounce_spin)

        # Log flush interval
        self._flush_spin = QSpinBox()
        self._flush_spin.setRange(1, 1000)
        self._flush_spin.setValue(config.get("flush_every_n_rows", 1))
        self._flush_spin.editingFinished.connect(self._emit)
        form.addRow(LBL_FLUSH_ROWS, self._flush_spin)

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def min_amps(self) -> float | None:
        v = self._min_spin.value()
        return None if v < 0.0 else v

    @property
    def max_amps(self) -> float | None:
        v = self._max_spin.value()
        return None if v < 0.0 else v

    @property
    def debounce(self) -> int:
        return self._debounce_spin.value()

    @property
    def flush_every(self) -> int:
        return self._flush_spin.value()

    # ── Internal ───────────────────────────────────────────────────────────

    def _emit(self) -> None:
        self._config.set("soft_current_min", self.min_amps)
        self._config.set("soft_current_max", self.max_amps)
        self._config.set("debounce_count", self.debounce)
        self._config.set("flush_every_n_rows", self.flush_every)
        self.bounds_changed.emit(self.min_amps, self.max_amps, self.debounce)
