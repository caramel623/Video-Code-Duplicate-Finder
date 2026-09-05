from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeleteSettings:
    enabled: bool = False
    use_recycle_bin: bool = True
    permanent_delete: bool = False

    def safe_permanent_delete(self) -> bool:
        """A corrupt/old config must never turn permanent deletion on."""
        return self.enabled and self.permanent_delete and not self.use_recycle_bin


class UserSettingsStore:
    """Persist non-destructive preferences only.

    Deletion enablement and permanent mode are intentionally never restored
    from disk, so a damaged or stale settings file cannot enable deletion.
    """

    def __init__(self, path: Path):
        self.path = path

    def load_ffmpeg_directory(self) -> Path | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            value = data.get("ffmpeg_directory", "")
            return Path(value).resolve(strict=False) if isinstance(value, str) and value.strip() else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def save_ffmpeg_directory(self, directory: Path | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"ffmpeg_directory": str(directory.resolve(strict=False)) if directory else ""}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
