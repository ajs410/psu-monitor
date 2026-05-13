"""Entry point — creates the QApplication and launches the main window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from .app_window import MainWindow
from .config import AppConfig
from .constants import APP_NAME, APP_ORG, APP_VERSION


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORG)

    config = AppConfig()
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
