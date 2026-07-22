from app.settings import UserSettingsStore


def test_ffmpeg_directory_round_trip(tmp_path):
    store = UserSettingsStore(tmp_path / "settings" / "settings.json")
    ffmpeg_dir = tmp_path / "FFmpeg 工具"
    ffmpeg_dir.mkdir()
    store.save_ffmpeg_directory(ffmpeg_dir)
    assert store.load_ffmpeg_directory() == ffmpeg_dir.resolve()


def test_corrupt_settings_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert UserSettingsStore(path).load_ffmpeg_directory() is None


def test_settings_never_persist_delete_mode(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"ffmpeg_directory": "", "permanent_delete": true, "enabled": true}',
        encoding="utf-8",
    )
    store = UserSettingsStore(path)
    assert store.load_ffmpeg_directory() is None
