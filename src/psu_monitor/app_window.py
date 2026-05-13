"""Main application window — layout, widget wiring, connection flow."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import serial
from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .constants import (
    APP_NAME,
    DLG_DETECT_CANCEL,
    DLG_DETECT_MISMATCH,
    DLG_DETECT_TITLE,
    DLG_IDN_NOT_OWON,
    DLG_IDN_TITLE,
    DLG_LOG_FILTER,
    DLG_PLUG_MSG,
    DLG_RECONNECT_MSG,
    DLG_RECONNECT_TITLE,
    DLG_UNPLUG_MSG,
    FMT_LOG_ELAPSED,
    FMT_LOG_ROWS,
    LBL_BROWSE,
    LBL_CONNECT,
    LBL_CURRENT,
    LBL_DETECT_PLUG,
    LBL_DISCONNECT,
    LBL_I_SETPOINT,
    LBL_IDENTIFY_DEVICE,
    LBL_LINE_ENDING,
    LBL_LOG_FILE,
    LBL_LOG_NOTE,
    LBL_OCP_LIMIT,
    LBL_OUTPUT_OFF,
    LBL_OUTPUT_ON,
    LBL_OVP_LIMIT,
    LBL_POLL_RATE_MS,
    LBL_PORT,
    LBL_POWER,
    LBL_REFRESH_PORTS,
    LBL_START_LOG,
    LBL_STOP_LOG,
    LBL_V_SETPOINT,
    LBL_VOLTAGE,
    LE_CRLF,
    LE_LF,
    MSG_AUTO_CONNECTED,
    MSG_AUTO_CONNECT_FAILED,
    MSG_CONNECTED,
    MSG_DISCONNECTED,
    MSG_POLLING_PAUSED,
    UNIT_A,
    UNIT_V,
    UNIT_W,
    WARN_CURR_HIGH,
    WARN_CURR_LOW,
)
from .data_logger import DataLogger
from .port_detector import PortInfo, list_ports, port_set
from .psu_driver import PSUDriver
from .serial_worker import SerialWorker
from .widgets.gauges import NumericGauge
from .widgets.plot_widget import PSUPlotWidget
from .widgets.settings_panel import SettingsPanel
from .widgets.warning_panel import WarningPanel

log = logging.getLogger(__name__)

# Maximum voltage/current for the OWON P4305 (conservative upper bounds for spinboxes)
MAX_VOLTAGE = 43.0
MAX_CURRENT = 5.0


# ── Plug/Unplug detection dialog ───────────────────────────────────────────────


class PlugUnplugDialog(QDialog):
    """Guides the user through unplugging then re-plugging the PSU to identify its port."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(DLG_DETECT_TITLE)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._phase = "unplug"
        self._snapshot = port_set()
        self._gone_port: str | None = None
        self.detected_port: str | None = None

        self._msg = QLabel(DLG_UNPLUG_MSG)
        self._msg.setTextFormat(Qt.TextFormat.RichText)
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #888888; font-size: 10px;")

        cancel_btn = QPushButton(DLG_DETECT_CANCEL)
        cancel_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.addWidget(self._msg)
        layout.addWidget(self._status)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)

    def _tick(self) -> None:
        current = port_set()
        if self._phase == "unplug":
            gone = self._snapshot - current
            if gone:
                self._gone_port = gone.pop()
                self._snapshot = current
                self._phase = "plug"
                self._msg.setText(DLG_PLUG_MSG.format(port=self._gone_port))
        elif self._phase == "plug":
            appeared = current - self._snapshot
            if appeared:
                new_port = appeared.pop()
                self._timer.stop()
                if new_port == self._gone_port:
                    self.detected_port = new_port
                    self.accept()
                else:
                    ans = QMessageBox.question(
                        self,
                        DLG_DETECT_TITLE,
                        DLG_DETECT_MISMATCH.format(new=new_port, old=self._gone_port),
                    )
                    if ans == QMessageBox.StandardButton.Yes:
                        self.detected_port = new_port
                        self.accept()
                    else:
                        self.reject()


# ── IDN probe thread ──────────────────────────────────────────────────────────


