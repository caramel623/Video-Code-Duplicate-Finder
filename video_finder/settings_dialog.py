from __future__ import annotations

import os
from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from .handbrake_backend import (
    ENCODER_CHOICES,
    candidate_handbrake_paths,
    find_handbrake,
    handbrake_version,
)


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
        self.resize(580, 780)
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

        # ---- handbrake ------------------------------------------------------
        hb_group = QGroupBox("HandBrake(轉碼用)")
        hb_layout = QVBoxLayout(hb_group)
        hb_row = QHBoxLayout()
        self.handbrake_edit = QLineEdit()
        self.handbrake_edit.setPlaceholderText(
            "留空 = 自動偵測(優先使用設定路徑,再試標準安裝位置與 PATH)")
        self.handbrake_edit.setText(self.cfg.handbrake_path)
        self.handbrake_browse = QPushButton("瀏覽...")
        self.handbrake_browse.setProperty("variant", "secondary")
        self.handbrake_browse.clicked.connect(self._browse_handbrake)
        hb_row.addWidget(self.handbrake_edit, 1)
        hb_row.addWidget(self.handbrake_browse)
        enc_row = QHBoxLayout()
        enc_row.addWidget(QLabel("目標編碼器"))
        self.handbrake_enc = QComboBox()
        for value, label in ENCODER_CHOICES:
            self.handbrake_enc.addItem(label, value)
        idx = self.handbrake_enc.findData(self.cfg.handbrake_encoder)
        self.handbrake_enc.setCurrentIndex(max(idx, 0))
        enc_row.addWidget(self.handbrake_enc, 1)
        enc_row.addWidget(QLabel("品質"))
        self.handbrake_quality = QSpinBox()
        self.handbrake_quality.setRange(1, 60)
        self.handbrake_quality.setValue(self.cfg.handbrake_quality)
        enc_row.addWidget(self.handbrake_quality, 1)
        self.handbrake_backup = QCheckBox("轉碼完成後備份原檔(加入 .hborig)")
        self.handbrake_backup.setChecked(self.cfg.handbrake_keep_backup)
        self.handbrake_status = QLabel("")
        self.handbrake_status.setObjectName("Muted")
        self.handbrake_status.setWordWrap(True)
        hb_layout.addLayout(hb_row)
        hb_layout.addLayout(enc_row)
        hb_layout.addWidget(self.handbrake_backup)
        hb_layout.addWidget(self.handbrake_status)
        root.addWidget(hb_group)
        self._refresh_handbrake_status()

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
        self.chk_codec = QCheckBox("編碼掃描:預設只看非 AV1/HEVC 影片")
        self.chk_codec.setChecked(self.cfg.codec_non_modern_only)
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

    # ---- handbrake ------------------------------------------------------------
    def _browse_handbrake(self):
        start = os.path.dirname(self.handbrake_edit.text()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 HandBrakeCLI.exe", start,
            "HandBrake CLI (HandBrakeCLI.exe);;執行檔 (*.exe)")
        if path:
            self.handbrake_edit.setText(path)
            self._refresh_handbrake_status()

    def _refresh_handbrake_status(self):
        cfg = self.cfg
        cfg.handbrake_path = self.handbrake_edit.text().strip()
        resolved = find_handbrake(cfg)
        if resolved:
            self.handbrake_status.setText(f"將使用:{resolved}\n{handbrake_version(resolved)}")
        else:
            self.handbrake_status.setText(
                "未找到 HandBrakeCLI。請先安裝 HandBrake 並在上方指定 "
                "HandBrakeCLI.exe 的位置。")

    # ---- save ----------------------------------------------------------------
    def _save(self):
        self.cfg.ffmpeg_path = self.cfg.ffmpeg_path.strip()
        self.cfg.handbrake_path = self.handbrake_edit.text().strip()
        self.cfg.handbrake_encoder = self.handbrake_enc.currentData()
        self.cfg.handbrake_quality = self.handbrake_quality.value()
        self.cfg.handbrake_keep_backup = self.handbrake_backup.isChecked()
        self.cfg.thumbnail_seconds = self.thumb_seconds.value()
        self.cfg.thumbnail_width = self.thumb_width.value()
        self.cfg.strip_disc = self.chk_disc.isChecked()
        self.cfg.strip_quality = self.chk_quality.isChecked()
        self.cfg.show_duplicates_only = self.chk_dups.isChecked()
        self.cfg.codec_non_modern_only = self.chk_codec.isChecked()
        self.cfg.save()
        self.accept()
