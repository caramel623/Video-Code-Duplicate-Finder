from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FFmpegTools:
    ffmpeg: Path | None = None
    ffprobe: Path | None = None

    @property
    def complete(self) -> bool:
        return self.ffmpeg is not None and self.ffprobe is not None


def find_ffmpeg_tools(candidates: Iterable[Path]) -> FFmpegTools:
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    for candidate in candidates:
        directory = candidate if candidate.is_dir() else candidate.parent
        ffmpeg = directory / ffmpeg_name
        ffprobe = directory / ffprobe_name
        if ffmpeg.is_file() and ffprobe.is_file():
            return FFmpegTools(ffmpeg, ffprobe)
    bundled_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    bundled_dir = bundled_root / "tools" / "ffmpeg"
    bundled = FFmpegTools(bundled_dir / ffmpeg_name, bundled_dir / ffprobe_name)
    if bundled.complete and bundled.ffmpeg.is_file() and bundled.ffprobe.is_file():
        return bundled
    ffmpeg_found = shutil.which(ffmpeg_name)
    ffprobe_found = shutil.which(ffprobe_name)
    return FFmpegTools(
        Path(ffmpeg_found) if ffmpeg_found else None,
        Path(ffprobe_found) if ffprobe_found else None,
    )


class ThumbnailService:
    """Create deterministic, cached video previews without blocking the GUI thread."""

    def __init__(self, cache_dir: Path, ffmpeg_candidates: Iterable[Path] = ()):
        self.cache_dir = cache_dir
        self.tools = find_ffmpeg_tools(ffmpeg_candidates)
        self.ffmpeg = self.tools.ffmpeg

    def configure(self, candidates: Iterable[Path]) -> FFmpegTools:
        self.tools = find_ffmpeg_tools(candidates)
        self.ffmpeg = self.tools.ffmpeg
        return self.tools

    def cached_path(self, video_path: Path) -> Path:
        try:
            stat = video_path.stat()
            identity = f"{video_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        except OSError:
            identity = str(video_path.resolve(strict=False))
        digest = hashlib.sha1(identity.encode("utf-8", errors="surrogatepass")).hexdigest()
        return self.cache_dir / f"{digest}.jpg"

    def generate(self, video_path: Path) -> Path | None:
        if not self.ffmpeg or not video_path.is_file():
            return None
        output = self.cached_path(video_path)
        if output.is_file() and output.stat().st_size > 0:
            return output
        output.parent.mkdir(parents=True, exist_ok=True)
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        command = [
            str(self.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "00:00:05",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2",
            "-q:v",
            "3",
            "-y",
            str(output),
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=45,
                creationflags=creation_flags,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            output.unlink(missing_ok=True)
            return None
        if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)
            return None
        return output
