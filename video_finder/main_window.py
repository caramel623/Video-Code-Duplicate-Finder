from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import Config
from .ffmpeg_backend import ffmpeg_version, find_ffmpeg
from .scanner import VideoFile, VideoGroup, group_files
from .settings_dialog import SettingsDialog
from .util import human_size, open_folder, open_with_default, short_path
from .workers import ScanWorker, ThumbWorker, thumb_cache_path

CARD_W = 168
CARD_H = 94
COLS = 2


def make_placeholder(width: int, height: int, text: str) -> QPixmap:
    pm = QPixmap(width, height)
    pm.fill(QColor("#2a2f38"))
    painter = QPainter(pm)
    painter.setPen(QColor("#9aa2ad"))
    font = QFont()
    font.setPointSize(10)
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignCenter, text)
    painter.end()
    return pm


class ThumbCard(QWidget):
    """One video file card: thumbnail, name, size and play/folder buttons."""

    opened = Signal(str)
    folder_requested = Signal(str)

    def __init__(self, path: str, size: int, parent=None):
        super().__init__(parent)
        self.path = path
        self.size = size
        self.setFixedWidth(CARD_W)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.img = QLabel()
        self.img.setFixedSize(CARD_W - 16, CARD_H)
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setStyleSheet("background:#2a2f38; border-radius:6px; border:1px solid #343a44;")
        self.img.setPixmap(make_placeholder(CARD_W - 16, CARD_H, "讀取截圖中"))

        name = os.path.basename(path)
        self.name_label = QLabel(name)
        self.name_label.setWordWrap(False)
        self.name_label.setToolTip(path)
        self.size_label = QLabel(human_size(size))
        self.size_label.setObjectName("Muted")

        row = QHBoxLayout()
        row.setSpacing(6)
        play = QPushButton("播放")
        play.setProperty("variant", "secondary")
        play.setFixedHeight(28)
        play.clicked.connect(lambda: self.opened.emit(self.path))
        folder = QPushButton("資料夾")
        folder.setProperty("variant", "secondary")
        folder.setFixedHeight(28)
        folder.clicked.connect(lambda: self.folder_requested.emit(self.path))
        row.addWidget(play, 1)
        row.addWidget(folder, 1)

        layout.addWidget(self.img)
        layout.addWidget(self.name_label)
        layout.addWidget(self.size_label)
        layout.addLayout(row)

    def set_image(self, pm: QPixmap):
        self.img.setPixmap(pm.scaled(
            self.img.width(), self.img.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mouseDoubleClickEvent(self, event):
        self.opened.emit(self.path)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_play = QAction("用預設播放器開啟", menu)
        act_play.triggered.connect(lambda: self.opened.emit(self.path))
        act_folder = QAction("開啟所在資料夾", menu)
        act_folder.triggered.connect(lambda: self.folder_requested.emit(self.path))
        menu.addAction(act_play)
        menu.addAction(act_folder)
        menu.exec(event.globalPos())


class MainWindow(QMainWindow):
    """Main window: folder picker, scan, duplicate tree, detail cards."""

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.files: list[VideoFile] = []
        self.groups: list[VideoGroup] = []
        self.visible_groups: list[VideoGroup] = []
        self.scan_worker = None
        self.thumb_worker = None
        self.cards: dict[str, ThumbCard] = {}

        self.setWindowTitle(f"Video Finder {__version__} — 影片重複檢查")
        self.resize(1100, 680)
        self.setMinimumSize(860, 540)
        self._build_ui()
        self._update_ffmpeg_status()
        if cfg.last_folder and os.path.isdir(cfg.last_folder):
            self.root_edit.setText(cfg.last_folder)

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 8)
        outer.setSpacing(10)

        header = QFrame()
        header.setObjectName("HeaderBar")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(10, 8, 10, 8)
        hrow.setSpacing(8)
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("選擇影片資料夾(含子資料夾)")
        self.browse_btn = QPushButton("瀏覽")
        self.browse_btn.setProperty("variant", "secondary")
        self.browse_btn.clicked.connect(self._browse_folder)
        self.scan_btn = QPushButton("掃描")
        self.scan_btn.clicked.connect(self.start_scan)
        hrow.addWidget(self.root_edit, 1)
        hrow.addWidget(self.browse_btn)
        hrow.addWidget(self.scan_btn)
        outer.addWidget(header)

        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜尋片名…")
        self.search_edit.textChanged.connect(self._apply_filter)
        self.dups_chk = QCheckBox("只看重複")
        self.dups_chk.setChecked(self.cfg.show_duplicates_only)
        self.dups_chk.toggled.connect(self._on_dups_toggled)
        self.settings_btn = QPushButton("⚙ 設定")
        self.settings_btn.setProperty("variant", "secondary")
        self.settings_btn.clicked.connect(self._open_settings)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setAlignment(Qt.AlignVCenter)
        frow.addWidget(self.search_edit, 1)
        frow.addWidget(self.dups_chk)
        frow.addWidget(self.settings_btn)
        frow.addStretch(1)
        frow.addWidget(self.count_label)
        outer.addLayout(frow)

        splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "片名", "檔案數", "總大小", "位置"])
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(4, QHeaderView.Interactive)
        for col in (0, 2, 3):
            self.tree.header().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_menu)

        splitter.addWidget(self.tree)
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setCollapsible(1, False)
        outer.addWidget(splitter, 1)

        self.status_label = QLabel("準備就緒")
        self.ffmpeg_label = QLabel("")
        self.ffmpeg_label.setObjectName("Muted")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.ffmpeg_label)

    def _build_detail_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.detail_title = QLabel("詳情")
        self.detail_title.setObjectName("DetailTitle")
        self.detail_files = QLabel("")
        self.detail_files.setObjectName("Muted")
        head.addWidget(self.detail_title)
        head.addStretch(1)
        head.addWidget(self.detail_files)
        lay.addLayout(head)

        self.detail_hint = QLabel("點選左側清單可看到各檔案的 FFmpeg 截圖預覽")
        self.detail_hint.setObjectName("Muted")
        self.detail_hint.setWordWrap(True)
        lay.addWidget(self.detail_hint)

        self.card_area = QScrollArea()
        self.card_area.setWidgetResizable(True)
        self.card_frame = QWidget()
        self.card_layout = QGridLayout(self.card_frame)
        self.card_layout.setSpacing(10)
        self.card_layout.setContentsMargins(4, 4, 4, 4)
        self.card_area.setWidget(self.card_frame)
        lay.addWidget(self.card_area, 1)
        return panel

    # ------------------------------------------------------------- actions
    def _browse_folder(self):
        start = self.root_edit.text() or self.cfg.last_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "選擇資料夾", start)
        if not folder:
            return
        self.root_edit.setText(folder)
        self.cfg.last_folder = folder
        self.cfg.save()
        self.start_scan()

    def start_scan(self):
        root = self.root_edit.text().strip()
        if not root or not os.path.isdir(root):
            self.status_label.setText("請先選擇有效的資料夾")
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("掃描中")
        self.status_label.setText(f"正在掃描 {short_path(root, 60)} …")
        self.tree.clear()
        self._clear_cards()
        self.scan_worker = ScanWorker(root, self.cfg.extensions)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished_ok.connect(self._on_scan_done)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _on_scan_progress(self, dirpath: str, count: int):
        self.status_label.setText(f"正在掃描 {short_path(dirpath, 56)}(已 {count} 個影片)")

    def _on_scan_failed(self, message: str):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("掃描")
        self.status_label.setText(f"掃描失敗:{message}")

    def _on_scan_done(self, files):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("掃描")
        self.files = files
        self._apply_filter()
        if self.visible_groups:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self._select_group(self.visible_groups[0])
        dup_count = sum(1 for g in self.groups if g.is_duplicate)
        seg_count = sum(1 for g in self.groups if g.is_segments)
        self.status_label.setText(
            f"完成:{len(self.files)} 個檔案、{len(self.groups)} 部影片、"
            f"{dup_count} 組重複、{seg_count} 组分段")

    # ------------------------------------------------------------- filtering
    def _apply_filter(self):
        self.groups = group_files(self.files, self.cfg)
        text = self.search_edit.text().strip().lower()
        only_dups = self.dups_chk.isChecked()
        visible = []
        for group in self.groups:
            if only_dups and not group.is_duplicate:
                continue
            if text and text not in group.title.lower() and not any(
                    text in os.path.basename(f.path).lower() for f in group.files):
                continue
            visible.append(group)
        self.visible_groups = visible
        self.count_label.setText(f"{len(visible)} / {len(self.groups)} 部")
        self._fill_tree()

    def _on_dups_toggled(self, checked: bool):
        self.cfg.show_duplicates_only = checked
        self.cfg.save()
        self._apply_filter()

    def _fill_tree(self):
        bold = QFont()
        bold.setBold(True)
        self.tree.clear()
        for group in self.visible_groups:
            if group.is_duplicate:
                badge = "重複"
                badge_color = QColor("#f59e0b")
            elif group.is_segments:
                badge = "分段"
                badge_color = QColor("#38bdf8")
            else:
                badge = "唯一"
                badge_color = QColor("#9aa2ad")
            folders = sorted({os.path.dirname(f.path) for f in group.files})
            loc = short_path(folders[0], 46) if len(folders) == 1 else f"{len(folders)} 個資料夾"
            root_item = QTreeWidgetItem([badge, group.title, str(len(group.files)),
                                         human_size(group.total_size), loc])
            root_item.setFont(1, bold)
            root_item.setForeground(0, badge_color)
            root_item.setData(0, Qt.UserRole, group.key)
            for vf in group.files:
                child = QTreeWidgetItem(["", os.path.basename(vf.path), "",
                                         human_size(vf.size),
                                         short_path(os.path.dirname(vf.path), 46)])
                child.setData(0, Qt.UserRole, vf.path)
                root_item.addChild(child)
            self.tree.addTopLevelItem(root_item)
            if group.is_duplicate or group.is_segments:
                root_item.setExpanded(True)

    # ---------------------------------------------------------- interactions
    def _selected_group(self):
        current = self.tree.currentItem()
        while current is not None and current.parent() is not None:
            current = current.parent()
        if current is None:
            return None
        for group in self.visible_groups:
            if group.key == current.data(0, Qt.UserRole):
                return group
        return None

    def _on_tree_selection(self):
        group = self._selected_group()
        if group is not None:
            self._select_group(group)

    def _on_tree_double_clicked(self, item, column):
        if item.parent() is not None:
            self._open_path(item.data(0, Qt.UserRole))
        else:
            group = self._selected_group()
            if group:
                self._open_path(group.files[0].path)

    def _on_tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        self.tree.setCurrentItem(item)
        if item.parent() is not None:
            path = item.data(0, Qt.UserRole)
            menu = QMenu(self)
            act_play = QAction("用預設播放器開啟", menu)
            act_play.triggered.connect(lambda: self._open_path(path))
            act_folder = QAction("開啟所在資料夾", menu)
            act_folder.triggered.connect(lambda: self._open_folder(path))
            menu.addAction(act_play)
            menu.addAction(act_folder)
            menu.exec(self.tree.viewport().mapToGlobal(pos))
            return
        group = self._selected_group()
        if group is None:
            return
        first = group.files[0].path
        menu = QMenu(self)
        act_play = QAction("用預設播放器開啟(第一個檔案)", menu)
        act_play.triggered.connect(lambda: self._open_path(first))
        act_folder = QAction("開啟所在資料夾", menu)
        act_folder.triggered.connect(lambda: self._open_folder(first))
        menu.addAction(act_play)
        menu.addAction(act_folder)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = dlg.cfg
            self._update_ffmpeg_status()
            self.dups_chk.blockSignals(True)
            self.dups_chk.setChecked(self.cfg.show_duplicates_only)
            self.dups_chk.blockSignals(False)
            self._apply_filter()

    # ------------------------------------------------------------- details
    def _select_group(self, group: VideoGroup):
        self.detail_hint.hide()
        self.detail_title.setText(group.title)
        if group.is_duplicate:
            dup = "  (重複)"
        elif group.is_segments:
            dup = "  (分段)"
        else:
            dup = ""
        self.detail_files.setText(f"{len(group.files)} 個檔案・{human_size(group.total_size)}{dup}")
        self._clear_cards()
        for index, vf in enumerate(group.files):
            card = ThumbCard(vf.path, vf.size)
            card.opened.connect(self._open_path)
            card.folder_requested.connect(self._open_folder)
            self.cards[vf.path] = card
            self.card_layout.addWidget(card, index // COLS, index % COLS)
        rows = (len(group.files) + COLS - 1) // COLS
        self.card_layout.setRowStretch(rows, 1)
        self.card_layout.setColumnStretch(COLS, 1)
        self._start_thumbs(group)

    def _clear_cards(self):
        for card in self.cards.values():
            self.card_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

    def _start_thumbs(self, group: VideoGroup):
        missing = []
        for vf in group.files:
            out = thumb_cache_path(vf, self.cfg.thumbnail_seconds, self.cfg.thumbnail_width)
            if not (os.path.exists(out) and os.path.getsize(out) > 0):
                missing.append(vf)
        if not missing:
            self._refresh_cached_thumbs(group)
            return
        if self.thumb_worker is not None and self.thumb_worker.isRunning():
            return
        ffmpeg = find_ffmpeg(self.cfg)
        self.thumb_worker = ThumbWorker(
            missing, self.cfg.thumbnail_seconds, self.cfg.thumbnail_width, ffmpeg)
        self.thumb_worker.item_done.connect(self._on_thumb_done)
        self.thumb_worker.all_done.connect(self._on_thumbs_done)
        self.thumb_worker.start()

    def _refresh_cached_thumbs(self, group: VideoGroup):
        for vf in group.files:
            out = thumb_cache_path(vf, self.cfg.thumbnail_seconds, self.cfg.thumbnail_width)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                pm = QPixmap(out)
                if not pm.isNull():
                    card = self.cards.get(vf.path)
                    if card:
                        card.set_image(pm)

    def _on_thumb_done(self, path: str, out: str, ok: bool):
        card = self.cards.get(path)
        if card and ok and os.path.exists(out):
            pm = QPixmap(out)
            if not pm.isNull():
                card.set_image(pm)

    def _on_thumbs_done(self):
        self.thumb_worker = None

    # ------------------------------------------------------------------- misc
    def _open_path(self, path: str):
        if not open_with_default(path):
            self.status_label.setText(f"無法開啟:{short_path(path, 60)}")

    def _open_folder(self, path: str):
        open_folder(path, select_file=True)

    def _update_ffmpeg_status(self):
        ff = find_ffmpeg(self.cfg)
        if ff:
            self.ffmpeg_label.setText(f"FFmpeg:{short_path(ff, 40)}  {ffmpeg_version(ff)}")
        else:
            self.ffmpeg_label.setText("FFmpeg:未找到(截圖功能停用)")