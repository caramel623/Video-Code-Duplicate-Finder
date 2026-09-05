from pathlib import Path

import pytest

from app.scanner import scan_videos


def test_scanner_finds_video_and_ignores_non_video(tmp_path: Path):
    (tmp_path / "ABC-123.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    items = scan_videos(tmp_path)
    assert [(i.path.name, i.code) for i in items] == [("ABC-123.mp4", "ABC-123")]


def test_scanner_does_not_follow_directory_symlink(tmp_path: Path):
    root = tmp_path / "root"; root.mkdir()
    outside = tmp_path / "outside-videos"; outside.mkdir()
    (outside / "DEF-456.mp4").write_bytes(b"x")
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable for this test user")
    assert scan_videos(root) == []
