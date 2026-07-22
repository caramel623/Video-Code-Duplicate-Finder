from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoItem:
    path: Path
    code: str | None
    size: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    bitrate: int = 0
    modified_ns: int = 0

    @property
    def parent(self) -> Path:
        return self.path.parent

    @property
    def pixels(self) -> int:
        return self.width * self.height
