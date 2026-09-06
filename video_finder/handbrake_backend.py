from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time

from .config import app_data_dir

# Windows: keep a console window from flashing for HandBrake subprocesses.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Encoder choices offered in the settings dialog (ShortName values accepted
# by HandBrakeCLI --encoder). SVT-AV1 and x265 are the "modern" targets.
ENCODER_CHOICES = [
    ("svt_av1_10bit", "AV1 10-bit (SVT)"),
    ("svt_av1", "AV1 8-bit (SVT)"),
    ("x265_10bit", "HEVC 10-bit (x265)"),
    ("x265", "HEVC 8-bit (x265)"),
]

# Output container choices offered in the settings dialog. "mp4" is the
# default; encoded files are renamed so the extension matches the container.
CONTAINER_CHOICES = [
    ("mp4", "MP4 (.mp4)"),
    ("mkv", "MKV (.mkv)"),
]

# container (config value) -> HandBrakeCLI --format value
_CONTAINER_FORMAT = {"mp4": "av_mp4", "mkv": "av_mkv"}

# Per-encoder extra flags (preset / tune), matching the recipe used in the
# GUI-exported SAMPLE.json queue (AV1 preset 8 + vq tune).
_ENCODER_OPTS = {
    "svt_av1_10bit": ["--encoder-preset", "8", "--encoder-tune", "vq"],
    "svt_av1": ["--encoder-preset", "8", "--encoder-tune", "vq"],
    "x265_10bit": ["--encoder-preset", "slower"],
    "x265": ["--encoder-preset", "slower"],
}

# Containers each encoder cannot mux into.
_UNSUPPORTED = {
    "svt_av1_10bit": {"avi", "asf", "wmv", "mpg", "mpeg", "ts", "m2ts", "3gp", "vob"},
    "svt_av1": {"avi", "asf", "wmv", "mpg", "mpeg", "ts", "m2ts", "3gp", "vob"},
    "x265_10bit": {"webm", "flv", "ts", "m2ts", "3gp", "avi", "asf", "wmv"},
    "x265": {"webm", "flv", "ts", "m2ts", "3gp", "avi", "asf", "wmv"},
}

# ext -> HandBrakeCLI --format value; None = auto-detected from file name.
# (Legacy: used only by unsupported_reason(); encode_command now takes an
# explicit output container.)
_FORMAT_BY_EXT = {
    "mp4": "av_mp4", "m4v": "av_mp4", "mov": "av_mp4",
    "mkv": "av_mkv", "webm": "av_webm",
}


def candidate_handbrake_paths(cfg):
    """Candidate locations for HandBrakeCLI, in priority order."""
    exe = "HandBrakeCLI.exe" if os.name == "nt" else "HandBrakeCLI"
    paths = []
    if cfg.handbrake_path:
        paths.append(cfg.handbrake_path)
    # If the user pointed at the HandBrake folder, resolve the CLI inside it.
    if cfg.handbrake_path and os.path.isdir(cfg.handbrake_path):
        paths.append(os.path.join(cfg.handbrake_path, exe))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(os.path.join(meipass, exe))
        paths.append(os.path.join(meipass, "handbrake", exe))
    base = app_data_dir()
    paths.append(os.path.join(base, exe))
    paths.append(os.path.join(base, "handbrake", exe))
    paths.append(os.path.join(base, "HandBrake", exe))
    if os.name == "nt":
        for root in (r"C:\Program Files\HandBrake",
                    r"C:\Program Files (x86)\HandBrake"):
            paths.append(os.path.join(root, exe))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            paths.append(os.path.join(local, "Programs", "HandBrake", exe))
            # HandBrake >= 1.11 ships the CLI as a separate winget package.
            winget_links = os.path.join(
                local, "Microsoft", "WinGet", "Links", exe)
            paths.append(winget_links)
            packages = os.path.join(local, "Microsoft", "WinGet", "Packages")
            try:
                import glob
                for pattern in (
                        os.path.join(packages, "HandBrake.HandBrake.CLI*",
                                     exe),
                        os.path.join(packages, "HandBrake*", exe)):
                    paths.extend(sorted(glob.glob(pattern), reverse=True))
            except Exception:  # noqa: BLE001
                pass
    found = shutil.which("HandBrakeCLI")
    if found:
        paths.append(found)
    return paths


def find_handbrake(cfg):
    for path in candidate_handbrake_paths(cfg):
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def handbrake_version(cli_path):
    """First line of `HandBrakeCLI --version` output, or '' on failure."""
    if not cli_path:
        return ""
    try:
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                  "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = _NO_WINDOW
        proc = subprocess.run([cli_path, "--version"], timeout=30, **kwargs)
        text = (proc.stdout or proc.stderr or b"").decode("utf-8", "ignore")
        for ln in text.splitlines():
            ln = ln.strip()
            # Prefer the bare "HandBrake 1.11.2" line; newer builds print
            # several log lines before it.
            if re.match(r"^HandBrake\s+\d", ln):
                return ln
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[0] if lines else ""
    except Exception:
        return ""


