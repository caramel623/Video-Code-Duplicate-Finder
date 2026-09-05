from __future__ import annotations

from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .config import DEFAULT_EXTENSIONS
from .ffmpeg_backend import candidate_ffmpeg_paths, ffmpeg_version, find_ffmpeg


def _parse_exts(text):
    out = []
    for part in text.replace(",", " ").replace(";", " ").split():
        part = part.strip().lstrip(".").lower()
        if part and part not in out:
            out.append(part)
    return out


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = replace(cfg)
        self.cfg.extensions = list(cfg.extensions)
        self.setWindowTitle("設定")
        self.resize(560, 640)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)

        # ---- video extensions -------------------------------------------
        ext_group = QGroupBox("影片格式(副檔名)")
        ext_layout = QVBoxLayout(ext_group)
        add_row = QHBoxLayout()
        self.ext_input = QLineEdit()
        self.ext_input.setPlaceholderText("新增格式,例如:mp5 或 vob, ts")
        self.ext_add = QPushButton("新增")
        self.ext_add.setProperty("variant", "secondary")
        self.ext_add.clicked.connect(self._add_ext)
        add_row.addWidget(self.ext_input, 1)
        add_row.addWidget(self.ext_add)
        self.ext_list = QListWidget()
        self.ext_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.ext_list.itemDoubleClicked.connect(lambda _: self._remove_ext())
        self.ext_remove = QPushButton("移除選取")
        self.ext_remove.setProperty("variant", "secondary")
        self.ext_remove.clicked.connect(self._remove_ext)
        self.ext_default = QPushButton("還原預設")
        self.ext_default.setProperty("variant", "secondary")
        self.ext_default.clicked.connect(self._reset_ext)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.ext_remove, 1)
        btn_row.addWidget(self.ext_default, 1)
        ext_layout.addLayout(add_row)
        ext_layout.addWidget(self.ext_list, 1)
        ext_layout.addLayout(btn_row)
        root.addWidget(ext_group)
        self._load_exts()

        # ---- ffmpeg -------------------------------------------------------
        ff_group = QGroupBox("FFmpeg(截圖用)")
        ff_layout = QVBoxLayout(ff_group)
        ff_row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setPlaceholderText("留空 = 自動偵測(優先使用程式資料夾內的 ffmpeg.exe)")
        self.ffmpeg_browse = QPushButton("瀏覽...")
        self.ffmpeg_browse.setProperty("variant", "secondary")
        self.ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ff_row.addWidget(self.ffmpeg_edit, 1)
        ff_row.addWidget(self.ffmpeg_browse)
        self.ffmpeg_status = QLabel("")
        self.ffmpeg_status.setObjectName("Muted")
        self.ffmpeg_status.setWordWrap(True)
        ff_layout.addLayout(ff_row)
        ff_layout.addWidget(self.ffmpeg_status)
        root.addWidget(ff_group)
        self._refresh_ffmpeg_status()

        # ---- options -------------------------------------------------------
        opt_group = QGroupBox("截圖與比對選項")
        opt_layout = QVBoxLayout(opt_group)
        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("截圖時間點(秒)"))
        self.thumb_seconds = QSpinBox()
        self.thumb_seconds.setRange(1, 3600)
        self.thumb_seconds.setValue(self.cfg.thumbnail_seconds)
        t_row.addWidget(self.thumb_seconds, 1)
        t_row.addWidget(QLabel("縮圖寬度"))
        self.thumb_width = QSpinBox()
        self.thumb_width.setRange(160, 1280)
        self.thumb_width.setSingleStep(16)
        self.thumb_width.setValue(self.cfg.thumbnail_width)
        t_row.addWidget(self.thumb_width, 1)
        opt_layout.addLayout(t_row)
        self.chk_disc = QCheckBox("將 CD1 / CD2 / 碟1… 視為同一部影片(不重複顯示)")
        self.chk_disc.setChecked(self.cfg.strip_disc)
        self.chk_quality = QCheckBox("比對時忽略畫質/編碼字樣(1080p、x264、BluRay、年份等)")
        self.chk_quality.setChecked(self.cfg.strip_quality)
        self.chk_dups = QCheckBox("預設只顯示重複影片(同片 ≥2 個檔案)")
        self.chk_dups.setChecked(self.cfg.show_duplicates_only)
        opt_layout.addWidget(self.chk_disc)
        opt_layout.addWidget(self.chk_quality)
        opt_layout.addWidget(self.chk_dups)
        root.addWidget(opt_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ---- extensions -------------------------------------------------------
    def _load_exts(self):
        self.ext_list.clear()
        for ext in sorted(self.cfg.extensions):
            QListWidgetItem("." + ext, self.ext_list)

    def _add_ext(self):
        new = _parse_exts(self.ext_input.text())
        for ext in new:
            if ext not in self.cfg.extensions:
                self.cfg.extensions.append(ext)
        self.ext_input.clear()
        self._load_exts()

    def _remove_ext(self):
        selected = [item.text()[1:] for item in self.ext_list.selectedItems()]
        self.cfg.extensions = [e for e in self.cfg.extensions if e not in selected]
        self._load_exts()

    def _reset_ext(self):
        self.cfg.extensions = list(DEFAULT_EXTENSIONS)
        self._load_exts()

    # ---- ffmpeg -------------------------------------------------------------
    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 ffmpeg.exe", "", "ffmpeg (*.exe)")
        if path:
            self.ffmpeg_edit.setText(path)
            self._refresh_ffmpeg_status()

    def _refresh_ffmpeg_status(self):
        cfg = self.cfg
        cfg.ffmpeg_path = self.ffmpeg_edit.text().strip()
        resolved = find_ffmpeg(cfg)
        if resolved:
            self.ffmpeg_status.setText(f"將使用:{resolved}\n{ffmpeg_version(resolved)}")
        else:
            tried = "、".join(p for p in candidate_ffmpeg_paths(cfg))
            self.ffmpeg_status.setText(f"未找到 FFmpeg。嘗試過:{tried}")

    # ---- save ----------------------------------------------------------------
    def _save(self):
        self.cfg.ffmpeg_path = self.cfg.ffmpeg_path.strip()
        self.cfg.thumbnail_seconds = self.thumb_seconds.value()
        self.cfg.thumbnail_width = self.thumb_width.value()
        self.cfg.strip_disc = self.chk_disc.isChecked()
        self.cfg.strip_quality = self.chk_quality.isChecked()
        self.cfg.show_duplicates_only = self.chk_dups.isChecked()
        self.cfg.save()
        self.accept()
