from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    cache_dir: Path
    settings_dir: Path
    database_dir: Path
    thumbnail_dir: Path
    ffmpeg_dir: Path
    settings_file: Path
    deletion_log: Path

    @classmethod
    def for_current_user(cls) -> "AppPaths":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "VideoCodeDuplicateFinder"
        paths = cls(
            data_dir=base,
            cache_dir=base / "cache",
            settings_dir=base / "settings",
            database_dir=base / "database",
            thumbnail_dir=base / "cache" / "thumbnails",
            ffmpeg_dir=base / "tools" / "ffmpeg",
            settings_file=base / "settings" / "settings.json",
            deletion_log=base / "logs" / "deletions.jsonl",
        )
        return paths

    def protected_directories(self) -> set[Path]:
        return {
            self.data_dir,
            self.cache_dir,
            self.settings_dir,
            self.database_dir,
            self.thumbnail_dir,
            self.ffmpeg_dir,
            self.deletion_log.parent,
        }
