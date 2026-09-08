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
    QTabWidget,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import Config
from .ffmpeg_backend import ffmpeg_version, find_ffmpeg, find_ffprobe, probe_video_codecs
from .handbrake_backend import (
    append_transcode_batch,
    find_handbrake,
    load_transcode_log,
    originals_backup_dir,
)
from .scanner import VideoFile, VideoGroup, group_files
from .settings_dialog import SettingsDialog
from .util import human_size, open_folder, open_with_default, short_path
from .workers import (
    CodecScanWorker,
    FileCodecWorker,
    HandBrakeWorker,
    ScanWorker,
    ThumbWorker,
    thumb_cache_path,
)

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
        self._scan_stopped = False
        self.thumb_worker = None
        self.codec_worker = None
        self._codec_scan_stopped = False
        self.codec_results: list[dict] = []
        self.codec_visible: list[dict] = []
        self.codec_row_index: dict[str, int] = {}
        self.dup_codec_worker = None
        self.dup_codec_results: dict[str, dict] = {}
        self.hb_worker = None
        self.codec_encode_status: dict[str, str] = {}
        self.codec_row_index: dict[str, int] = {}
        self._hb_batch: dict | None = None
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

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        # ------------------------------------------------ tab: duplicates
        dup_page = QWidget()
        dup_layout = QVBoxLayout(dup_page)
        dup_layout.setContentsMargins(0, 0, 0, 0)
        dup_layout.setSpacing(10)

        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜尋片名…")
        self.search_edit.textChanged.connect(self._apply_filter)
        self.dups_chk = QCheckBox("只看重複")
        self.dups_chk.setChecked(self.cfg.show_duplicates_only)
        self.dups_chk.toggled.connect(self._on_dups_toggled)
        self.dup_codec_chk = QCheckBox("掃描編碼")
        self.dup_codec_chk.setChecked(self.cfg.dup_scan_codecs)
        self.dup_codec_chk.toggled.connect(self._on_dup_codec_toggled)
        self.settings_btn = QPushButton("⚙ 設定")
        self.settings_btn.setProperty("variant", "secondary")
        self.settings_btn.clicked.connect(self._open_settings)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setAlignment(Qt.AlignVCenter)
        frow.addWidget(self.search_edit, 1)
        frow.addWidget(self.dups_chk)
        frow.addWidget(self.dup_codec_chk)
        frow.addWidget(self.settings_btn)
        frow.addStretch(1)
        frow.addWidget(self.count_label)
        outer.addLayout(frow)

        splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "片名", "檔案數", "總大小", "位置", "編碼"])
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(4, QHeaderView.Interactive)
        for col in (0, 2, 3, 5):
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
        dup_layout.addWidget(splitter, 1)

        # ------------------------------------------------- tab: codecs
        self.tabs.addTab(dup_page, "重複偵測")
        codec_page = self._build_codec_page()
        self.tabs.addTab(codec_page, "編碼掃描")
        hb_page = self._build_hb_results_page()
        self._hb_results_tab_index = self.tabs.addTab(hb_page, "轉碼結果")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.refresh_hb_results()

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

    # ------------------------------------------------------ codec scan tab
    def _build_codec_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.codec_search = QLineEdit()
        self.codec_search.setPlaceholderText("搜尋檔名…")
        self.codec_search.textChanged.connect(self._apply_codec_filter)
        self.non_modern_chk = QCheckBox("只看非 AV1 / HEVC 的影片")
        self.non_modern_chk.setChecked(self.cfg.codec_non_modern_only)
        self.non_modern_chk.toggled.connect(self._apply_codec_filter)
        self.codec_scan_btn = QPushButton("掃描編碼")
        self.codec_scan_btn.clicked.connect(self.start_codec_scan)
        self.codec_encode_btn = QPushButton("轉碼選取並替換")
        self.codec_encode_btn.setToolTip(
            "用 HandBrake 將選取的影片轉碼為 AV1/HEVC(參數見設定),完成後替換原檔案")
        self.codec_encode_btn.clicked.connect(self.start_codec_encode)
        frow.addWidget(self.codec_search, 1)
        frow.addWidget(self.non_modern_chk)
        frow.addWidget(self.codec_scan_btn)
        frow.addWidget(self.codec_encode_btn)
        lay.addLayout(frow)

        self.codec_table = QTableWidget(0, 5)
        self.codec_table.setHorizontalHeaderLabels(
            ["檔名", "位置", "影片編碼", "音訊編碼", "大小"])
        header = self.codec_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        for col in (2, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.codec_table.verticalHeader().setVisible(False)
        self.codec_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.codec_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.codec_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.codec_table.setAlternatingRowColors(True)
        self.codec_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.codec_table.customContextMenuRequested.connect(self._on_codec_menu)
        self.codec_table.itemDoubleClicked.connect(
            lambda item, _col: self._open_path(item.data(Qt.UserRole)))
        lay.addWidget(self.codec_table, 1)

        self.codec_summary = QLabel("尚未掃描")
        self.codec_summary.setObjectName("Muted")
        lay.addWidget(self.codec_summary)
        return page

    # --------------------------------------------------- transcode results tab
    def _build_hb_results_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.hb_batch_label = QLabel("尚無轉碼記錄")
        self.hb_batch_label.setObjectName("Muted")
        self.hb_batch_label.setWordWrap(True)
        lay.addWidget(self.hb_batch_label)

        trow = QHBoxLayout()
        trow.setSpacing(8)
        self.hb_play_btn = QPushButton("▶ 播放選取")
        self.hb_play_btn.setToolTip("用系統預設撥放器開啟選取的輸出檔")
        self.hb_play_btn.clicked.connect(self._play_hb_selected)
        self.hb_open_out_btn = QPushButton("開啟輸出資料夾")
        self.hb_open_out_btn.setToolTip("開啟選取項輸出檔所在的資料夾")
        self.hb_open_out_btn.clicked.connect(lambda: self._open_hb_row_folder(1))
        self.hb_open_orig_btn = QPushButton("開啟原檔備份資料夾")
        self.hb_open_orig_btn.setToolTip("開啟程式資料夾內的原檔備份(hb_originals)")
        self.hb_open_orig_btn.clicked.connect(self._open_hb_originals)
        self.hb_refresh_btn = QPushButton("重新整理")
        self.hb_refresh_btn.setProperty("variant", "secondary")
        self.hb_refresh_btn.clicked.connect(self.refresh_hb_results)
        trow.addWidget(self.hb_play_btn)
        trow.addWidget(self.hb_open_out_btn)
        trow.addWidget(self.hb_open_orig_btn)
        trow.addStretch(1)
        trow.addWidget(self.hb_refresh_btn)
        lay.addLayout(trow)

        self.hb_table = QTableWidget(0, 5)
        self.hb_table.setHorizontalHeaderLabels(
            ["檔案", "輸出路徑", "原檔備份", "大小", "狀態"])
        header = self.hb_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.hb_table.verticalHeader().setVisible(False)
        self.hb_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hb_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hb_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hb_table.setAlternatingRowColors(True)
        self.hb_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hb_table.customContextMenuRequested.connect(self._on_hb_results_menu)
        self.hb_table.itemDoubleClicked.connect(
            lambda item, _col: self._play_hb_path(item.data(Qt.UserRole)))
        lay.addWidget(self.hb_table, 1)

        self.hb_results_summary = QLabel("")
        self.hb_results_summary.setObjectName("Muted")
        lay.addWidget(self.hb_results_summary)
        return page

    def refresh_hb_results(self):
        """Re-read the transcode log and show the most recent batch.

        If nothing has been transcoded this session, the most recent recorded
        batch (i.e. the previous run) is shown.
        """
        batches = load_transcode_log()
        batch = batches[-1] if batches else None
        self.hb_table.setRowCount(0)
        if not batch:
            self.hb_batch_label.setText(
                "尚無轉碼記錄 — 到「編碼掃描」分頁執行轉碼後,結果會顯示在這裡")
            self.hb_results_summary.setText("")
            return
        enc = batch.get("encoder_label") or batch.get("encoder") or ""
        fmt = batch.get("container") or ""
        t = batch.get("time") or ""
        items = batch.get("items", []) or []
        self.hb_batch_label.setText(
            f"轉碼批次:{t}　編碼器:{enc}　輸出格式:.{fmt}　檔案數:{len(items)}")
        done = sum(1 for it in items if it.get("ok"))
        for it in items:
            self._hb_append_row(it)
        self.hb_results_summary.setText(
            f"成功 {done}/{len(items)}　雙擊列或按「▶ 播放選取」可用系統預設撥放器確認;"
            "原檔已移動到 hb_originals,確認無誤後可自行刪除。")

    def _hb_append_row(self, it):
        row = self.hb_table.rowCount()
        self.hb_table.insertRow(row)
        out = it.get("out") or it.get("src") or ""
        src = it.get("src") or ""
        ok = bool(it.get("ok"))
        detail = it.get("detail") or ""
        backup = it.get("original") or ""

        name_item = QTableWidgetItem(os.path.basename(out) or os.path.basename(src) or "(未知)")
        name_item.setData(Qt.UserRole, out)
        name_item.setToolTip(src)
        self.hb_table.setItem(row, 0, name_item)

        out_item = QTableWidgetItem(short_path(out, 54))
        out_item.setData(Qt.UserRole, out)
        out_item.setToolTip(out)
        self.hb_table.setItem(row, 1, out_item)

        orig_item = QTableWidgetItem(short_path(backup, 40) if backup else "(未保留)")
        orig_item.setData(Qt.UserRole, backup)
        orig_item.setToolTip(backup)
        self.hb_table.setItem(row, 2, orig_item)

        size = ""
        if out and os.path.isfile(out):
            try:
                size = human_size(os.path.getsize(out))
            except OSError:
                size = ""
        self.hb_table.setItem(row, 3, QTableWidgetItem(size))

        status_item = QTableWidgetItem("成功" if ok else (detail or "失敗"))
        status_item.setForeground(QColor("#34d399") if ok else QColor("#f87171"))
        status_item.setToolTip(detail if not ok else "")
        self.hb_table.setItem(row, 4, status_item)

    def _on_tab_changed(self, index):
        if index == getattr(self, "_hb_results_tab_index", -1):
            self.refresh_hb_results()

    def _play_hb_path(self, path):
        if not path or not os.path.isfile(path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "找不到檔案",
                "檔案不存在,可能已被移動或刪除:\n" + (path or ""))
            return
        if not open_with_default(path):
            self.status_label.setText(f"無法開啟:{short_path(path, 50)}")

    def _play_hb_selected(self):
        rows = sorted({i.row() for i in self.hb_table.selectionModel().selectedRows()})
        if not rows:
            self.status_label.setText("請先選取要播放的轉碼結果")
            return
        item = self.hb_table.item(rows[0], 0)
        path = item.data(Qt.UserRole) if item else None
        self._play_hb_path(path)

    def _open_hb_row_folder(self, col):
        rows = sorted({i.row() for i in self.hb_table.selectionModel().selectedRows()})
        if not rows:
            self.status_label.setText("請先選取一列")
            return
        item = self.hb_table.item(rows[0], col)
        path = item.data(Qt.UserRole) if item else None
        if path and os.path.isfile(path):
            open_folder(path, select_file=True)

    def _open_hb_originals(self):
        d = originals_backup_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        open_folder(d)

    def _on_hb_results_menu(self, pos):
        row = self.hb_table.rowAt(pos.y())
        if row is None:
            return
        out_item = self.hb_table.item(row, 0)
        out = out_item.data(Qt.UserRole) if out_item else None
        orig_item = self.hb_table.item(row, 2)
        orig = orig_item.data(Qt.UserRole) if orig_item else None
        menu = QMenu(self)
        act_play = menu.addAction("▶ 播放(系統預設撥放器)")
        act_play.triggered.connect(lambda: self._play_hb_path(out))
        menu.addSeparator()
        act_out = menu.addAction("開啟輸出所在資料夾")
        act_out.setEnabled(bool(out and os.path.isfile(out)))
        act_out.triggered.connect(
            lambda: out and os.path.isfile(out) and open_folder(out, select_file=True))
        act_orig = menu.addAction("開啟原檔備份所在資料夾")
        act_orig.setEnabled(bool(orig and os.path.isfile(orig)))
        act_orig.triggered.connect(
            lambda: orig and os.path.isfile(orig) and open_folder(orig, select_file=True))
        menu.exec(self.hb_table.viewport().mapToGlobal(pos))

    @staticmethod
    def _codec_label(code):
        if not code:
            return "未知"
        nice = {
            "hevc": "HEVC (H.265)",
            "h265": "HEVC (H.265)",
            "av1": "AV1",
            "h264": "H.264 (AVC)",
            "mpeg4": "MPEG-4",
            "wmv2": "WMV2",
            "wmv3": "WMV3",
            "xvid": "DivX / Xvid (MPEG-4)",
            "divx": "DivX / Xvid (MPEG-4)",
            "vp9": "VP9",
            "vp8": "VP8",
        }
        return nice.get(code.lower(), code)

    @staticmethod
    def _is_modern_codec(code):
        return bool(code) and code.lower() in ("av1", "hevc", "h265")

    def start_codec_scan(self):
        # While running the button acts as "停止" -> request a stop.
        if self.codec_worker is not None and self.codec_worker.isRunning():
            self._codec_scan_stopped = True
            self.codec_worker.stop()
            self.status_label.setText("正在停止編碼掃描 …")
            return
        root = os.path.normpath(self.root_edit.text().strip())
        if not root or not os.path.isdir(root):
            self.status_label.setText("請先選擇有效的資料夾")
            return
        ffprobe = find_ffprobe(find_ffmpeg(self.cfg))
        if not ffprobe:
            self.status_label.setText("未找到 ffprobe,無法掃描編碼")
            return
        self._codec_scan_stopped = False
        self.codec_scan_btn.setText("停止")
        self.codec_scan_btn.setProperty("variant", "danger")
        self._repolish(self.codec_scan_btn)
        self.codec_table.setRowCount(0)
        self.codec_row_index.clear()
        self.codec_results = []
        self.codec_summary.setText("掃描中…")
        self.status_label.setText(f"正在掃描編碼 {short_path(root, 60)} …")
        self.codec_worker = CodecScanWorker(root, self.cfg.extensions, ffprobe)
        self.codec_worker.progress.connect(self._on_codec_progress)
        self.codec_worker.item_done.connect(self._on_codec_item)
        self.codec_worker.finished_ok.connect(self._on_codec_done)
        self.codec_worker.failed.connect(self._on_codec_failed)
        self.codec_worker.start()

    def _on_codec_progress(self, dirpath: str, total: int, shown: int):
        self.status_label.setText(
            f"編碼掃描 {short_path(dirpath, 56)}(已完成 {total}/{shown} 個檔案)")

    def _on_codec_item(self, path: str, vcodec: str, acodec: str):
        info = {"path": path, "vcodec": vcodec or None, "acodec": acodec or None}
        row = self.codec_row_index.get(path)
        if row is None or row >= self.codec_table.rowCount():
            self._codec_append_row(info)
        else:
            self.codec_table.item(row, 2).setText(self._codec_label(info["vcodec"]))
            self.codec_table.item(row, 3).setText(info["acodec"] or "")
            self._apply_codec_row_color(row)

    def _codec_append_row(self, info):
        row = self.codec_table.rowCount()
        self.codec_table.insertRow(row)
        self.codec_row_index[info["path"]] = row
        name = os.path.basename(info["path"])
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, info["path"])
        name_item.setToolTip(info["path"])
        self.codec_table.setItem(row, 0, name_item)
        self.codec_table.setItem(
            row, 1, QTableWidgetItem(short_path(os.path.dirname(info["path"]), 46)))
        self.codec_table.setItem(row, 2, QTableWidgetItem("掃描中…"))
        self.codec_table.setItem(row, 3, QTableWidgetItem(""))
        self.codec_table.setItem(
            row, 4, QTableWidgetItem(human_size(info.get("size", 0))))
        self._apply_codec_row_color(row)

    def _reset_codec_button(self):
        self.codec_scan_btn.setEnabled(True)
        self.codec_scan_btn.setText("掃描編碼")
        self.codec_scan_btn.setProperty("variant", "")
        self._repolish(self.codec_scan_btn)

    def _on_codec_done(self, results):
        self._reset_codec_button()
        self.codec_results = results
        self._apply_codec_filter()
        total = len(results)
        bad = sum(1 for r in results
                  if r["vcodec"] and not self._is_modern_codec(r["vcodec"]))
        unknown = sum(1 for r in results if not r["vcodec"])
        if self._codec_scan_stopped:
            self._codec_scan_stopped = False
            self.codec_summary.setText(f"已停止:目前 {total} 個影片(部分結果)")
            self.status_label.setText(f"編碼掃描已停止:{total} 個檔案")
            return
        self.codec_summary.setText(
            f"共 {total} 個影片,其中 {bad} 個非 AV1/HEVC"
            + (f"、{unknown} 個無法辨識" if unknown else ""))
        self.status_label.setText(f"編碼掃描完成:{total} 個檔案")

    def _on_codec_failed(self, message: str):
        self._reset_codec_button()
        self.status_label.setText(f"編碼掃描失敗:{message}")

    # ------------------------------------------------------------- handbrake
    def _encoder_label(self):
        from .handbrake_backend import ENCODER_CHOICES
        enc = self.cfg.handbrake_encoder
        return dict(ENCODER_CHOICES).get(enc, enc)

    def _selected_codec_paths(self):
        """Paths of the selected rows (only non-modern codecs), or []."""
        paths = []
        for index in self.codec_table.selectionModel().selectedRows():
            row = index.row()
            item = self.codec_table.item(row, 0)
            if item is None:
                continue
            paths.append(item.data(Qt.UserRole))
        return paths

    def start_codec_encode(self, explicit_paths=None):
        if self.hb_worker is not None and self.hb_worker.isRunning():
            self.status_label.setText("HandBrake 正在轉碼中…")
            return
        if explicit_paths:
            paths = list(explicit_paths)
        else:
            selected = self._selected_codec_paths()
            if selected:
                paths = selected
            else:
                # No selection: offer everything visible that needs re-encoding.
                paths = [info["path"] for info in self.codec_results
                         if not self._is_modern_codec(info.get("vcodec"))]
        # Keep only existing files that are not already modern and not in flight.
        ready, skipped = [], 0
        for path in paths:
            info = next((r for r in self.codec_results if r["path"] == path), None)
            if info is None or not os.path.isfile(path):
                skipped += 1
                continue
            if self._is_modern_codec(info.get("vcodec")):
                skipped += 1
                continue
            if self.codec_encode_status.get(path) == "enc":
                skipped += 1
                continue
            ready.append(path)
        if not ready:
            self.status_label.setText(
                f"沒有可轉碼的影片(需先掃描編碼並選取非 AV1/HEVC 檔案){'、略過 ' + str(skipped) if skipped else ''}")
            return
        cli = find_handbrake(self.cfg)
        if not cli:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "HandBrake 未設定",
                "尚未找到 HandBrakeCLI。\n\n請到「⚙ 設定 → HandBrake」指定 "
                "HandBrakeCLI.exe 的安裝位置後再試。")
            return
        if skipped:
            self.status_label.setText(f"略過 {skipped} 個(已是 AV1/HEVC),轉碼 {len(ready)} 個…")
        else:
            self.status_label.setText(f"HandBrake 轉碼 {len(ready)} 個檔案…")
        self.codec_encode_btn.setEnabled(False)
        self.codec_encode_btn.setText("轉碼中…")
        from datetime import datetime
        self._hb_batch = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "encoder": self.cfg.handbrake_encoder,
            "encoder_label": self._encoder_label(),
            "container": self.cfg.handbrake_container,
            "quality": self.cfg.handbrake_quality,
            "items": [],
        }
        ffprobe = find_ffprobe(find_ffmpeg(self.cfg))
        self.hb_worker = HandBrakeWorker(
            ready, cli, self.cfg.handbrake_encoder,
            self.cfg.handbrake_quality, self.cfg.handbrake_keep_backup,
            self.cfg.handbrake_container)
        self.hb_worker.progress.connect(self._on_hb_progress)
        self.hb_worker.item_done.connect(self._on_hb_item)
        self.hb_worker.all_done.connect(self._on_hb_all_done)
        self.hb_worker._ffprobe = ffprobe
        self.hb_worker.start()

    def _on_hb_progress(self, path: str, percent: int, stage: str):
        self.status_label.setText(
            f"HandBrake 轉碼 {short_path(os.path.basename(path), 40)}:{percent}%")

    def _on_hb_item(self, path: str, ok: bool, detail: str, final_path: str,
                    backup_path: str):
        if self._hb_batch is not None:
            self._hb_batch["items"].append({
                "src": path,
                "out": final_path or path,
                "ok": bool(ok),
                "detail": detail,
                "original": backup_path or "",
            })
        row = self.codec_row_index.get(path)
        renamed = bool(ok and final_path and final_path != path)
        if renamed:
            self._renamed_codec_path(path, final_path, row)
            path = final_path
            row = self.codec_row_index.get(path)
        if ok:
            self.codec_encode_status[path] = "done"
            ffprobe = getattr(self.hb_worker, "_ffprobe", None)
            if ffprobe:
                vcodec, acodec = probe_video_codecs(ffprobe, path)
                info = next((r for r in self.codec_results if r["path"] == path), None)
                if info is not None:
                    info["vcodec"] = vcodec
                    info["acodec"] = acodec
            if row is not None:
                self._apply_codec_row_color(row)
        else:
            self.codec_encode_status[path] = "fail"
            if row is not None:
                self._apply_codec_row_color(row)
        if ok:
            if renamed:
                note = f"(已替換為 {os.path.splitext(path)[1]})"
            else:
                note = "(已替換原檔)"
        else:
            note = f"(失敗:{detail})"
        self.status_label.setText(
            f"完成:{short_path(os.path.basename(path), 40)}{note}")

    def _renamed_codec_path(self, old: str, new: str, row):
        """Re-key table row / index / status after a successful encode
        changed the file name to match the output container."""
        info = next((r for r in self.codec_results if r["path"] == old), None)
        if info is not None:
            info["path"] = new
        if row is not None:
            item = self.codec_table.item(row, 0)
            if item is not None:
                item.setText(os.path.basename(new))
                item.setData(Qt.UserRole, new)
                item.setToolTip(new)
        self.codec_row_index.pop(old, None)
        if row is not None:
            self.codec_row_index[new] = row
        self.codec_encode_status.pop(old, None)

    def _on_hb_all_done(self):
        self.hb_worker = None
        self.codec_encode_btn.setEnabled(True)
        self.codec_encode_btn.setText("轉碼選取並替換")
        done = sum(1 for s in self.codec_encode_status.values() if s == "done")
        failed = sum(1 for s in self.codec_encode_status.values() if s == "fail")
        extra = f"、失敗 {failed}" if failed else ""
        if self.cfg.handbrake_keep_backup:
            backup = "、原檔已移至 hb_originals"
        else:
            backup = "、原檔已刪除"
        batch = self._hb_batch
        self._hb_batch = None
        if batch and batch.get("items"):
            append_transcode_batch(batch)
            self.refresh_hb_results()
        self.status_label.setText(f"HandBrake 轉碼完成:成功 {done}{extra}{backup}")

    def _apply_codec_filter(self):
        text = self.codec_search.text().strip().lower()
        only_bad = self.non_modern_chk.isChecked()
        self.codec_table.setRowCount(0)
        self.codec_row_index.clear()
        shown = 0
        for info in self.codec_results:
            if only_bad and self._is_modern_codec(info["vcodec"]):
                continue
            name = os.path.basename(info["path"]).lower()
            if text and text not in name and text not in info["path"].lower():
                continue
            self._codec_append_row(info)
            shown += 1
        self.count_label.setText(
            f"編碼:{shown} / {len(self.codec_results)} 個影片")

    def _apply_codec_row_color(self, row: int):
        item = self.codec_table.item(row, 0)
        if item is None:
            return
        info = next((r for r in self.codec_results
                     if r["path"] == item.data(Qt.UserRole)), None)
        if info is None:
            return
        status = self.codec_encode_status.get(info["path"])
        col2 = self.codec_table.item(row, 2)
        if status == "enc":
            col2.setText(self._codec_label(info["vcodec"]) + " → 轉碼中…")
            col2.setForeground(QColor("#38bdf8"))
        elif status == "done":
            col2.setText((self._codec_label(info["vcodec"]) + " → "
                          + self._encoder_label()) if info["vcodec"] else self._encoder_label())
            col2.setForeground(QColor("#34d399"))
        elif status == "fail":
            col2.setText((self._codec_label(info["vcodec"]) + " → 轉碼失敗")
                          if info["vcodec"] else "轉碼失敗")
            col2.setForeground(QColor("#f87171"))
        elif info["vcodec"] and not self._is_modern_codec(info["vcodec"]):
            col2.setForeground(QColor("#f59e0b"))

    def _on_codec_menu(self, pos):
        row = self.codec_table.rowAt(pos.y())
        if row is None:
            return
        item = self.codec_table.item(row, 0)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        info = next((r for r in self.codec_results if r["path"] == path), None)
        menu = QMenu(self)
        act_play = QAction("用預設播放器開啟", menu)
        act_play.triggered.connect(lambda: self._open_path(path))
        act_folder = QAction("開啟檔案所在資料夾", menu)
        act_folder.triggered.connect(lambda: self._open_folder(path))
        act_encode = QAction(f"轉碼為 {self._encoder_label()} 並替換", menu)
        busy = (self.hb_worker is not None and self.hb_worker.isRunning())
        already = bool(info and self._is_modern_codec(info.get("vcodec")))
        act_encode.setEnabled(not busy and not already)
        act_encode.triggered.connect(lambda: self.start_codec_encode([path]))
        menu.addAction(act_play)
        menu.addAction(act_folder)
        menu.addAction(act_encode)
        menu.exec(self.codec_table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- actions
    def _browse_folder(self):
        start = self.root_edit.text() or self.cfg.last_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "選擇資料夾", start)
        if not folder:
            return
        # Qt returns "/" separators even on Windows ("Z:/影片/…"); normalize to
        # native paths so every downstream path (os.walk, ffprobe, HandBrake,
        # explorer /select) uses backslashes.
        folder = os.path.normpath(folder)
        self.root_edit.setText(folder)
        self.cfg.last_folder = folder
        self.cfg.save()
        self.start_scan()

    @staticmethod
    def _repolish(widget):
        """Force a style refresh after changing a dynamic property (variant)."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def start_scan(self):
        # While a scan is running the button acts as "停止" -> request a stop.
        if self.scan_worker is not None and self.scan_worker.isRunning():
            self._scan_stopped = True
            self.scan_worker.stop()
            self.status_label.setText("正在停止掃描 …")
            return
        root = os.path.normpath(self.root_edit.text().strip())
        if not root or not os.path.isdir(root):
            self.status_label.setText("請先選擇有效的資料夾")
            return
        self._scan_stopped = False
        self.scan_btn.setText("停止")
        self.scan_btn.setProperty("variant", "danger")
        self._repolish(self.scan_btn)
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

    def _reset_scan_button(self):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("掃描")
        self.scan_btn.setProperty("variant", "")
        self._repolish(self.scan_btn)

    def _on_scan_failed(self, message: str):
        self._reset_scan_button()
        self.status_label.setText(f"掃描失敗:{message}")

    def _on_scan_done(self, files):
        self._reset_scan_button()
        self.files = files
        self._apply_filter()
        if self.dup_codec_chk.isChecked():
            self._start_dup_codec_scan()
        if self.visible_groups:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self._select_group(self.visible_groups[0])
        dup_count = sum(1 for g in self.groups if g.is_duplicate)
        seg_count = sum(1 for g in self.groups if g.is_segments)
        if self._scan_stopped:
            self._scan_stopped = False
            self.status_label.setText(
                f"已停止:{len(self.files)} 個檔案、{len(self.groups)} 部影片")
        else:
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

    def _on_dup_codec_toggled(self, checked: bool):
        self.cfg.dup_scan_codecs = checked
        self.cfg.save()
        if checked:
            self._start_dup_codec_scan()
        elif self.dup_codec_worker is not None and self.dup_codec_worker.isRunning():
            self.dup_codec_worker.stop()

    def _start_dup_codec_scan(self):
        if not self.files:
            return
        if self.dup_codec_worker is not None and self.dup_codec_worker.isRunning():
            return
        ff = find_ffmpeg(self.cfg)
        ffprobe = find_ffprobe(ff)
        if not ffprobe:
            self.status_label.setText("找不到 ffprobe，無法掃描編碼")
            return
        self.dup_codec_chk.setEnabled(False)
        self.dup_codec_chk.setText("掃描編碼中…")
        self.dup_codec_worker = FileCodecWorker(self.files, ffprobe)
        self.dup_codec_worker.item_done.connect(self._on_dup_codec_item)
        self.dup_codec_worker.finished_ok.connect(self._on_dup_codec_done)
        self.dup_codec_worker.failed.connect(self._on_dup_codec_failed)
        self.dup_codec_worker.start()

    def _on_dup_codec_item(self, path: str, vcodec: str, acodec: str):
        self.dup_codec_results[path] = {"vcodec": vcodec or None, "acodec": acodec or None}
        self._refresh_dup_codec_cells()

    def _on_dup_codec_done(self, results):
        self.dup_codec_worker = None
        self.dup_codec_chk.setEnabled(True)
        self.dup_codec_chk.setText("掃描編碼")
        self._refresh_dup_codec_cells()
        scanned = sum(1 for r in results if r.get("vcodec"))
        self.status_label.setText(f"編碼掃描完成:{scanned}/{len(results)} 個檔案已識別")

    def _on_dup_codec_failed(self, message: str):
        self.dup_codec_worker = None
        self.dup_codec_chk.setEnabled(True)
        self.dup_codec_chk.setText("掃描編碼")
        self.status_label.setText(f"編碼掃描失敗:{message}")

    def _dup_file_codec(self, vf):
        code = (self.dup_codec_results.get(vf.path) or {}).get("vcodec")
        return self._codec_label(code) if code else "—"

    def _dup_group_codec(self, group):
        labels = []
        for vf in group.files:
            code = (self.dup_codec_results.get(vf.path) or {}).get("vcodec")
            if not code:
                continue
            lab = self._codec_label(code)
            if lab not in labels:
                labels.append(lab)
        return ", ".join(labels) if labels else "—"

    def _refresh_dup_codec_cells(self):
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            labels = []
            for j in range(root.childCount()):
                child = root.child(j)
                path = child.childCount() if False else child.data(0, Qt.UserRole)
                info = self.dup_codec_results.get(path) or {}
                code = info.get("vcodec")
                if code:
                    lab = self._codec_label(code)
                    child.setText(5, lab)
                    if lab not in labels:
                        labels.append(lab)
                else:
                    child.setText(5, "—")
                audio = info.get("acodec")
                child.setToolTip(5, ("音訊:" + audio) if audio else "")
            root.setText(5, ", ".join(labels) if labels else "—")

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
                                         human_size(group.total_size), loc,
                                         self._dup_group_codec(group)])
            root_item.setFont(1, bold)
            root_item.setForeground(0, badge_color)
            root_item.setData(0, Qt.UserRole, group.key)
            for vf in group.files:
                child = QTreeWidgetItem(["", os.path.basename(vf.path), "",
                                         human_size(vf.size),
                                         short_path(os.path.dirname(vf.path), 46),
                                         self._dup_file_codec(vf)])
                child.setData(0, Qt.UserRole, vf.path)
                audio = (self.dup_codec_results.get(vf.path) or {}).get("acodec")
                if audio:
                    child.setToolTip(5, "音訊:" + audio)
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
            self.dup_codec_chk.blockSignals(True)
            self.dup_codec_chk.setChecked(self.cfg.dup_scan_codecs)
            self.dup_codec_chk.blockSignals(False)
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