def temp_output_path(src_path, container="mp4"):
    """Unique temp destination next to *src_path* (same drive = fast rename).

    The temp file uses the *output* container's extension, since the final
    encode is renamed to match the configured output format.
    """
    base = os.path.splitext(src_path)[0]
    return f"{base}.hfout-{int(time.time() * 1000)}.{container.lower()}"


def encode_command(cli_path, src_path, out_path, encoder, quality,
                   container="mp4"):
    """Build the HandBrakeCLI argument list for one input file.

    *container* is the configured output format ("mp4" or "mkv"); the
    source container is irrelevant, HandBrake demuxes anything it can read.
    """
    fmt = _CONTAINER_FORMAT.get(container, "av_mp4")
    cmd = [cli_path,
           "--json",
           "-i", src_path,
           "-o", out_path,
           "-e", encoder,
           "-q", str(quality),
           "--audio-copy-mask", "aac,ac3,eac3,truehd,dts,dtshd,mp2,mp3,opus,vorbis,flac,alac",
           "-E", "copy",
           # If a track cannot be copied as-is (e.g. opus into MP4),
           # re-encode it to AAC instead of failing.
           "--audio-fallback", "av_aac"]
    for flag in _ENCODER_OPTS.get(encoder, []):
        cmd.extend([flag])
    cmd.extend(["-f", fmt])
    if fmt == "av_mp4":
        cmd.append("--optimize")
    return cmd


def unsupported_reason(ext, encoder):
    """Return a short reason string when *encoder* can't mux into *ext*."""
    ext = ext.lower().lstrip(".")
    if ext in _UNSUPPORTED.get(encoder, set()):
        return f"{encoder} 不支援 .{ext} 容器,請先將檔案改為 mp4 / mkv"
    return ""


class ProgressReader:
    """Incremental parser for HandBrakeCLI --json progress output.

    HandBrake (1.11 and current builds) prints multi-line blocks such as:

        Progress: {
            "State": "WORKING",
            "Working": { "Progress": 0.42, ... }
        }

    and a final block with "State": "WORKDONE". Feed one stdout line at a
    time; feed() returns an int percent (0-100) whenever a complete
    progress block has been parsed, otherwise None. Legacy single-line
    JSON objects with a top-level "progress" key are also accepted.
    """

    def __init__(self):
        self._buf = None

    def feed(self, line):
        stripped = line.strip()
        if self._buf is None:
            if stripped.startswith("{") and stripped.endswith("}"):
                # Legacy single-line JSON object.
                return self._parse(stripped)
            if stripped.endswith("{"):
                self._buf = stripped
            return None
        self._buf += "\n" + stripped
        if self._buf.count("{") > self._buf.count("}"):
            return None  # block not complete yet
        block, self._buf = self._buf, None
        return self._parse(block)

    @staticmethod
    def _parse(block):
        text = block[block.index("{"):]
        # Tolerate trailing commas (defensive; most builds emit clean JSON).
        text = re.sub(r",\s*}", "}", text)
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        state = str(obj.get("State", "")).upper()
        if state == "WORKDONE":
            return 100
        if state == "WORKING":
            progress = (obj.get("Working") or {}).get("Progress")
        else:
            progress = obj.get("progress")
        try:
            return max(0, min(100, int(float(progress) * 100)))
        except (TypeError, ValueError):
            return None


def replace_original(src_path, out_path, keep_backup, target_ext=None):
    """Replace *src_path* with the finished encode.

    When *target_ext* (the output container, e.g. "mp4") differs from the
    source extension, the finished encode is renamed to keep the same base
    name with the new extension (e.g. clip.mkv -> clip.mp4). The backup
    always keeps the original file name.

    Returns (ok: bool, detail: str, final_path: str).
    """
    if not os.path.isfile(out_path) or os.path.getsize(out_path) <= 0:
        return False, "輸出檔案不存在或為空", ""
    if not os.path.isfile(src_path):
        return False, "原檔案已不存在", ""
    src_ext = os.path.splitext(src_path)[1].lstrip(".").lower()
    final_path = src_path
    if target_ext and target_ext.lower() != src_ext:
        base = os.path.splitext(src_path)[0]
        final_path = f"{base}.{target_ext.lower()}"
        if os.path.exists(final_path):
            return (False,
                    f"目標檔案已存在:{os.path.basename(final_path)}", "")
    if keep_backup:
        backup = src_path + ".hborig"
        n = 1
        while os.path.exists(backup):
            backup = f"{src_path}.{n}.hborig"
            n += 1
        try:
            os.replace(src_path, backup)
        except OSError as exc:
            return False, f"備份原檔案失敗:{exc}", ""
    try:
        os.replace(out_path, final_path)
    except OSError as exc:
        return False, f"替換原檔案失敗:{exc}", ""
    return True, "", final_path
