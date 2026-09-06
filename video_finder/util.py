from __future__ import annotations

import os
import subprocess
import sys


def human_size(n):
    """Format a byte count into a short, human readable string."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    if n < 0:
        n = 0.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def open_with_default(path):
    """Open *path* with the OS default application. Returns True on success."""
    if not path or not os.path.exists(path):
        return False
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def open_folder(path, select_file=False):
    """Open a file's folder in the OS file manager.

    When *select_file* is True and *path* is a file, the manager highlights it.
    Works for local paths and mapped network (SMB) drive letters.
    """
    if not path:
        return False
    try:
        if os.name == "nt":
            if select_file and os.path.isfile(path):
                # explorer.exe needs "/select," glued to the quoted path as a
                # single argument; the space-separated form opens the desktop
                # instead of the file's folder. The glued form is reliable for
                # both local drives and mapped network (SMB) drive letters.
                subprocess.Popen(["explorer", '/select,"%s"' % path])
            else:
                target = path if os.path.isdir(path) else os.path.dirname(path)
                os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            if select_file and os.path.isfile(path):
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["open", path if os.path.isdir(path) else os.path.dirname(path)])
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
        return True
    except Exception:
        return False


def short_path(p, width=46):
    """Shorten a long path for compact display."""
    if not p:
        return ""
    p = p.replace("\\", "/")
    if len(p) > width:
        return "…" + p[-width + 1:]
    return p
