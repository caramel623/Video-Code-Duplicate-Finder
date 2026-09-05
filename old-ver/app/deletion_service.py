from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

try:
    from send2trash import send2trash
except ImportError:  # Lets core safety tests run before optional runtime dependencies are installed.
    def send2trash(path: str) -> None:
        raise RuntimeError("Send2Trash 尚未安裝；請執行 pip install -r requirements.txt")

from .code_parser import extract_codes
from .models import VideoItem
from .scanner import VIDEO_EXTENSIONS, is_link_or_reparse


class DeleteStatus(str, Enum):
    SUCCESS_RECYCLE = "已移至資源回收筒"
    SUCCESS_PERMANENT = "已永久刪除"
    SKIPPED = "略過"
    SAFETY_REJECTED = "安全檢查拒絕"
    NOT_FOUND = "路徑不存在"
    PERMISSION_DENIED = "無權限"
    IN_USE = "檔案正在使用"
    RECYCLE_FAILED = "資源回收筒操作失敗"
    ERROR = "其他錯誤"


@dataclass
class FolderPreview:
    path: Path
    videos: list[Path] = field(default_factory=list)
    other_files: list[Path] = field(default_factory=list)
    subfolder_count: int = 0
    file_count: int = 0
    total_size: int = 0
    codes: set[str] = field(default_factory=set)
    has_unrecognized_video: bool = False

    @property
    def has_multiple_codes(self) -> bool:
        return len(self.codes) > 1


@dataclass
class DeleteResult:
    path: Path
    status: DeleteStatus
    preview: FolderPreview | None = None
    error: str = ""


class DeletionSafetyError(ValueError):
    pass


class DeletionService:
    """Folder deletion with path containment and reparse-point protections."""

    def __init__(self, scan_root: Path, protected_paths: Iterable[Path] = ()):
        self.scan_root = self._resolve(scan_root)
        self.protected_paths = {self._resolve(p) for p in protected_paths if p}

    @staticmethod
    def _resolve(path: Path) -> Path:
        if not str(path).strip():
            raise DeletionSafetyError("空白或無法解析的路徑")
        try:
            return Path(path).resolve(strict=False)
        except OSError as exc:
            raise DeletionSafetyError(f"無法正規化路徑：{exc}") from exc

    def validate_target(self, target: Path) -> Path:
        target = self._resolve(target)
        if not target.exists():
            raise FileNotFoundError(target)
        if not target.is_dir() or is_link_or_reparse(target):
            raise DeletionSafetyError("目標必須是非連結的資料夾")
        if target.parent == target:
            raise DeletionSafetyError("禁止刪除磁碟或 UNC 根目錄")
        if target == self.scan_root:
            raise DeletionSafetyError("禁止刪除掃描根目錄")
        try:
            target.relative_to(self.scan_root)
        except ValueError as exc:
            raise DeletionSafetyError("目標不在掃描根目錄之下") from exc
        for protected in self.protected_paths:
            if target == protected or protected in target.parents:
                raise DeletionSafetyError("目標是受保護的程式資料夾")
        # Avoid common catastrophic folders even if incorrectly chosen as scan root.
        home = self._resolve(Path.home())
        windows = self._resolve(Path(os.environ.get("WINDIR", r"C:\\Windows")))
        if target == home or target == windows or windows in target.parents:
            raise DeletionSafetyError("禁止刪除系統或使用者家目錄")
        return target

    def normalize_targets(self, targets: Iterable[Path]) -> list[Path]:
        unique: set[Path] = set()
        for target in targets:
            try:
                unique.add(self.validate_target(target))
            except (DeletionSafetyError, FileNotFoundError):
                continue
        return [p for p in sorted(unique, key=lambda x: (len(x.parts), str(x).lower()))
                if not any(parent != p and p.is_relative_to(parent) for parent in unique)]

    def preview(self, target: Path) -> FolderPreview:
        target = self.validate_target(target)
        data = FolderPreview(path=target)
        for current, dirs, files in os.walk(target, followlinks=False):
            current_path = Path(current)
            link_dirs = [d for d in dirs if is_link_or_reparse(current_path / d)]
            data.subfolder_count += len(dirs)
            # Links count as an entry but are never followed.
            dirs[:] = [d for d in dirs if d not in link_dirs]
            for filename in files:
                path = current_path / filename
                data.file_count += 1
                try:
                    if not is_link_or_reparse(path):
                        data.total_size += path.stat().st_size
                except OSError:
                    pass
                if path.suffix.lower() in VIDEO_EXTENSIONS:
                    data.videos.append(path)
                    codes = extract_codes(path.stem)
                    if codes:
                        data.codes.update(codes)
                    else:
                        data.has_unrecognized_video = True
                else:
                    data.other_files.append(path)
        return data

    def delete(self, targets: Iterable[Path], *, permanent: bool = False,
               recycler: Callable[[str], None] = send2trash) -> list[DeleteResult]:
        results: list[DeleteResult] = []
        valid: set[Path] = set()
        seen: set[Path] = set()
        for raw in targets:
            try:
                resolved = self._resolve(raw)
                if resolved in seen:
                    continue
                seen.add(resolved)
                valid.add(self.validate_target(resolved))
            except FileNotFoundError:
                results.append(DeleteResult(Path(raw), DeleteStatus.NOT_FOUND))
            except DeletionSafetyError as exc:
                results.append(DeleteResult(Path(raw), DeleteStatus.SAFETY_REJECTED, error=str(exc)))

        ordered = sorted(valid, key=lambda path: (len(path.parts), str(path).lower()))
        actual: list[Path] = []
        for path in ordered:
            parent = next((candidate for candidate in actual if path.is_relative_to(candidate)), None)
            if parent is not None:
                results.append(
                    DeleteResult(path, DeleteStatus.SKIPPED, error=f"已由上層刪除目標涵蓋：{parent}")
                )
            else:
                actual.append(path)

        for raw in actual:
            preview: FolderPreview | None = None
            try:
                preview = self.preview(raw)  # validates again immediately before action
                if permanent:
                    shutil.rmtree(raw)
                    status = DeleteStatus.SUCCESS_PERMANENT
                else:
                    recycler(str(raw))
                    status = DeleteStatus.SUCCESS_RECYCLE
                results.append(DeleteResult(raw, status, preview))
            except FileNotFoundError:
                results.append(DeleteResult(raw, DeleteStatus.NOT_FOUND, preview))
            except DeletionSafetyError as exc:
                results.append(DeleteResult(raw, DeleteStatus.SAFETY_REJECTED, preview, str(exc)))
            except PermissionError as exc:
                results.append(DeleteResult(raw, DeleteStatus.PERMISSION_DENIED, preview, str(exc)))
            except OSError as exc:
                results.append(DeleteResult(raw, DeleteStatus.IN_USE, preview, str(exc)))
            except Exception as exc:
                results.append(DeleteResult(raw, DeleteStatus.RECYCLE_FAILED if not permanent else DeleteStatus.ERROR, preview, str(exc)))
        return results


def suggested_keep(items: Iterable[VideoItem]) -> VideoItem | None:
    return max(items, key=lambda item: (item.pixels, item.duration, item.size, item.bitrate, item.modified_ns), default=None)
