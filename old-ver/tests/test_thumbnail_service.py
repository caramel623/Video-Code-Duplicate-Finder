from app.thumbnail_service import ThumbnailService


def test_thumbnail_cache_key_changes_with_file_metadata(tmp_path):
    video = tmp_path / "ABC-123.mp4"
    video.write_bytes(b"one")
    service = ThumbnailService(tmp_path / "cache", [])
    first = service.cached_path(video)
    video.write_bytes(b"a different size")
    second = service.cached_path(video)
    assert first != second
    assert first.parent == tmp_path / "cache"


def test_thumbnail_generation_gracefully_falls_back_without_ffmpeg(tmp_path):
    video = tmp_path / "ABC-123.mp4"
    video.write_bytes(b"video")
    service = ThumbnailService(tmp_path / "cache", [])
    service.ffmpeg = None
    assert service.generate(video) is None
    assert not service.cache_dir.exists()
