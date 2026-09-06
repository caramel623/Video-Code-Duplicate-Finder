from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QThread, Signal

from .config import app_data_dir
from .ffmpeg_backend import extract_thumb
from .scanner import VideoFile


def _cache_dir():
    path = os.path.join(app_data_dir(), "temp")
    os.makedirs(path, exist_ok=True)
    return path


def thumb_cache_path(vf: VideoFile, seconds, width):
    """Stable cache file for a thumbnail; invalidates on file/settings change."""
    basis = f"{vf.path}|{int(vf.mtime)}|{vf.size}|{seconds}|{width}"
    digest = hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()
    return os.path.join(_cache_dir(), digest + ".jpg")


def temp_dir():
    """Thumbnail temp folder (cleared on app exit)."""
    return os.path.join(app_data_dir(), "temp")


def clear_temp():
    """Remove all thumbnails from the temp folder."""
    import shutil

    path = temp_dir()
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
    except Exception:
        pass



class ScanWorker(QThread):
    progress = Signal(str, int)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, root, exts):
        super().__init__()
        self.root = root
        self.exts = {e.lower().lstrip(".") for e in exts if e}

    def run(self):
        try:
            files = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames.sort(key=str.lower)
                for name in sorted(filenames, key=str.lower):
                    ext = os.path.splitext(name)[1].lstrip(".").lower()
                    if ext not in self.exts:
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    files.append(VideoFile(path=path, size=st.st_size, mtime=st.st_mtime))
                self.progress.emit(dirpath, len(files))
            self.finished_ok.emit(files)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ThumbWorker(QThread):
    item_done = Signal(str, str, bool)
    all_done = Signal()

    def __init__(self, files, seconds, width, ffmpeg):
        super().__init__()
        self.files = files
        self.seconds = seconds
        self.width = width
        self.ffmpeg = ffmpeg

    def run(self):
        for vf in self.files:
            out = thumb_cache_path(vf, self.seconds, self.width)
            ok = os.path.exists(out) and os.path.getsize(out) > 0
            if not ok and self.ffmpeg:
                try:
                    ok = extract_thumb(self.ffmpeg, vf.path, out, self.seconds, self.width)
                except Exception:  # noqa: BLE001
                    ok = False
            self.item_done.emit(vf.path, out, ok)
        self.all_done.emit()


class CodecScanWorker(QThread):
    """Walk *root* and probe each video file's codecs with ffprobe."""
    progress = Signal(str, int, int)
    item_done = Signal(str, str, str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, root, exts, ffprobe):
        super().__init__()
        self.root = root
        self.exts = {e.lower().lstrip(".") for e in exts if e}
        self.ffprobe = ffprobe
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            from .ffmpeg_backend import probe_video_codecs
            results = []
            total = 0
            for dirpath, dirnames, filenames in os.walk(self.root):
                if self._stop:
                    break
                dirnames.sort(key=str.lower)
                for name in sorted(filenames, key=str.lower):
                    if self._stop:
                        break
                    ext = os.path.splitext(name)[1].lstrip(".").lower()
                    if ext not in self.exts:
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    total += 1
                    vcodec, acodec = (None, None)
                    if self.ffprobe:
                        try:
                            vcodec, acodec = probe_video_codecs(self.ffprobe, path)
                        except Exception:  # noqa: BLE001
                            vcodec, acodec = None, None
                    results.append({"path": path, "size": st.st_size,
                                    "vcodec": vcodec, "acodec": acodec})
                    self.item_done.emit(path, vcodec or "", acodec or "")
                    self.progress.emit(dirpath, total, len(results))
            self.finished_ok.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class FileCodecWorker(QThread):
    """Probe codecs for an explicit list of video files (no directory re-walk)."""
    item_done = Signal(str, str, str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, files, ffprobe):
        super().__init__()
        self.files = list(files)
        self.ffprobe = ffprobe
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            from .ffmpeg_backend import probe_video_codecs
            results = []
            for vf in self.files:
                if self._stop:
                    break
                vcodec, acodec = (None, None)
                if self.ffprobe:
                    try:
                        vcodec, acodec = probe_video_codecs(self.ffprobe, vf.path)
                    except Exception:  # noqa: BLE001
                        vcodec, acodec = None, None
                results.append({"path": vf.path, "size": vf.size,
                                "vcodec": vcodec, "acodec": acodec})
                self.item_done.emit(vf.path, vcodec or "", acodec or "")
            self.finished_ok.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
