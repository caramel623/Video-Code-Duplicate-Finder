from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from video_finder.config import Config
from video_finder.main_window import MainWindow
from video_finder.theme import apply_theme
from video_finder.workers import clear_temp


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Video Finder")
    app.setOrganizationName("Video Finder")
    apply_theme(app)
    cfg = Config.load()
    window = MainWindow(cfg)
    window.showMaximized()
    code = app.exec()
    clear_temp()
    return code
