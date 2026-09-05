from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .deletion_service import DeleteResult


class DeletionLogger:
    def __init__(self, path: Path):
        self.path = path

    def record_many(self, results: list[DeleteResult], mode: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            for result in results:
                preview = result.preview
                record = {
                    "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
                    "mode": mode,
                    "folder": str(result.path),
                    "parent": str(result.path.parent),
                    "file_count": preview.file_count if preview else None,
                    "total_size": preview.total_size if preview else None,
                    "result": result.status.value,
                    "error": result.error,
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
