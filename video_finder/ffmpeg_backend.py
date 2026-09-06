from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from .config import app_data_dir

# Windows: keep a console window from flashing for ffmpeg subprocesses.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(cmd, **kwargs):
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if os.name == "nt":
        kwargs.setdefault("creationflags", _NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


def candidate_ffmpeg_paths(cfg):
    paths = []
    if cfg.ffmpeg_path:
        paths.append(cfg.ffmpeg_path)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # PyInstaller one-file bundles extract here at runtime.
        paths.append(os.path.join(meipass, "ffmpeg.exe"))
        paths.append(os.path.join(meipass, "ffmpeg", "ffmpeg.exe"))
    base = app_data_dir()
    paths.append(os.path.join(base, "ffmpeg.exe"))
    paths.append(os.path.join(base, "ffmpeg", "ffmpeg.exe"))
    found = shutil.which("ffmpeg")
    if found:
        paths.append(found)
    return paths


def find_ffmpeg(cfg):
    for path in candidate_ffmpeg_paths(cfg):
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def find_ffprobe(ffmpeg_path):
    if not ffmpeg_path:
        return None
    candidate = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe")
    if os.name != "nt":
        candidate = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe")
    if os.path.isfile(candidate):
        return candidate
    found = shutil.which("ffprobe")
    return found


def ffmpeg_version(ffmpeg_path):
    if not ffmpeg_path:
        return ""
    try:
        proc = _run([ffmpeg_path, "-version"])
        lines = proc.stdout.decode("utf-8", "ignore").splitlines()
        return lines[0] if lines else ""
    except Exception:
        return ""


def probe_duration(video, ffprobe):
    """Return the media duration in seconds, or None when unavailable."""
    if not ffprobe or not video:
        return None
    try:
        proc = _run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", video])
        text = proc.stdout.decode("utf-8", "ignore").strip()
        return float(text) if text else None
    except Exception:
        return None


def extract_thumb(ffmpeg_path, video, out_path, at_seconds, width):
    """Grab one frame from *video* into *out_path*. Returns True on success."""
    if not ffmpeg_path:
        return False
    cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{max(at_seconds, 0):.2f}", "-i", video,
           "-frames:v", "1", "-vf", f"scale={width}:-2", out_path]
    proc = _run(cmd)
    if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return True
    # The requested time may be beyond the clip length; retry at the start.
    try:
        os.remove(out_path)
    except OSError:
        pass
    cmd[4] = "0.25"
    proc = _run(cmd)
    return proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


def probe_video_codecs(ffprobe, video):
    """Return (video_codec, audio_codecs) for *video* using ffprobe.

    *video_codec* is the first video stream codec name (e.g. "hevc", "av1",
    "h264") or None when no usable video stream is found.
    *audio_codecs* is a comma-joined list of audio stream codecs.
    """
    if not ffprobe:
        return None, None
    try:
        proc = _run([ffprobe, "-v", "error",
                    "-show_entries", "stream=codec_type,codec_name",
                    "-of", "json", video])
        data = json.loads(proc.stdout.decode("utf-8", "ignore") or "{}")
        video_codec = None
        audio = []
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type")
            codec_name = (stream.get("codec_name") or "").strip()
            if codec_type == "video" and video_codec is None and codec_name:
                video_codec = codec_name
            elif codec_type == "audio" and codec_name:
                audio.append(codec_name)
        return video_codec, (",".join(audio) if audio else None)
    except Exception:
        return None, None
