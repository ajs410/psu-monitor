"""Persistent application configuration stored as JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

from .constants import APP_NAME, APP_ORG

log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "known_device": None,
    "settings": {
        "last_port": None,
        "poll_interval_ms": 500,
        "line_ending": "LF",
        "chart_window_s": 60,
        "soft_current_min": None,
        "soft_current_max": None,
        "debounce_count": 3,
        "last_log_dir": None,
        "flush_every_n_rows": 1,
        "window_x": None,
        "window_y": None,
        "window_w": 1200,
        "window_h": 750,
    },
}


class AppConfig:
    """Load, access, and persist application configuration."""

    def __init__(self) -> None:
        config_dir = Path(user_config_dir(APP_NAME, APP_ORG))
        config_dir.mkdir(parents=True, exist_ok=True)
        self._path = config_dir / "config.json"
        self._data: dict[str, Any] = json.loads(json.dumps(_DEFAULTS))  # deep copy
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as fh:
                saved = json.load(fh)
            # Merge saved values over defaults so new keys appear automatically
            self._deep_merge(self._data, saved)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load config from %s: %s", self._path, exc)

    def save(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not save config to %s: %s", self._path, exc)

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                AppConfig._deep_merge(base[k], v)
            else:
                base[k] = v

    # ── Known device ───────────────────────────────────────────────────────

    @property
    def known_device(self) -> dict | None:
        return self._data.get("known_device")

    @known_device.setter
    def known_device(self, value: dict | None) -> None:
        self._data["known_device"] = value

    # ── Settings (flat proxy) ──────────────────────────────────────────────

    @property
    def settings(self) -> dict[str, Any]:
        return self._data.setdefault("settings", {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value