class IDNProbe(threading.Thread):
    """One-shot thread that sends *IDN? and returns the result via callback."""

    def __init__(self, port: str, baud: int = 115200, le: str = "\n", callback=None) -> None:
        super().__init__(daemon=True)
        self._port = port
        self._baud = baud
        self._le = le
        self._callback = callback

    def run(self) -> None:
        try:
            ser = serial.Serial(
                port=self._port, baudrate=self._baud, timeout=1.0, write_timeout=1.0
            )
            driver = PSUDriver(ser, line_ending=self._le)
            idn = driver.idn()
            driver.close()
            if self._callback:
                self._callback(idn, None)
        except Exception as exc:  # noqa: BLE001
            if self._callback:
                self._callback(None, str(exc))


# ── Main window ───────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._logger = DataLogger()
        self._worker: SerialWorker | None = None
        self._is_connected = False
        self._current_port: str | None = None

        # Last known measurements for logging/greying
        self._last_v = 0.0
        self._last_a = 0.0
        self._last_w = 0.0
        self._last_status: dict = {}
        self._last_v_set = 0.0
        self._last_i_set = 0.0
        self._last_v_lim = 0.0
        self._last_i_lim = 0.0
        self._last_output_on = False

        # Soft-bounds tracking
        self._soft_warn_counter = 0
        self._soft_warn_active = False

        # Timeout counter
        self._timeout_count = 0

        self._build_ui()
        self._build_worker()
        self._refresh_ports()
        self._restore_geometry()
        self._try_auto_connect()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)

        # Status bar
        self._status_bar: QStatusBar = self.statusBar()
        self._timeout_lbl = QLabel("Timeouts: 0")
        self._status_bar.addPermanentWidget(self._timeout_lbl)
        self._status_bar.showMessage(MSG_DISCONNECTED)

        self._build_toolbar()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Left + Right splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        left = self._build_left_panel()
        left.setMinimumWidth(290)
        left.setMaximumWidth(350)
        splitter.addWidget(left)
        splitter.setStretchFactor(0, 0)

        self._plot = PSUPlotWidget(
            window_s=self._config.get("chart_window_s", 60),
            show_v=self._config.get("chart_show_v", True),
            show_i=self._config.get("chart_show_i", True),
            show_w=self._config.get("chart_show_w", True),
        )
        splitter.addWidget(self._plot)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._build_log_panel())

    def _build_toolbar(self) -> None:
        tb: QToolBar = self.addToolBar("Connection")
        tb.setMovable(False)
        tb.setFloatable(False)

        tb.addWidget(QLabel(LBL_PORT))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(200)
        tb.addWidget(self._port_combo)

        refresh_btn = QToolButton()
        refresh_btn.setText(LBL_REFRESH_PORTS)
        refresh_btn.clicked.connect(self._refresh_ports)
        tb.addWidget(refresh_btn)

        self._connect_btn = QPushButton(LBL_CONNECT)
        self._connect_btn.setCheckable(False)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        tb.addWidget(self._connect_btn)

        detect_btn = QToolButton()
        detect_btn.setText(LBL_DETECT_PLUG)
        detect_btn.clicked.connect(self._on_detect_clicked)
        tb.addWidget(detect_btn)

        identify_btn = QToolButton()
        identify_btn.setText(LBL_IDENTIFY_DEVICE)
        identify_btn.clicked.connect(self._on_identify_clicked)
        tb.addWidget(identify_btn)

        tb.addSeparator()

        tb.addWidget(QLabel(LBL_POLL_RATE_MS))
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(50, 5000)
        self._poll_spin.setSingleStep(50)
        self._poll_spin.setSuffix(" ms")
        self._poll_spin.setValue(self._config.get("poll_interval_ms", 500))
        self._poll_spin.valueChanged.connect(self._on_poll_rate_changed)
        tb.addWidget(self._poll_spin)

        tb.addWidget(QLabel(LBL_LINE_ENDING))
        self._le_combo = QComboBox()
        self._le_combo.addItems([LE_LF, LE_CRLF])
        le = self._config.get("line_ending", "LF")
        self._le_combo.setCurrentIndex(0 if le == "LF" else 1)
        self._le_combo.currentIndexChanged.connect(self._on_le_changed)
        tb.addWidget(self._le_combo)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Gauges
        meas_group = QGroupBox("Measurements")
        g = QVBoxLayout(meas_group)
        g.setSpacing(4)
        self._v_gauge = NumericGauge(LBL_VOLTAGE, UNIT_V)
        self._a_gauge = NumericGauge(LBL_CURRENT, UNIT_A)
        self._w_gauge = NumericGauge(LBL_POWER, UNIT_W)
        g.addWidget(self._v_gauge)
        g.addWidget(self._a_gauge)
        g.addWidget(self._w_gauge)
        layout.addWidget(meas_group)

        # Setpoints
        sp_group = QGroupBox("Setpoints")
        f = QFormLayout(sp_group)
        f.setContentsMargins(8, 8, 8, 8)

        self._v_set_spin = self._make_dspin(0.0, MAX_VOLTAGE, " V", self._on_v_set)
        self._i_set_spin = self._make_dspin(0.0, MAX_CURRENT, " A", self._on_i_set)
        self._ovp_spin = self._make_dspin(0.0, MAX_VOLTAGE, " V", self._on_ovp)
        self._ocp_spin = self._make_dspin(0.0, MAX_CURRENT, " A", self._on_ocp)

        f.addRow(LBL_V_SETPOINT, self._v_set_spin)
        f.addRow(LBL_I_SETPOINT, self._i_set_spin)
        f.addRow(LBL_OVP_LIMIT, self._ovp_spin)
        f.addRow(LBL_OCP_LIMIT, self._ocp_spin)
        layout.addWidget(sp_group)

        # Output toggle
        self._output_btn = QPushButton(LBL_OUTPUT_OFF)
        self._output_btn.setCheckable(True)
        self._output_btn.setFixedHeight(56)
        font = self._output_btn.font()
        font.setPointSize(13)
        font.setBold(True)
        self._output_btn.setFont(font)
        self._output_btn.clicked.connect(self._on_output_toggle)
        self._set_output_btn_style(False)
        layout.addWidget(self._output_btn)

        # Fault / mode LEDs
        self._warn_panel = WarningPanel()
        layout.addWidget(self._warn_panel)

        # Soft-bounds settings
        self._settings_panel = SettingsPanel(self._config)
        self._settings_panel.bounds_changed.connect(self._on_bounds_changed)
        layout.addWidget(self._settings_panel)

        layout.addStretch()
        return panel

    def _build_log_panel(self) -> QGroupBox:
        group = QGroupBox("Data Logging")
        h = QHBoxLayout(group)
        h.setSpacing(8)

        self._log_btn = QPushButton(LBL_START_LOG)
        self._log_btn.setFixedWidth(110)
        self._log_btn.clicked.connect(self._on_log_toggle)
        h.addWidget(self._log_btn)

        h.addWidget(QLabel(LBL_LOG_FILE))
        self._log_path = QLineEdit()
        self._log_path.setReadOnly(True)
        self._log_path.setPlaceholderText("No file selected")
        h.addWidget(self._log_path, stretch=1)

        browse_btn = QPushButton(LBL_BROWSE)
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._on_browse_log)
        h.addWidget(browse_btn)

        h.addWidget(QLabel(LBL_LOG_NOTE))
        self._log_note = QLineEdit()
        self._log_note.setPlaceholderText("Optional session note")
        self._log_note.setMaximumWidth(180)
        h.addWidget(self._log_note)

        self._log_rows_lbl = QLabel(FMT_LOG_ROWS.format(n=0))
        self._log_rows_lbl.setMinimumWidth(70)
        h.addWidget(self._log_rows_lbl)

        self._log_elapsed_lbl = QLabel(FMT_LOG_ELAPSED.format(s=0))
        self._log_elapsed_lbl.setMinimumWidth(80)
        h.addWidget(self._log_elapsed_lbl)

        # Update logging stats every second
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._update_log_stats)
        self._log_timer.start(1000)

        return group

    # ── Worker lifecycle ───────────────────────────────────────────────────

    def _build_worker(self) -> None:
        self._worker = SerialWorker(self)
        self._worker.measurements_ready.connect(self._on_measurements)
        self._worker.setpoints_ready.connect(self._on_setpoints)
        self._worker.connection_status_changed.connect(self._on_connection_changed)
        self._worker.idn_ready.connect(self._on_idn_ready)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.timeout_count_changed.connect(self._on_timeout_count)
        self._worker.reconnect_required.connect(self._on_reconnect_required)
        self._worker.start()
        # Push the persisted poll rate immediately — the worker starts with a 500 ms default
        self._worker.send_set_poll_interval(self._poll_spin.value())

    # ── Port helpers ───────────────────────────────────────────────────────

    def _refresh_ports(self) -> None:
        self._port_combo.blockSignals(True)
        prev = self._port_combo.currentData()
        self._port_combo.clear()
        for p in list_ports():
            self._port_combo.addItem(p.display_label(), userData=p.port)
        # Restore previous selection if still present
        for i in range(self._port_combo.count()):
            if self._port_combo.itemData(i) == prev:
                self._port_combo.setCurrentIndex(i)
                break
        self._port_combo.blockSignals(False)

    def _selected_port(self) -> str | None:
        return self._port_combo.currentData()

    def _select_port(self, port: str) -> None:
        for i in range(self._port_combo.count()):
            if self._port_combo.itemData(i) == port:
                self._port_combo.setCurrentIndex(i)
                return
        # Port not in list — add and select it
        self._port_combo.addItem(port, userData=port)
        self._port_combo.setCurrentIndex(self._port_combo.count() - 1)

    def _current_line_ending(self) -> str:
        return "\n" if self._le_combo.currentIndex() == 0 else "\r\n"

    # ── Connection flow ────────────────────────────────────────────────────

    def _on_connect_clicked(self) -> None:
        if self._is_connected:
            self._worker.request_disconnect()
        else:
            port = self._selected_port()
            if not port:
                QMessageBox.warning(self, "No port", "Please select a serial port first.")
                return
            self._do_connect(port)

    def _do_connect(self, port: str) -> None:
        le = self._current_line_ending()
        baud = 115200
        self._status_bar.showMessage(f"Connecting to {port}…")
        self._worker.request_connect(port, baud, le)
        self._config.set("last_port", port)

    def _on_detect_clicked(self) -> None:
        dlg = PlugUnplugDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.detected_port:
            self._refresh_ports()
            self._select_port(dlg.detected_port)
            self._status_bar.showMessage(f"Detected port: {dlg.detected_port}")

    def _on_identify_clicked(self) -> None:
        port = self._selected_port()
        if not port:
            QMessageBox.warning(self, "No port", "Please select a serial port first.")
            return
        le = self._current_line_ending()
        self._status_bar.showMessage(f"Identifying device on {port}…")

        def callback(idn: str | None, err: str | None) -> None:
            # Deliver result back to the main thread via a singleshot timer
            QTimer.singleShot(0, lambda: self._idn_result(port, idn, err))

        IDNProbe(port, le=le, callback=callback).start()

    def _idn_result(self, port: str, idn: str | None, err: str | None) -> None:
        if err:
            QMessageBox.warning(self, DLG_IDN_TITLE, f"Error on {port}: {err}")
            self._status_bar.showMessage(f"IDN failed: {err}")
            return

        if not idn:
            QMessageBox.warning(self, DLG_IDN_TITLE, f"No response from {port}")
            return

        is_owon = idn.upper().startswith("OWON")
        self._status_bar.showMessage(f"IDN: {idn}")

        if is_owon:
            # Parse OWON,<model>,<serial>,FV:X.XX.XX
            parts = idn.split(",")
            model = parts[1].strip() if len(parts) > 1 else "?"
            serial_num = parts[2].strip() if len(parts) > 2 else "?"

            # Save known device to config
            self._config.known_device = {
                "model": model,
                "idn_serial_number": serial_num,
                "last_port": port,
            }
            self._config.save()

            ans = QMessageBox.information(
                self,
                DLG_IDN_TITLE,
                f"Identified: {idn}\n\nDevice saved as known device.\nConnect now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                self._do_connect(port)
        else:
            ans = QMessageBox.warning(
                self,
                DLG_IDN_TITLE,
                DLG_IDN_NOT_OWON.format(port=port, idn=idn),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if ans == QMessageBox.StandardButton.Yes:
                self._do_connect(port)

    def _try_auto_connect(self) -> None:
        dev = self._config.known_device
        last_port = (dev or {}).get("last_port") or self._config.get("last_port")
        if not last_port:
            return

        if not dev:
            # No IDN record yet — just reconnect to the last port directly.
            # The IDN query that fires after connect will populate known_device.
            self._status_bar.showMessage(f"Auto-connecting to last port {last_port}…")
            QTimer.singleShot(
                0,
                lambda: (self._select_port(last_port), self._do_connect(last_port)),
            )
            return

        # Known device: validate with IDN before connecting
        serial_num = dev.get("idn_serial_number", "")
        model = dev.get("model", "?")
        self._status_bar.showMessage(f"Looking for {model} on {last_port}…")

        def probe(ports_to_try: list[str]) -> None:
            for p in ports_to_try:
                try:
                    probe_ser = serial.Serial(
                        port=p, baudrate=115200, timeout=1.0, write_timeout=1.0
                    )
                    d = PSUDriver(probe_ser, line_ending=self._current_line_ending())
                    idn = d.idn()
                    d.close()
                    idn_match = idn.upper().startswith("OWON") and (
                        not serial_num or serial_num in idn
                    )
                    if idn_match:
                        QTimer.singleShot(
                            0,
                            lambda port=p, m=model: (
                                self._select_port(port),
                                self._do_connect(port),
                                self._status_bar.showMessage(
                                    MSG_AUTO_CONNECTED.format(model=m, port=port)
                                ),
                            ),
                        )
                        return
                except Exception:  # noqa: BLE001
                    continue
            QTimer.singleShot(
                0, lambda: self._status_bar.showMessage(MSG_AUTO_CONNECT_FAILED)
            )

        all_ports = [pi.port for pi in list_ports()]
        ordered = [last_port] + [p for p in all_ports if p != last_port]
        threading.Thread(target=probe, args=(ordered,), daemon=True).start()

    # ── Worker slots ───────────────────────────────────────────────────────

    @Slot(float, float, float, dict)
    def _on_measurements(self, volts: float, amps: float, watts: float, status: dict) -> None:
        self._last_v = volts
        self._last_a = amps
        self._last_w = watts
        self._last_status = status

        mode = status.get("mode", 0)
        ovp = status.get("ovp_fault", False)
        ocp = status.get("ocp_fault", False)
        otp = status.get("otp_fault", False)

        # Determine gauge state
        v_state = "fault" if ovp else ("warn" if volts > self._last_v_lim * 0.9 > 0 else "normal")
        a_state = "fault" if ocp else ("warn" if amps > self._last_i_lim * 0.9 > 0 else "normal")
        w_state = "fault" if (ovp or ocp) else "normal"

        self._v_gauge.set_value(volts, v_state)
        self._a_gauge.set_value(amps, a_state)
        self._w_gauge.set_value(watts, w_state)
        self._warn_panel.update_faults(ovp, ocp, otp, mode)
        self._plot.append(volts, amps, watts)

        # Derive output state from mode every poll — more reliable than OUTP? every 10th poll
        # mode 0=standby(off), 1=CV(on), 2=CC(on), 3=fault(leave unchanged)
        if mode in (1, 2):
            self._update_output_btn(True)
        elif mode == 0:
            self._update_output_btn(False)

        # Soft-bounds check
        log_note = self._check_soft_bounds(amps, self._last_output_on)

        # Data logging
        if self._logger.is_active:
            self._logger.log(
                volts=volts,
                amps=amps,
                watts=watts,
                v_set=self._last_v_set,
                i_set=self._last_i_set,
                output_on=self._last_output_on,
                mode=mode,
                ovp=ovp,
                ocp=ocp,
                otp=otp,
                note=log_note,
            )

    @Slot(float, float, float, float, bool)
    def _on_setpoints(self, v_set: float, i_set: float, v_lim: float, i_lim: float, output_on: bool) -> None:
        self._last_v_set = v_set
        self._last_i_set = i_set
        self._last_v_lim = v_lim
        self._last_i_lim = i_lim
        self._last_output_on = output_on

        # Update spinboxes without triggering send-commands
        for spin, val in [
            (self._v_set_spin, v_set),
            (self._i_set_spin, i_set),
            (self._ovp_spin, v_lim),
            (self._ocp_spin, i_lim),
        ]:
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)

        self._output_btn.blockSignals(True)
        self._output_btn.setChecked(output_on)
        self._output_btn.blockSignals(False)
        self._set_output_btn_style(output_on)

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, message: str) -> None:
        self._is_connected = connected
        if connected:
            self._current_port = message  # message contains port name on connect
            self._connect_btn.setText(LBL_DISCONNECT)
            dev = self._config.known_device
            model = dev.get("model", "?") if dev else "?"
            serial_num = dev.get("idn_serial_number", "?") if dev else "?"
            self._status_bar.showMessage(
                MSG_CONNECTED.format(port=message, model=model, serial=serial_num)
            )
            self._timeout_count = 0
            self._timeout_lbl.setText("Timeouts: 0")
        else:
            self._connect_btn.setText(LBL_CONNECT)
            self._status_bar.showMessage(message or MSG_DISCONNECTED)
            self._v_gauge.clear()
            self._a_gauge.clear()
            self._w_gauge.clear()
            self._warn_panel.clear_faults()
            self._warn_panel.clear_soft_warning()

    @Slot(str)
    def _on_idn_ready(self, idn: str) -> None:
        parts = idn.split(",")
        model = parts[1].strip() if len(parts) > 1 else "?"
        serial_num = parts[2].strip() if len(parts) > 2 else "?"
        self._status_bar.showMessage(
            MSG_CONNECTED.format(port=self._current_port or "?", model=model, serial=serial_num)
        )
        # Auto-save known device on first successful IDN
        if idn.upper().startswith("OWON") and not self._config.known_device:
            self._config.known_device = {
                "model": model,
                "idn_serial_number": serial_num,
                "last_port": self._current_port,
            }
            self._config.save()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        self._status_bar.showMessage(message)

    @Slot(int)
    def _on_timeout_count(self, count: int) -> None:
        self._timeout_count = count
        self._timeout_lbl.setText(f"Timeouts: {count}")
        if count >= 5:
            self._status_bar.showMessage(MSG_POLLING_PAUSED)

    @Slot()
    def _on_reconnect_required(self) -> None:
        ans = QMessageBox.question(
            self,
            DLG_RECONNECT_TITLE,
            DLG_RECONNECT_MSG,
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Retry:
            self._worker.request_reconnect()
            self._status_bar.showMessage("Resuming polling…")

    # ── Control slots (setpoints) ──────────────────────────────────────────

    def _on_v_set(self) -> None:
        if self._is_connected:
            self._worker.send_set_voltage(self._v_set_spin.value())

    def _on_i_set(self) -> None:
        if self._is_connected:
            self._worker.send_set_current(self._i_set_spin.value())

    def _on_ovp(self) -> None:
        if self._is_connected:
            self._worker.send_set_volt_limit(self._ovp_spin.value())

    def _on_ocp(self) -> None:
        if self._is_connected:
            self._worker.send_set_curr_limit(self._ocp_spin.value())

    def _on_output_toggle(self, checked: bool) -> None:
        self._set_output_btn_style(checked)
        if self._is_connected:
            self._worker.send_set_output(checked)

    # ── Toolbar control slots ──────────────────────────────────────────────

    def _on_poll_rate_changed(self, ms: int) -> None:
        self._config.set("poll_interval_ms", ms)
        if self._worker:
            self._worker.send_set_poll_interval(ms)

    def _on_le_changed(self, idx: int) -> None:
        key = "LF" if idx == 0 else "CRLF"
        self._config.set("line_ending", key)
        le = "\n" if idx == 0 else "\r\n"
        if self._worker:
            self._worker.send_set_line_ending(le)

    # ── Soft-bounds logic ──────────────────────────────────────────────────

    def _check_soft_bounds(self, amps: float, output_on: bool) -> str:
        """Update soft-bounds warning. Returns a log note string if an event fires."""
        if not output_on:
            self._soft_warn_counter = 0
            self._soft_warn_active = False
            self._warn_panel.clear_soft_warning()
            return ""

        min_a = self._config.get("soft_current_min")
        max_a = self._config.get("soft_current_max")
        debounce = self._config.get("debounce_count", 3)

        if min_a is None and max_a is None:
            return ""

        out_of_bounds = False
        message = ""
        if min_a is not None and amps < min_a:
            out_of_bounds = True
            message = WARN_CURR_LOW.format(val=amps, min=min_a)
        elif max_a is not None and amps > max_a:
            out_of_bounds = True
            message = WARN_CURR_HIGH.format(val=amps, max=max_a)

        if out_of_bounds:
            self._soft_warn_counter += 1
            if self._soft_warn_counter >= debounce:
                self._warn_panel.show_soft_warning(message)
                if not self._soft_warn_active:
                    self._soft_warn_active = True
                    return message  # Log note only on first trigger
        else:
            if self._soft_warn_counter > 0:
                self._soft_warn_counter = 0
                self._soft_warn_active = False
                self._warn_panel.clear_soft_warning()

        return ""

    # ── Settings panel slot ────────────────────────────────────────────────

    @Slot(object, object, int)
    def _on_bounds_changed(self, min_a, max_a, debounce: int) -> None:
        # Reset warning state when bounds change
        self._soft_warn_counter = 0
        self._soft_warn_active = False
        self._warn_panel.clear_soft_warning()

    # ── Logging ────────────────────────────────────────────────────────────

    def _on_log_toggle(self) -> None:
        if self._logger.is_active:
            self._logger.stop()
            self._log_btn.setText(LBL_START_LOG)
            self._log_btn.setStyleSheet("")
        else:
            path = self._log_path.text().strip()
            if not path:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save log file", str(self._default_log_dir()), DLG_LOG_FILTER
                )
                if not path:
                    return
                self._log_path.setText(path)
            flush = self._settings_panel.flush_every
            self._logger.start(
                Path(path), session_note=self._log_note.text().strip(), flush_every=flush
            )
            self._log_btn.setText(LBL_STOP_LOG)
            self._log_btn.setStyleSheet("QPushButton { background-color: #8B0000; color: white; }")
            self._config.set("last_log_dir", str(Path(path).parent))

    def _on_browse_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save log file", str(self._default_log_dir()), DLG_LOG_FILTER
        )
        if path:
            self._log_path.setText(path)

    def _default_log_dir(self) -> Path:
        saved = self._config.get("last_log_dir")
        return Path(saved) if saved else Path.home()

    def _update_log_stats(self) -> None:
        if self._logger.is_active:
            self._log_rows_lbl.setText(FMT_LOG_ROWS.format(n=self._logger.row_count))
            self._log_elapsed_lbl.setText(
                FMT_LOG_ELAPSED.format(s=self._logger.elapsed_seconds)
            )

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_dspin(
        minimum: float, maximum: float, suffix: str, callback
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSuffix(suffix)
        spin.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        spin.editingFinished.connect(callback)
        return spin

    def _update_output_btn(self, on: bool) -> None:
        """Update button checked state + style without emitting a command."""
        if self._last_output_on == on:
            return
        self._last_output_on = on
        self._output_btn.blockSignals(True)
        self._output_btn.setChecked(on)
        self._output_btn.blockSignals(False)
        self._set_output_btn_style(on)

    def _set_output_btn_style(self, on: bool) -> None:
        self._output_btn.setText(LBL_OUTPUT_ON if on else LBL_OUTPUT_OFF)
        if on:
            self._output_btn.setStyleSheet(
                "QPushButton { background-color: #006600; color: #ffffff; border-radius: 4px; }"
                "QPushButton:hover { background-color: #009900; }"
            )
        else:
            self._output_btn.setStyleSheet(
                "QPushButton { background-color: #660000; color: #ffffff; border-radius: 4px; }"
                "QPushButton:hover { background-color: #990000; }"
            )

    # ── Geometry persistence ───────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        x = self._config.get("window_x")
        y = self._config.get("window_y")
        w = self._config.get("window_w", 1200)
        h = self._config.get("window_h", 750)
        self.resize(w, h)
        if x is not None and y is not None:
            self.move(x, y)

    def _save_geometry(self) -> None:
        geom = self.geometry()
        self._config.set("window_x", geom.x())
        self._config.set("window_y", geom.y())
        self._config.set("window_w", geom.width())
        self._config.set("window_h", geom.height())

    # ── Qt lifecycle ───────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._logger.stop()
        self._save_geometry()
        self._config.set("poll_interval_ms", self._poll_spin.value())
        chart_state = self._plot.state
        self._config.set("chart_window_s", chart_state["window_s"])
        self._config.set("chart_show_v", chart_state["show_v"])
        self._config.set("chart_show_i", chart_state["show_i"])
        self._config.set("chart_show_w", chart_state["show_w"])
        self._config.save()
        if self._worker:
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(event)
