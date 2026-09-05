from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from video_finder.config import Config  # noqa: E402
from video_finder.ffmpeg_backend import extract_thumb, find_ffmpeg  # noqa: E402
from video_finder.main_window import MainWindow  # noqa: E402
from video_finder.scanner import VideoFile, group_files  # noqa: E402
from video_finder.workers import thumb_cache_path  # noqa: E402

EXTS = (".mkv", ".mp4", ".wmv", ".avi")
ROOT = "test_videos"

files = []
for dirpath, _dirs, filenames in os.walk(ROOT):
    for name in sorted(filenames):
        if name.lower().endswith(EXTS):
            path = os.path.join(dirpath, name)
            st = os.stat(path)
            files.append(VideoFile(path=path, size=st.st_size, mtime=st.st_mtime))

cfg = Config.load()
groups = group_files(files, cfg)

print("== 分組結果(片名已去除畫質/碟號) ==")
for group in groups:
    tag = "  [重複]" if group.is_duplicate else ""
    print(f"  [{len(group.files)}]{tag} {group.title}")
    for f in group.files:
        print(f"      - {f.path}")

by_title = {g.title: g for g in groups}
assert "AVOP-123" in by_title and len(by_title["AVOP-123"].files) == 2, "AVOP-123 兩個格式未合併"
assert by_title["AVOP-123"].is_duplicate, "AVOP-123 應為重複"
assert "090333_01" in by_title and len(by_title["090333_01"].files) == 2, "090333_01 碟號合併失敗"
assert by_title["090333_01"].is_segments and not by_title["090333_01"].is_duplicate, \
    "090333_01 同資料夾 CD 分段應不視為重複"
assert "LF-06" in by_title and len(by_title["LF-06"].files) == 1, "LF-06 唯一分組錯誤"
assert "080123-001" in by_title, "080123-001 分組錯誤"

# 跨資料夾的 CD 檔案仍視為重複
a = VideoFile(path=os.path.join(ROOT, "sub", "CD1", "ZZZ-999.CD1.mkv"), size=1, mtime=0)
b = VideoFile(path=os.path.join(ROOT, "other", "CD1", "ZZZ-999.CD2.mkv"), size=1, mtime=0)
g2 = group_files([a, b], cfg)
assert len(g2) == 1 and g2[0].is_duplicate, "跨資料夾的 CD 分段應視為重複"
print("scanner: OK")

# ---- build the main window (offscreen) -----------------------------------
window = MainWindow(cfg)
window.show()
app.processEvents()
print("MainWindow: built OK, tree cols =", window.tree.columnCount())

# 樹狀列 + 單擊更新預覽
window.files = files
window._apply_filter()
assert window.tree.topLevelItemCount() == len(window.groups), "樹狀列筆數錯誤"
root0 = window.tree.topLevelItem(0)
assert root0.childCount() == len(window.groups[0].files), "子節點(檔案)未建立"
window.tree.setCurrentItem(root0)
window._on_tree_selection()
assert window._selected_group() is window.groups[0], "選取群組錯誤"
second = window.tree.topLevelItem(1)
window.tree.setCurrentItem(second)
window._on_tree_selection()
assert window._selected_group() is window.groups[1], "換列未更新選取"
assert window.detail_title.text() == window.groups[1].title, "預覽標題未隨選取更新"
print("tree selection: OK")

# ---- generate a thumbnail for the real tiny video -------------------------
real = [f for f in files if f.path.endswith("AVOP-123.1080p.x264.mkv")][0]
ff = find_ffmpeg(cfg)
out = thumb_cache_path(real, cfg.thumbnail_seconds, cfg.thumbnail_width)
ok = extract_thumb(ff, real.path, out, 0.2, cfg.thumbnail_width)
print(f"thumbnail: ok={ok} size={os.path.getsize(out) if ok and os.path.exists(out) else '-'}")
assert ok, "FFmpeg 截圖失敗"

if window.thumb_worker is not None:
    window.thumb_worker.wait(15000)
    window.thumb_worker = None
app.processEvents()
print("ALL PASS")
sys.exit(0)