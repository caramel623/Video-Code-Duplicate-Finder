from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

# Common video containers/codec extensions shipped by default.
DEFAULT_EXTENSIONS = [
    "mkv", "mp4", "wmv", "avi", "mov", "m4v", "flv", "webm",
    "ts", "m2ts", "mpg", "mpeg", "asf", "3gp",
]


def app_data_dir():
    """Directory where portable data (settings.json, thumbnail cache) lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Config:
    extensions: list = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    ffmpeg_path: str = ""
    thumbnail_seconds: int = 10
    thumbnail_width: int = 320
    strip_disc: bool = True
    strip_quality: bool = True
    show_duplicates_only: bool = False
    codec_non_modern_only: bool = True
    dup_scan_codecs: bool = False
    last_folder: str = ""
    handbrake_path: str = ""
    handbrake_encoder: str = "svt_av1_10bit"
    handbrake_quality: int = 32
    handbrake_container: str = "mp4"
    handbrake_keep_backup: bool = True

    @property
    def settings_file(self):
        return os.path.join(app_data_dir(), "settings.json")

    @classmethod
    def load(cls):
        cfg = cls()
        try:
            with open(cfg.settings_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key, value in data.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
        except Exception:
            pass
        return cfg

    def save(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as fh:
                json.dump(self.__dict__, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
