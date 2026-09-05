from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, QObject, QRunnable, QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider, QListView, QListWidget, QListWidgetItem

from .models import VideoItem
from .thumbnail_service import ThumbnailService


class _ThumbnailSignals(QObject):
    ready = Signal(str, str)


class _ThumbnailTask(QRunnable):
    def __init__(self, video_path: Path, service: ThumbnailService, signals: _ThumbnailSignals):
        super().__init__()
        self.video_path = video_path
        self.service = service
        self.signals = signals

    @Slot()
    def run(self) -> None:
        result = self.service.generate(self.video_path)
        self.signals.ready.emit(str(self.video_path), str(result) if result else "")


class VideoThumbnailView(QListWidget):
    folder_selection_changed = Signal(object, bool)
    video_activated = Signal(object)

    VIDEO_ROLE = Qt.UserRole
    FOLDER_ROLE = Qt.UserRole + 1

    def __init__(self, service: ThumbnailService, parent=None):
        super().__init__(parent)
        self.service = service
        self._signals = _ThumbnailSignals(self)
        self._signals.ready.connect(self._thumbnail_ready)
        self._pool = QThreadPool.globalInstance()
        self._items_by_video: dict[Path, QListWidgetItem] = {}
        self._loading: set[Path] = set()
        self._placeholder_provider = QFileIconProvider()
        self._syncing = False

        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(240, 135))
        self.setGridSize(QSize(285, 205))
        self.setSpacing(8)
        self.setSelectionMode(QListView.SingleSelection)
        self.setWordWrap(True)
        self.itemChanged.connect(self._item_changed)
        self.itemDoubleClicked.connect(self._item_double_clicked)

    def set_videos(self, items: list[VideoItem], selected_folders: set[Path]) -> None:
        self._syncing = True
        self.clear()
        self._items_by_video.clear()
        for video in sorted(items, key=lambda item: ((item.code or "~"), str(item.path).lower())):
            label = f"{video.code or '未辨識'}\n{video.path.name}"
            item = QListWidgetItem(label)
            item.setData(self.VIDEO_ROLE, str(video.path))
            item.setData(self.FOLDER_ROLE, str(video.parent))
            item.setToolTip(str(video.path))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if video.parent in selected_folders else Qt.Unchecked)
            cached = self.service.cached_path(video.path)
            if cached.is_file():
                item.setIcon(QIcon(str(cached)))
            else:
                item.setIcon(self._placeholder_provider.icon(QFileInfo(str(video.path))))
            self.addItem(item)
            self._items_by_video[video.path] = item
        self._syncing = False

    def ensure_thumbnails(self) -> None:
        if not self.service.ffmpeg:
            return
        for video_path, item in self._items_by_video.items():
            cached = self.service.cached_path(video_path)
            if cached.is_file():
                item.setIcon(QIcon(str(cached)))
            elif video_path not in self._loading:
                self._loading.add(video_path)
                self._pool.start(_ThumbnailTask(video_path, self.service, self._signals))

    def sync_folder(self, folder: Path, checked: bool) -> None:
        self._syncing = True
        for index in range(self.count()):
            item = self.item(index)
            if Path(item.data(self.FOLDER_ROLE)) == folder:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._syncing = False

    @Slot(str, str)
    def _thumbnail_ready(self, video_value: str, thumbnail_value: str) -> None:
        video_path = Path(video_value)
        self._loading.discard(video_path)
        item = self._items_by_video.get(video_path)
        if item and thumbnail_value:
            item.setIcon(QIcon(thumbnail_value))

    def _item_changed(self, item: QListWidgetItem) -> None:
        if not self._syncing:
            folder = Path(item.data(self.FOLDER_ROLE))
            self.folder_selection_changed.emit(folder, item.checkState() == Qt.Checked)

    def _item_double_clicked(self, item: QListWidgetItem) -> None:
        self.video_activated.emit(Path(item.data(self.VIDEO_ROLE)))
