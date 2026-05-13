"""pyqtgraph real-time rolling chart with dual Y-axes."""

from __future__ import annotations

import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    LBL_CUSTOM_WINDOW,
    LBL_SHOW_I,
    LBL_SHOW_V,
    LBL_SHOW_W,
    LBL_CHART_WINDOW,
    WINDOW_OPTIONS,
)

# Trace colours
_COLOR_V = "#FFD700"   # gold   — voltage
_COLOR_I = "#00BFFF"   # sky    — current
_COLOR_W = "#FF69B4"   # pink   — power


class PSUPlotWidget(QWidget):
    """Rolling time-series chart widget."""

    def __init__(
        self,
        window_s: int = 60,
        show_v: bool = True,
        show_i: bool = True,
        show_w: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._window_s = window_s
        self._t0 = time.monotonic()
        self._dirty = False

        # Rolling buffers — one deque per series
        self._t: deque[float] = deque()
        self._v: deque[float] = deque()
        self._i: deque[float] = deque()
        self._w: deque[float] = deque()

        self._build_ui()

        # Restore persisted state without triggering callbacks
        self._restore_state(window_s, show_v, show_i, show_w)

        # Redraw at a fixed 20 Hz, decoupled from the serial poll rate
        self._redraw_timer = QTimer(self)
        self._redraw_timer.timeout.connect(self._redraw_if_dirty)
        self._redraw_timer.start(50)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)
        ctrl.addWidget(QLabel(LBL_CHART_WINDOW))

        self._window_combo = QComboBox()
        for label, _ in WINDOW_OPTIONS:
            self._window_combo.addItem(label)
        self._window_combo.addItem(LBL_CUSTOM_WINDOW)
        # Select the closest default
        self._window_combo.setCurrentIndex(1)  # 60 s
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)
        ctrl.addWidget(self._window_combo)

        ctrl.addStretch()

        self._chk_v = QCheckBox(LBL_SHOW_V)
        self._chk_v.setChecked(True)
        self._chk_v.setStyleSheet(f"color: {_COLOR_V};")
        self._chk_v.toggled.connect(self._update_visibility)
        ctrl.addWidget(self._chk_v)

        self._chk_i = QCheckBox(LBL_SHOW_I)
        self._chk_i.setChecked(True)
        self._chk_i.setStyleSheet(f"color: {_COLOR_I};")
        self._chk_i.toggled.connect(self._update_visibility)
        ctrl.addWidget(self._chk_i)

        self._chk_w = QCheckBox(LBL_SHOW_W)
        self._chk_w.setChecked(True)
        self._chk_w.setStyleSheet(f"color: {_COLOR_W};")
        self._chk_w.toggled.connect(self._update_visibility)
        ctrl.addWidget(self._chk_w)

        root.addLayout(ctrl)

        # Build the pyqtgraph widget
        pg.setConfigOption("background", "#1e1e1e")
        pg.setConfigOption("foreground", "#cccccc")

        self._pw = pg.PlotWidget()
        pi = self._pw.getPlotItem()
        pi.setLabel("left", "Voltage", units="V", color=_COLOR_V)
        pi.showAxis("right")
        pi.getAxis("right").setLabel("Current / Power", units="A / W", color=_COLOR_I)
        pi.getAxis("bottom").setLabel("Time", units="s")
        pi.showGrid(x=True, y=True, alpha=0.3)
        pi.addLegend(offset=(10, 10))
        pi.setMouseEnabled(x=False, y=True)
        pi.enableAutoRange(axis="x", enable=False)
        pi.setXRange(-self._window_s, 0, padding=0)

        # Primary view box hosts voltage
        self._curve_v = pi.plot(pen=pg.mkPen(_COLOR_V, width=2), name="V (left)")

        # Secondary view box for current + power (right axis)
        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi.vb)
        self._vb2.setMouseEnabled(x=False, y=True)
        self._vb2.enableAutoRange(axis="x", enable=False)

        self._curve_i = pg.PlotCurveItem(pen=pg.mkPen(_COLOR_I, width=2), name="I (right)")
        self._curve_w = pg.PlotCurveItem(pen=pg.mkPen(_COLOR_W, width=1.5), name="W (right)")
        self._vb2.addItem(self._curve_i)
        self._vb2.addItem(self._curve_w)

        # Add legend entries for secondary curves
        pi.legend.addItem(self._curve_i, "I (right)")
        pi.legend.addItem(self._curve_w, "W (right)")

        # Keep secondary ViewBox geometry in sync
        pi.vb.sigResized.connect(self._sync_vb)

        root.addWidget(self._pw, stretch=1)

    # ── Public API ─────────────────────────────────────────────────────────

    def append(self, volts: float, amps: float, watts: float) -> None:
        """Buffer one sample; the redraw timer will paint it within 50 ms."""
        t = time.monotonic() - self._t0
        self._t.append(t)
        self._v.append(volts)
        self._i.append(amps)
        self._w.append(watts)
        self._trim()
        self._dirty = True

    def clear_data(self) -> None:
        self._t.clear()
        self._v.clear()
        self._i.clear()
        self._w.clear()
        self._curve_v.setData([], [])
        self._curve_i.setData([], [])
        self._curve_w.setData([], [])

    def set_window(self, seconds: int) -> None:
        self._window_s = seconds
        self._pw.getPlotItem().setXRange(-seconds, 0, padding=0)

    @property
    def state(self) -> dict:
        """Return serialisable state for config persistence."""
        return {
            "window_s": self._window_s,
            "show_v": self._chk_v.isChecked(),
            "show_i": self._chk_i.isChecked(),
            "show_w": self._chk_w.isChecked(),
        }

    def _restore_state(self, window_s: int, show_v: bool, show_i: bool, show_w: bool) -> None:
        # Set combo box without firing _on_window_changed (range already correct from _build_ui)
        self._window_combo.blockSignals(True)
        for i, (_, secs) in enumerate(WINDOW_OPTIONS):
            if secs == window_s:
                self._window_combo.setCurrentIndex(i)
                break
        self._window_combo.blockSignals(False)

        # Restore checkboxes (triggers _update_visibility via toggled signal — that's fine)
        self._chk_v.setChecked(show_v)
        self._chk_i.setChecked(show_i)
        self._chk_w.setChecked(show_w)

    # ── Internal ───────────────────────────────────────────────────────────

    def _redraw_if_dirty(self) -> None:
        if self._dirty:
            self._dirty = False
            self._redraw()

    def _trim(self) -> None:
        if not self._t:
            return
        cutoff = self._t[-1] - self._window_s
        while self._t and self._t[0] < cutoff:
            self._t.popleft()
            self._v.popleft()
            self._i.popleft()
            self._w.popleft()

    def _redraw(self) -> None:
        if not self._t:
            return
        t_arr = np.asarray(self._t)
        # Make x relative to "now" so the right edge is always 0
        x = t_arr - t_arr[-1]

        if self._chk_v.isChecked():
            self._curve_v.setData(x, np.asarray(self._v))
        if self._chk_i.isChecked():
            self._curve_i.setData(x, np.asarray(self._i))
        if self._chk_w.isChecked():
            self._curve_w.setData(x, np.asarray(self._w))

    def _sync_vb(self) -> None:
        pi = self._pw.getPlotItem()
        self._vb2.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2.linkedViewChanged(pi.vb, self._vb2.XAxis)

    def _update_visibility(self) -> None:
        self._curve_v.setVisible(self._chk_v.isChecked())
        self._curve_i.setVisible(self._chk_i.isChecked())
        self._curve_w.setVisible(self._chk_w.isChecked())

    def _on_window_changed(self, idx: int) -> None:
        options = WINDOW_OPTIONS
        if idx < len(options):
            self.set_window(options[idx][1])
        else:
            # Custom
            val, ok = QInputDialog.getInt(
                self,
                "Custom window",
                "Window duration (seconds):",
                value=self._window_s,
                min=10,
                max=86400,
            )
            if ok:
                self.set_window(val)
