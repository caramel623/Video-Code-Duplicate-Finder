import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def test_main_window_builds_with_safe_defaults():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.tabs.count() == 3
        assert window.duplicate_table.columnCount() == 8
        assert not window.settings.enabled
        assert window.recycle_radio.isChecked()
        assert not window.permanent_radio.isChecked()
        assert not window.delete_button.isEnabled()
        assert window.ffmpeg_path_edit.isReadOnly()
    finally:
        window.close()
        app.processEvents()


def test_background_scan_populates_both_result_pages(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    (tmp_path / "A" / "ABC-123.mp4").write_bytes(b"one")
    (tmp_path / "B" / "ABC123.mkv").write_bytes(b"two")
    window = MainWindow()
    window.thumbnail_service.ffmpeg = None
    loop = QEventLoop()
    window.start_scan(tmp_path)
    assert window.scan_worker is not None
    window.scan_worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    app.processEvents()
    try:
        assert window.all_table.rowCount() == 2
        assert window.duplicate_table.rowCount() == 2
        assert window.thumbnail_view.count() == 2
        assert not window._scan_running()

        window.browser_view_button.click()
        assert window.browser_stack.currentIndex() == 1
        assert window.browser_view_button.text() == "切換至詳細資料"

        opened = []
        monkeypatch.setattr("app.main_window.os.startfile", lambda value: opened.append(value))
        window.thumbnail_view.itemDoubleClicked.emit(window.thumbnail_view.item(0))
        assert opened and opened[0].endswith((".mp4", ".mkv"))

        first_folder = Path(window.thumbnail_view.item(0).data(window.thumbnail_view.FOLDER_ROLE))
        window.thumbnail_view.item(0).setCheckState(Qt.Checked)
        assert first_folder in window.selected_paths
    finally:
        window.close()
