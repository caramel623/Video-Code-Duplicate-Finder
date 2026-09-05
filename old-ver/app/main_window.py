from __future__ import annotations

import html
import os
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .app_paths import AppPaths
from .deletion_log import DeletionLogger
from .deletion_service import (
    DeleteResult,
    DeleteStatus,
    DeletionSafetyError,
    DeletionService,
    FolderPreview,
    suggested_keep,
)
from .models import VideoItem
from .scanner import duplicate_groups, scan_videos
from .settings import DeleteSettings, UserSettingsStore
from .thumbnail_service import FFmpegTools, ThumbnailService
from .thumbnail_view import VideoThumbnailView


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def ffmpeg_directory_complete(directory: Path) -> bool:
    return (directory / "ffmpeg.exe").is_file() and (directory / "ffprobe.exe").is_file()


class ScanWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.root = root

    def run(self) -> None:
        try:
            items = scan_videos(self.root, should_cancel=self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.completed.emit(items)
        except Exception as exc:  # GUI boundary: report safely instead of crashing.
            self.failed.emit(str(exc))


class PreviewDialog(QDialog):
    def __init__(self, previews: list[FolderPreview], parent=None):
        super().__init__(parent)
        self.setWindowTitle("預覽刪除內容")
        self.resize(920, 650)
        layout = QVBoxLayout(self)

        totals = (
            len(previews),
            sum(p.file_count for p in previews),
            sum(p.total_size for p in previews),
        )
        summary = QLabel(
            f"將處理 <b>{totals[0]}</b> 個資料夾　 "
            f"共 <b>{totals[1]}</b> 個檔案　 "
            f"總大小 <b>{format_size(totals[2])}</b>"
        )
        summary.setObjectName("summaryCard")
        layout.addWidget(summary)

        warnings: list[str] = []
        if any(p.has_multiple_codes for p in previews):
            warnings.append("警告：部分資料夾包含其他番號的影片。刪除資料夾將一併刪除其中所有內容。")
        if any(p.has_unrecognized_video for p in previews):
            warnings.append("部分資料夾包含無法辨識番號的影片，請逐項確認內容。")
        if warnings:
            warning = QLabel("<br>".join(html.escape(x) for x in warnings))
            warning.setWordWrap(True)
            warning.setObjectName("dangerCard")
            layout.addWidget(warning)

        tree = QTreeWidget()
        tree.setHeaderLabels(["項目", "內容／完整路徑"])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        for preview in previews:
            root = QTreeWidgetItem(
                [
                    preview.path.name,
                    f"{preview.path}　｜　{preview.file_count} 個檔案　｜　{format_size(preview.total_size)}",
                ]
            )
            root.setData(0, Qt.UserRole, str(preview.path))
            root.setExpanded(preview.has_multiple_codes or preview.has_unrecognized_video)
            tree.addTopLevelItem(root)
            codes = "、".join(sorted(preview.codes)) if preview.codes else "未辨識"
            QTreeWidgetItem(root, ["涉及番號", codes])
            QTreeWidgetItem(root, ["子資料夾數量", str(preview.subfolder_count)])
            video_group = QTreeWidgetItem(root, [f"影片（{len(preview.videos)}）", ""])
            for path in preview.videos:
                QTreeWidgetItem(video_group, ["影片", str(path)])
            other_group = QTreeWidgetItem(root, [f"其他檔案（{len(preview.other_files)}）", ""])
            for path in preview.other_files:
                QTreeWidgetItem(other_group, ["檔案", str(path)])
        layout.addWidget(tree, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)


class ConfirmationDialog(QDialog):
    def __init__(self, previews: list[FolderPreview], scan_root: Path, permanent: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("第二階段刪除確認")
        self.resize(720, 470)
        layout = QVBoxLayout(self)

        title = QLabel("永久刪除確認" if permanent else "移至資源回收筒確認")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        if permanent:
            warning = QLabel("危險：永久刪除無法從資源回收筒復原。")
            warning.setObjectName("dangerCard")
            layout.addWidget(warning)

        paths = "\n".join(str(p.path) for p in previews)
        detail = QLabel(
            "即將刪除以下資料夾及其中全部內容：\n\n"
            f"{paths}\n\n"
            "上層掃描根目錄不會被刪除：\n"
            f"{scan_root}"
        )
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(detail)
        layout.addWidget(scroll, 1)

        self.understand = QCheckBox("我了解整個資料夾及其中所有內容都會被刪除")
        layout.addWidget(self.understand)
        self.permanent_understand: QCheckBox | None = None
        if permanent:
            self.permanent_understand = QCheckBox("我再次確認這是永久刪除，而且無法復原")
            layout.addWidget(self.permanent_understand)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.confirm = QPushButton("確認永久刪除" if permanent else "確認刪除")
        self.confirm.setObjectName("dangerButton")
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.confirm)
        layout.addLayout(row)

        self.understand.toggled.connect(self._update_confirm)
        if self.permanent_understand:
            self.permanent_understand.toggled.connect(self._update_confirm)

    def _update_confirm(self) -> None:
        permanent_ok = self.permanent_understand is None or self.permanent_understand.isChecked()
        self.confirm.setEnabled(self.understand.isChecked() and permanent_ok)


class ResultDialog(QDialog):
    def __init__(self, results: list[DeleteResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle("刪除詳細結果")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(results), 3)
        table.setHorizontalHeaderLabels(["資料夾完整路徑", "結果", "錯誤訊息"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, result in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(str(result.path)))
            table.setItem(row, 1, QTableWidgetItem(result.status.value))
            table.setItem(row, 2, QTableWidgetItem(result.error))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(table)
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)


class MainWindow(QMainWindow):
    COLUMNS = [
        "選取",
        "番號",
        "影片檔名",
        "刪除資料夾路徑",
        "資料夾內影片數量",
        "檔案總數",
        "資料夾總大小",
        "刪除狀態",
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Code Duplicate Finder")
        preferred_font = QFont("Microsoft JhengHei UI", 10)
        if preferred_font.exactMatch():
            self.setFont(preferred_font)
        self.resize(1440, 860)
        self.setMinimumSize(1050, 650)

        self.root: Path | None = None
        self.items: list[VideoItem] = []
        self.folder_previews: dict[Path, FolderPreview] = {}
        self.selected_paths: set[Path] = set()
        self.status_by_folder: dict[Path, str] = {}
        self.settings = DeleteSettings()
        self.deletion: DeletionService | None = None
        self.scan_worker: ScanWorker | None = None
        self.paths = AppPaths.for_current_user()
        self.delete_logger = DeletionLogger(self.paths.deletion_log)
        self.user_settings = UserSettingsStore(self.paths.settings_file)
        saved_ffmpeg_dir = self.user_settings.load_ffmpeg_directory()
        self.configured_ffmpeg_dir = (
            saved_ffmpeg_dir if saved_ffmpeg_dir and ffmpeg_directory_complete(saved_ffmpeg_dir) else None
        )
        ffmpeg_candidates = []
        if self.configured_ffmpeg_dir:
            ffmpeg_candidates.append(self.configured_ffmpeg_dir)
        ffmpeg_candidates.extend(
            [self.paths.ffmpeg_dir, Path(__file__).resolve().parents[1] / "tools" / "ffmpeg"]
        )
        self.thumbnail_service = ThumbnailService(
            self.paths.thumbnail_dir,
            ffmpeg_candidates,
        )

        self._build_ui()
        self._apply_style()
        self._update_actions()

    def _build_ui(self) -> None:
        container = QWidget()
        self.setCentralWidget(container)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        toolbar = QFrame()
        toolbar.setObjectName("toolbarCard")
        top = QHBoxLayout(toolbar)
        self.choose_button = QPushButton("選擇掃描資料夾")
        self.choose_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.choose_button.clicked.connect(self.choose_root)
        top.addWidget(self.choose_button)
        self.root_label = QLabel("尚未選擇掃描根目錄")
        self.root_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.root_label, 1)
        self.stop_button = QPushButton("停止掃描")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.hide()
        top.addWidget(self.stop_button)
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setFixedWidth(150)
        self.scan_progress.hide()
        top.addWidget(self.scan_progress)
        outer.addWidget(toolbar)

        self.tabs = QTabWidget()
        self.duplicate_table = self._create_table()
        self.all_table = self._create_table()
        self.thumbnail_view = VideoThumbnailView(self.thumbnail_service)
        self.thumbnail_view.folder_selection_changed.connect(self._thumbnail_selection_changed)
        self.thumbnail_view.video_activated.connect(self.open_video)
        self.tabs.addTab(self._results_page(self.duplicate_table), "重複番號結果")
        self.tabs.addTab(self._results_page(self.all_table), "影片瀏覽結果")
        self.tabs.addTab(self._settings_page(), "設定")
        outer.addWidget(self.tabs, 1)

        status_row = QHBoxLayout()
        self.count_label = QLabel("影片：0　重複番號群組：0　重複項目：0")
        status_row.addWidget(self.count_label)
        status_row.addStretch()
        self.selection_label = QLabel("已選取 0 個資料夾")
        status_row.addWidget(self.selection_label)
        outer.addLayout(status_row)
        self.statusBar().showMessage("就緒")

    def _results_page(self, table: QTableWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        controls = QHBoxLayout()
        self.delete_button = getattr(self, "delete_button", QPushButton("刪除已選取項目的所在資料夾"))
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self.delete_selected, Qt.UniqueConnection)
        self.preview_button = getattr(self, "preview_button", QPushButton("預覽刪除內容"))
        self.preview_button.clicked.connect(self.preview_selected, Qt.UniqueConnection)
        self.select_other_button = getattr(self, "select_other_button", QPushButton("選取同番號中除最佳版本以外的項目"))
        self.select_other_button.clicked.connect(self.select_non_best, Qt.UniqueConnection)
        clear = QPushButton("清除選取")
        clear.clicked.connect(self.clear_selection)
        # Shared actions are shown only on the first page; the second page gets lightweight clones.
        if table is self.duplicate_table:
            for button in (self.delete_button, self.preview_button, self.select_other_button, clear):
                controls.addWidget(button)
        else:
            delete_clone = QPushButton("刪除已選取項目的所在資料夾")
            delete_clone.setObjectName("dangerButton")
            delete_clone.clicked.connect(self.delete_selected)
            preview_clone = QPushButton("預覽刪除內容")
            preview_clone.clicked.connect(self.preview_selected)
            clear_clone = QPushButton("清除選取")
            clear_clone.clicked.connect(self.clear_selection)
            self.result_action_clones = [delete_clone, preview_clone]
            for button in (delete_clone, preview_clone, clear_clone):
                controls.addWidget(button)
            self.browser_view_button = QPushButton("切換至預覽圖")
            self.browser_view_button.setCheckable(True)
            self.browser_view_button.toggled.connect(self._toggle_browser_view)
            controls.addWidget(self.browser_view_button)
        controls.addStretch()
        layout.addLayout(controls)
        if table is self.all_table:
            self.browser_stack = QStackedWidget()
            self.browser_stack.addWidget(table)
            self.browser_stack.addWidget(self.thumbnail_view)
            layout.addWidget(self.browser_stack)
        else:
            layout.addWidget(table)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        group = QGroupBox("刪除功能")
        form = QVBoxLayout(group)
        self.enable_delete = QCheckBox("啟用刪除功能")
        self.enable_delete.setToolTip("關閉時，所有刪除按鈕都會停用。")
        self.enable_delete.toggled.connect(self._delete_enabled_changed)
        form.addWidget(self.enable_delete)
        self.recycle_radio = QRadioButton("預設移至 Windows 資源回收筒（建議）")
        self.recycle_radio.setChecked(True)
        self.recycle_radio.toggled.connect(self._mode_changed)
        form.addWidget(self.recycle_radio)
        layout.addWidget(group)

        ffmpeg_group = QGroupBox("FFmpeg 工具")
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        ffmpeg_help = QLabel(
            "主程式不內含 FFmpeg。請指定同時包含 ffmpeg.exe 與 ffprobe.exe 的資料夾；"
            "未指定時會檢查程式旁的 tools/ffmpeg 及 Windows PATH。"
        )
        ffmpeg_help.setWordWrap(True)
        ffmpeg_layout.addWidget(ffmpeg_help)
        ffmpeg_row = QHBoxLayout()
        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setReadOnly(True)
        self.ffmpeg_path_edit.setPlaceholderText("尚未指定 FFmpeg 資料夾")
        ffmpeg_row.addWidget(self.ffmpeg_path_edit, 1)
        choose_ffmpeg = QPushButton("指定資料夾")
        choose_ffmpeg.clicked.connect(self.choose_ffmpeg_directory)
        ffmpeg_row.addWidget(choose_ffmpeg)
        auto_ffmpeg = QPushButton("清除並自動偵測")
        auto_ffmpeg.clicked.connect(self.clear_ffmpeg_directory)
        ffmpeg_row.addWidget(auto_ffmpeg)
        ffmpeg_layout.addLayout(ffmpeg_row)
        self.ffmpeg_status_label = QLabel()
        self.ffmpeg_status_label.setWordWrap(True)
        ffmpeg_layout.addWidget(self.ffmpeg_status_label)
        layout.addWidget(ffmpeg_group)
        self._update_ffmpeg_ui()

        advanced = QGroupBox("進階設定")
        advanced_layout = QVBoxLayout(advanced)
        warning = QLabel("永久刪除模式具有高風險，刪除後無法從資源回收筒復原。")
        warning.setObjectName("dangerCard")
        warning.setWordWrap(True)
        advanced_layout.addWidget(warning)
        self.permanent_radio = QRadioButton("啟用永久刪除模式")
        self.permanent_radio.toggled.connect(self._mode_changed)
        advanced_layout.addWidget(self.permanent_radio)
        note = QLabel("此選項永遠預設關閉；每次永久刪除仍需額外勾選確認。")
        note.setObjectName("mutedText")
        advanced_layout.addWidget(note)
        layout.addWidget(advanced)

        protected = QGroupBox("安全限制")
        protected_layout = QVBoxLayout(protected)
        protected_layout.addWidget(
            QLabel(
                "程式會拒絕刪除掃描根目錄、磁碟／UNC 根目錄、Windows 目錄、使用者家目錄、"
                "程式資料與快取目錄；並且不跟隨 symbolic link、junction 或 reparse point。"
            )
        )
        layout.addWidget(protected)
        layout.addStretch()
        return page

    def _create_table(self) -> QTableWidget:
        table = QTableWidget(0, len(self.COLUMNS))
        table.setHorizontalHeaderLabels(self.COLUMNS)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, t=table: self.context_menu(t, pos))
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for col in (4, 5, 6, 7):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        return table

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f4f6f9; color: #1f2937; }
            QFrame#toolbarCard, QLabel#summaryCard { background: white; border: 1px solid #d8dee8; border-radius: 8px; padding: 9px; }
            QLabel#dangerCard { background: #fff1f1; color: #a11616; border: 1px solid #efb4b4; border-radius: 6px; padding: 10px; }
            QLabel#dialogTitle { font-size: 18px; font-weight: 700; }
            QLabel#mutedText { color: #667085; }
            QPushButton { background: white; border: 1px solid #b9c2cf; border-radius: 6px; padding: 7px 12px; }
            QPushButton:hover { background: #edf3fb; border-color: #7e9cc4; }
            QPushButton:disabled { color: #9ca3af; background: #eef0f3; border-color: #d7dbe0; }
            QPushButton#dangerButton:enabled { background: #b42318; color: white; border-color: #b42318; }
            QPushButton#dangerButton:hover:enabled { background: #912018; }
            QTabWidget::pane { background: white; border: 1px solid #d8dee8; border-radius: 6px; }
            QTabBar::tab { padding: 9px 18px; background: #e7ebf0; }
            QTabBar::tab:selected { background: white; color: #175cd3; }
            QTableWidget, QTreeWidget { background: white; border: 1px solid #d8dee8; gridline-color: #e5e7eb; }
            QHeaderView::section { background: #eef2f7; padding: 7px; border: 0; border-right: 1px solid #d8dee8; font-weight: 600; }
            QGroupBox { background: white; border: 1px solid #d8dee8; border-radius: 7px; margin-top: 12px; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; font-weight: 600; }
            """
        )

    def choose_root(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "選擇掃描根目錄")
        if name:
            self.start_scan(Path(name))

    def start_scan(self, root: Path) -> None:
        if self.scan_worker and self.scan_worker.isRunning():
            return
        self.root = root.resolve(strict=False)
        protected = self.paths.protected_directories() | {Path(__file__).resolve().parents[1]}
        self.deletion = DeletionService(self.root, protected)
        self.root_label.setText(str(self.root))
        self.items.clear()
        self.folder_previews.clear()
        self.selected_paths.clear()
        self._populate_tables()
        self.scan_worker = ScanWorker(self.root, self)
        self.scan_worker.completed.connect(self._scan_completed)
        self.scan_worker.failed.connect(self._scan_failed)
        self.scan_worker.finished.connect(self._scan_finished)
        self.scan_worker.start()
        self.scan_progress.show()
        self.stop_button.show()
        self.choose_button.setEnabled(False)
        self.statusBar().showMessage("正在掃描影片，掃描期間刪除功能已停用…")
        self._update_actions()

    def stop_scan(self) -> None:
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.requestInterruption()
            self.statusBar().showMessage("正在停止掃描…")

    def _scan_completed(self, items: object) -> None:
        self.items = list(items)
        self._build_folder_previews()
        self._populate_tables()
        self.statusBar().showMessage(f"掃描完成，共找到 {len(self.items)} 部影片", 8000)

    def _scan_failed(self, message: str) -> None:
        QMessageBox.critical(self, "掃描失敗", message)
        self.statusBar().showMessage("掃描失敗", 8000)

    def _scan_finished(self) -> None:
        self.scan_progress.hide()
        self.stop_button.hide()
        self.choose_button.setEnabled(True)
        self._update_actions()
        if self.scan_worker:
            self.scan_worker.deleteLater()
            self.scan_worker = None

    def _build_folder_previews(self) -> None:
        if not self.deletion:
            return
        for folder in sorted({item.parent for item in self.items}, key=str):
            try:
                self.folder_previews[folder] = self.deletion.preview(folder)
            except (DeletionSafetyError, FileNotFoundError, OSError):
                continue

    def _populate_tables(self) -> None:
        groups = duplicate_groups(self.items)
        duplicate_paths = {item.path for group in groups.values() for item in group}
        keep_paths = {
            keep.path
            for group in groups.values()
            if (keep := suggested_keep(group)) is not None
        }
        self._fill_table(self.all_table, self.items, keep_paths)
        self._fill_table(self.duplicate_table, [i for i in self.items if i.path in duplicate_paths], keep_paths)
        self.thumbnail_view.set_videos(self.items, self.selected_paths)
        if self.browser_stack.currentIndex() == 1:
            self.thumbnail_view.ensure_thumbnails()
        duplicate_count = sum(len(group) for group in groups.values())
        self.count_label.setText(
            f"影片：{len(self.items)}　重複番號群組：{len(groups)}　重複項目：{duplicate_count}"
        )
        self._update_selection_label()

    def _fill_table(self, table: QTableWidget, items: list[VideoItem], keep_paths: set[Path]) -> None:
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        for item in sorted(items, key=lambda i: ((i.code or "~"), str(i.path).lower())):
            row = table.rowCount()
            table.insertRow(row)
            checkbox = QCheckBox()
            checkbox.setProperty("folder", str(item.parent))
            checkbox.setChecked(item.parent in self.selected_paths)
            checkbox.stateChanged.connect(lambda state, p=item.parent: self._selection_changed(p, state))
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setAlignment(Qt.AlignCenter)
            wrapper_layout.addWidget(checkbox)
            table.setCellWidget(row, 0, wrapper)

            info = self.folder_previews.get(item.parent)
            status = self.status_by_folder.get(item.parent, "建議保留" if item.path in keep_paths else "")
            values = [
                item.code or "未辨識",
                item.path.name,
                str(item.parent),
                str(len(info.videos)) if info else "—",
                str(info.file_count) if info else "—",
                format_size(info.total_size) if info else "—",
                status,
            ]
            for col, value in enumerate(values, 1):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, str(item.path))
                if status == "建議保留" and col == 7:
                    cell.setForeground(QColor("#067647"))
                    font = QFont(cell.font())
                    font.setBold(True)
                    cell.setFont(font)
                table.setItem(row, col, cell)
        table.setUpdatesEnabled(True)

    def _selection_changed(self, path: Path, state: int) -> None:
        if state == Qt.Checked.value:
            self.selected_paths.add(path)
        else:
            self.selected_paths.discard(path)
        self._sync_checkboxes(path, path in self.selected_paths)
        self.thumbnail_view.sync_folder(path, path in self.selected_paths)
        self._update_selection_label()
        self._update_actions()

    def _sync_checkboxes(self, path: Path, checked: bool) -> None:
        for table in (self.duplicate_table, self.all_table):
            for row in range(table.rowCount()):
                wrapper = table.cellWidget(row, 0)
                checkbox = wrapper.findChild(QCheckBox) if wrapper else None
                if checkbox and Path(checkbox.property("folder")) == path and checkbox.isChecked() != checked:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(checked)
                    checkbox.blockSignals(False)

    def _thumbnail_selection_changed(self, path: Path, checked: bool) -> None:
        self._selection_changed(path, Qt.Checked.value if checked else Qt.Unchecked.value)

    def _toggle_browser_view(self, thumbnails: bool) -> None:
        self.browser_stack.setCurrentIndex(1 if thumbnails else 0)
        self.browser_view_button.setText("切換至詳細資料" if thumbnails else "切換至預覽圖")
        if thumbnails:
            self.thumbnail_view.ensure_thumbnails()
            if not self.thumbnail_service.ffmpeg:
                self.statusBar().showMessage(
                    "找不到 FFmpeg，目前顯示影片檔案圖示；雙擊仍可使用系統播放器開啟。",
                    8000,
                )

    def open_video(self, video_path: Path) -> None:
        if not video_path.is_file():
            QMessageBox.warning(self, "無法播放", f"影片檔案不存在：\n{video_path}")
            return
        try:
            os.startfile(str(video_path))
        except OSError as exc:
            QMessageBox.warning(self, "無法播放", f"無法使用系統播放器開啟影片：\n{exc}")

    def _update_selection_label(self) -> None:
        actual = self.deletion.normalize_targets(self.selected_paths) if self.deletion else []
        self.selection_label.setText(
            f"已選取 {len(self.selected_paths)} 個項目，實際刪除 {len(actual)} 個資料夾"
        )

    def clear_selection(self) -> None:
        self.selected_paths.clear()
        self._populate_tables()
        self._update_actions()

    def select_non_best(self) -> None:
        groups = duplicate_groups(self.items)
        for group in groups.values():
            keep = suggested_keep(group)
            for item in group:
                if keep is not None and item.path != keep.path:
                    self.selected_paths.add(item.parent)
        self._populate_tables()
        self._update_actions()

    def _selected_previews(self) -> list[FolderPreview]:
        if not self.deletion:
            return []
        previews: list[FolderPreview] = []
        for path in self.deletion.normalize_targets(self.selected_paths):
            previews.append(self.deletion.preview(path))
        return previews

    def preview_selected(self) -> None:
        try:
            previews = self._selected_previews()
        except (DeletionSafetyError, FileNotFoundError, OSError) as exc:
            QMessageBox.warning(self, "無法預覽", str(exc))
            return
        if not previews:
            QMessageBox.information(self, "預覽刪除內容", "請先勾選要處理的影片項目。")
            return
        PreviewDialog(previews, self).exec()

    def delete_selected(self) -> None:
        if not self.settings.enabled or not self.deletion or not self.root:
            return
        if self.scan_worker and self.scan_worker.isRunning():
            QMessageBox.information(self, "掃描進行中", "請等待掃描停止或完成後再刪除。")
            return
        try:
            previews = self._selected_previews()
        except (DeletionSafetyError, FileNotFoundError, OSError) as exc:
            QMessageBox.warning(self, "刪除已取消", str(exc))
            return
        if not previews:
            QMessageBox.information(self, "刪除", "請先勾選要刪除的項目。")
            return

        PreviewDialog(previews, self).exec()
        total_size = sum(p.total_size for p in previews)
        total_files = sum(p.file_count for p in previews)
        first = QMessageBox.warning(
            self,
            "第一階段確認：刪除摘要",
            f"即將處理 {len(previews)} 個資料夾、{total_files} 個檔案，總大小 {format_size(total_size)}。\n\n"
            "請再次確認實際路徑與內容。",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if first != QMessageBox.Ok:
            return

        permanent = self.settings.safe_permanent_delete()
        confirm = ConfirmationDialog(previews, self.root, permanent, self)
        if confirm.exec() != QDialog.Accepted:
            return

        results = self.deletion.delete([p.path for p in previews], permanent=permanent)
        self.delete_logger.record_many(results, "permanent" if permanent else "recycle_bin")
        successful = {
            result.path
            for result in results
            if result.status in {DeleteStatus.SUCCESS_RECYCLE, DeleteStatus.SUCCESS_PERMANENT}
        }
        for result in results:
            self.status_by_folder[result.path] = result.status.value
        self.items = [
            item for item in self.items
            if not any(item.path.is_relative_to(folder) for folder in successful)
        ]
        self.selected_paths.difference_update(successful)
        for folder in successful:
            self.folder_previews.pop(folder, None)
        self._populate_tables()

        success_count = len(successful)
        skipped_count = sum(r.status == DeleteStatus.SKIPPED for r in results)
        failed_count = len(results) - success_count - skipped_count
        summary = QMessageBox(self)
        summary.setWindowTitle("處理完成")
        summary.setIcon(QMessageBox.Information if failed_count == 0 else QMessageBox.Warning)
        summary.setText(
            f"處理完成\n\n成功：{success_count} 個資料夾\n"
            f"失敗：{failed_count} 個資料夾\n略過：{skipped_count} 個資料夾"
        )
        details = summary.addButton("查看詳細結果", QMessageBox.ActionRole)
        summary.addButton("關閉", QMessageBox.AcceptRole)
        summary.exec()
        if summary.clickedButton() is details:
            ResultDialog(results, self).exec()

    def context_menu(self, table: QTableWidget, pos) -> None:
        row = table.rowAt(pos.y())
        if row < 0:
            return
        item = table.item(row, 3)
        if not item:
            return
        folder = Path(item.text())
        menu = QMenu(self)
        delete_action = menu.addAction("刪除此影片所在資料夾")
        preview_action = menu.addAction("預覽此資料夾內容")
        open_action = menu.addAction("在檔案總管中開啟資料夾")
        menu.addSeparator()
        cancel_action = menu.addAction("取消選取")
        delete_action.setEnabled(self.settings.enabled and not self._scan_running())
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == delete_action:
            self.selected_paths.add(folder)
            self._populate_tables()
            self.delete_selected()
        elif chosen == preview_action and self.deletion:
            try:
                PreviewDialog([self.deletion.preview(folder)], self).exec()
            except (DeletionSafetyError, FileNotFoundError, OSError) as exc:
                QMessageBox.warning(self, "無法預覽", str(exc))
        elif chosen == open_action:
            os.startfile(str(folder))
        elif chosen == cancel_action:
            self.selected_paths.discard(folder)
            self._populate_tables()

    def _delete_enabled_changed(self, checked: bool) -> None:
        self.settings.enabled = checked
        self._update_actions()

    def choose_ffmpeg_directory(self) -> None:
        initial = str(self.configured_ffmpeg_dir or Path.home())
        value = QFileDialog.getExistingDirectory(self, "選擇 FFmpeg 工具資料夾", initial)
        if not value:
            return
        directory = Path(value).resolve(strict=False)
        if not ffmpeg_directory_complete(directory):
            QMessageBox.warning(
                self,
                "FFmpeg 工具不完整",
                "選擇的資料夾必須同時包含 ffmpeg.exe 與 ffprobe.exe。",
            )
            self._configure_ffmpeg_from_saved_or_default()
            return
        tools = self.thumbnail_service.configure([directory])
        self.configured_ffmpeg_dir = directory
        try:
            self.user_settings.save_ffmpeg_directory(directory)
        except OSError as exc:
            QMessageBox.warning(self, "無法儲存設定", str(exc))
        self._update_ffmpeg_ui()
        self.statusBar().showMessage("FFmpeg 工具路徑已更新。", 5000)

    def clear_ffmpeg_directory(self) -> None:
        self.configured_ffmpeg_dir = None
        try:
            self.user_settings.save_ffmpeg_directory(None)
        except OSError as exc:
            QMessageBox.warning(self, "無法儲存設定", str(exc))
        self._configure_ffmpeg_from_saved_or_default()
        self._update_ffmpeg_ui()

    def _configure_ffmpeg_from_saved_or_default(self) -> FFmpegTools:
        candidates = []
        if self.configured_ffmpeg_dir:
            candidates.append(self.configured_ffmpeg_dir)
        candidates.extend(
            [self.paths.ffmpeg_dir, Path(__file__).resolve().parents[1] / "tools" / "ffmpeg"]
        )
        return self.thumbnail_service.configure(candidates)

    def _update_ffmpeg_ui(self) -> None:
        tools = self.thumbnail_service.tools
        if self.configured_ffmpeg_dir:
            self.ffmpeg_path_edit.setText(str(self.configured_ffmpeg_dir))
        elif tools.complete and tools.ffmpeg:
            self.ffmpeg_path_edit.setText(str(tools.ffmpeg.parent))
        else:
            self.ffmpeg_path_edit.clear()
        if tools.complete:
            source = "使用者指定" if self.configured_ffmpeg_dir else "自動偵測"
            self.ffmpeg_status_label.setText(
                f"✓ {source}成功：{tools.ffmpeg.parent}\nffmpeg.exe 與 ffprobe.exe 均可用。"
            )
            self.ffmpeg_status_label.setStyleSheet("color: #067647;")
        else:
            self.ffmpeg_status_label.setText(
                "尚未找到完整的 FFmpeg 工具。縮圖會先顯示檔案圖示，其他瀏覽與刪除功能不受影響。"
            )
            self.ffmpeg_status_label.setStyleSheet("color: #b42318;")

    def _mode_changed(self) -> None:
        if self.permanent_radio.isChecked():
            answer = QMessageBox.warning(
                self,
                "啟用永久刪除模式",
                "永久刪除無法復原。確定要切換到此模式嗎？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.recycle_radio.blockSignals(True)
                self.recycle_radio.setChecked(True)
                self.recycle_radio.blockSignals(False)
                self.permanent_radio.blockSignals(True)
                self.permanent_radio.setChecked(False)
                self.permanent_radio.blockSignals(False)
        self.settings.use_recycle_bin = self.recycle_radio.isChecked()
        self.settings.permanent_delete = self.permanent_radio.isChecked()

    def _scan_running(self) -> bool:
        return bool(self.scan_worker and self.scan_worker.isRunning())

    def _update_actions(self) -> None:
        enabled = self.settings.enabled and bool(self.root) and not self._scan_running()
        has_selection = bool(self.selected_paths)
        self.delete_button.setEnabled(enabled and has_selection)
        self.preview_button.setEnabled(bool(self.root) and has_selection and not self._scan_running())
        self.select_other_button.setEnabled(bool(self.items) and not self._scan_running())
        for index, button in enumerate(getattr(self, "result_action_clones", [])):
            button.setEnabled((enabled if index == 0 else bool(self.root)) and has_selection and not self._scan_running())

    def closeEvent(self, event) -> None:
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.requestInterruption()
            self.scan_worker.wait(3000)
        super().closeEvent(event)
