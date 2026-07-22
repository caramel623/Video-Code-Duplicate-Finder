from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .code_parser import extract_codes
from .models import VideoItem

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m2ts", ".mpg", ".mpeg", ".m4v"}


def is_link_or_reparse(path: Path) -> bool:
    """`is_junction` is available on supported Python/Windows versions."""
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def scan_videos(root: Path, should_cancel: Callable[[], bool] | None = None) -> list[VideoItem]:
    """Scan without following directory links/reparse points."""
    root = root.resolve(strict=True)
    items: list[VideoItem] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        if should_cancel and should_cancel():
            break
        # Do not descend into symlink/junction directories.
        dirs[:] = [d for d in dirs if not is_link_or_reparse(Path(current) / d)]
        for name in files:
            if should_cancel and should_cancel():
                return items
            path = Path(current) / name
            if path.suffix.lower() not in VIDEO_EXTENSIONS or is_link_or_reparse(path):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            codes = extract_codes(path.stem)
            items.append(VideoItem(path, codes[0] if codes else None, stat.st_size, modified_ns=stat.st_mtime_ns))
    return items


def duplicate_groups(items: list[VideoItem]) -> dict[str, list[VideoItem]]:
    groups: dict[str, list[VideoItem]] = {}
    for item in items:
        if item.code:
            groups.setdefault(item.code, []).append(item)
    return {code: group for code, group in groups.items() if len(group) > 1}
