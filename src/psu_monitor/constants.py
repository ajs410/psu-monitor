"""All user-facing strings — single source for easy future localization."""

APP_NAME = "PSU Monitor"
APP_VERSION = "0.1.0"
APP_ORG = "PSUMonitor"

# ── Status bar ─────────────────────────────────────────────────────────────
MSG_CONNECTED = "Connected to {port} — {model}  SN: {serial}"
MSG_DISCONNECTED = "Disconnected"
MSG_CONNECTING = "Connecting to {port}…"
MSG_TIMEOUT = "Timeout #{count} on {port}"
MSG_POLLING_PAUSED = "Polling paused after 5 consecutive timeouts — click Reconnect"
MSG_PORT_GONE = "Device disconnected (port disappeared)"
MSG_AUTO_CONNECTED = "Auto-connected to {model} on {port}"
MSG_AUTO_CONNECT_FAILED = "Known device not found on startup — please connect manually"
MSG_MALFORMED_SKIP = "Malformed response skipped: {raw!r}"

# ── IDN ────────────────────────────────────────────────────────────────────
MSG_IDN_OK = "Identified: {idn}"
MSG_IDN_UNRECOGNIZED = "Unrecognized IDN response: {idn!r}"
MSG_IDN_TIMEOUT = "No IDN response on {port}"
MSG_IDN_ERROR = "IDN error on {port}: {err}"

# ── Toolbar ────────────────────────────────────────────────────────────────
LBL_CONNECT = "Connect"
LBL_DISCONNECT = "Disconnect"
LBL_RECONNECT = "Reconnect"
LBL_REFRESH_PORTS = "Refresh"
LBL_IDENTIFY_DEVICE = "Identify Device"
LBL_PORT = "Port:"
LBL_POLL_RATE_MS = "Poll (ms):"
LBL_LINE_ENDING = "Line ending:"
LE_LF = "LF (\\n)"
LE_CRLF = "CRLF (\\r\\n)"
LBL_DETECT_PLUG = "Plug/Unplug Detect"

# ── Gauges ─────────────────────────────────────────────────────────────────
LBL_VOLTAGE = "Voltage"
LBL_CURRENT = "Current"
LBL_POWER = "Power"
UNIT_V = "V"
UNIT_A = "A"
UNIT_W = "W"

# ── Setpoints ──────────────────────────────────────────────────────────────
LBL_V_SETPOINT = "Voltage Setpoint:"
LBL_I_SETPOINT = "Current Setpoint:"
LBL_OVP_LIMIT = "OVP Limit:"
LBL_OCP_LIMIT = "OCP Limit:"

# ── Output toggle ──────────────────────────────────────────────────────────
LBL_OUTPUT_ON = "OUTPUT  ON"
LBL_OUTPUT_OFF = "OUTPUT  OFF"

# ── Fault / mode indicators ────────────────────────────────────────────────
LBL_OVP = "OVP"
LBL_OCP = "OCP"
LBL_OTP = "OTP"
LBL_MODE = "Mode"
MODE_STANDBY = "STANDBY"
MODE_CV = "CV"
MODE_CC = "CC"
MODE_FAULT = "FAULT"
MODE_UNKNOWN = "—"

# ── Soft-bounds warning ────────────────────────────────────────────────────
WARN_CURR_LOW = "⚠  Current {val:.3f} A is below minimum {min:.3f} A"
WARN_CURR_HIGH = "⚠  Current {val:.3f} A is above maximum {max:.3f} A"
LBL_SOFT_BOUNDS = "Soft Current Bounds"
LBL_MIN_AMPS = "Min (A):"
LBL_MAX_AMPS = "Max (A):"
LBL_DEBOUNCE = "Debounce samples:"
LBL_FLUSH_ROWS = "Flush every N rows:"

# ── Chart ──────────────────────────────────────────────────────────────────
LBL_CHART_WINDOW = "Window:"
WINDOW_OPTIONS = [("30 s", 30), ("60 s", 60), ("5 min", 300), ("10 min", 600)]
LBL_CUSTOM_WINDOW = "Custom…"
LBL_SHOW_V = "Voltage"
LBL_SHOW_I = "Current"
LBL_SHOW_W = "Power"

# ── Logging ────────────────────────────────────────────────────────────────
LBL_START_LOG = "Start Logging"
LBL_STOP_LOG = "Stop Logging"
LBL_LOG_FILE = "File:"
LBL_BROWSE = "Browse…"
LBL_LOG_NOTE = "Note:"
FMT_LOG_ROWS = "Rows: {n}"
FMT_LOG_ELAPSED = "Elapsed: {s:.0f} s"
DLG_LOG_FILTER = "CSV / TSV files (*.csv *.tsv);;All files (*)"

# ── Plug/unplug detection dialog ───────────────────────────────────────────
DLG_DETECT_TITLE = "Detect PSU Port"
DLG_UNPLUG_MSG = "Please <b>unplug</b> the PSU USB cable…"
DLG_PLUG_MSG = (
    "Port <b>{port}</b> disappeared.<br>"
    "Please <b>plug in</b> the PSU USB cable…"
)
DLG_DETECT_MISMATCH = (
    "A new port appeared (<b>{new}</b>) but it differs from the one that "
    "disappeared (<b>{old}</b>).\n\nAuto-select the new port anyway?"
)
DLG_DETECT_CANCEL = "Cancel"

# ── IDN dialog ─────────────────────────────────────────────────────────────
DLG_IDN_TITLE = "Identify Device"
DLG_IDN_UNRECOGNIZED = (
    "The IDN response from {port} was unexpected:\n\n"
    "  {idn}\n\n"
    "Connect anyway?"
)
DLG_IDN_SAVE = "Save as known device and connect"
DLG_IDN_CONNECT_ANYWAY = "Connect anyway"
DLG_IDN_CANCEL = "Cancel"

# ── Reconnect prompt ───────────────────────────────────────────────────────
DLG_RECONNECT_TITLE = "Reconnect"
DLG_RECONNECT_MSG = (
    "Polling was paused after 5 consecutive timeouts.\n\n"
    "Check the device connection, then click Reconnect."
)

# ── Errors ─────────────────────────────────────────────────────────────────
ERR_CONNECT = "Cannot connect to {port}: {err}"
ERR_SERIAL = "Serial error: {err}"
