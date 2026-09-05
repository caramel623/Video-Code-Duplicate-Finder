from pathlib import Path

import pytest

from app.deletion_service import DeleteStatus, DeletionSafetyError, DeletionService


def make_folder(root: Path, name: str = "ABC-123") -> Path:
    folder = root / name; folder.mkdir(); (folder / "ABC-123.mp4").write_bytes(b"video"); (folder / "cover.jpg").write_bytes(b"image"); return folder


def test_deletes_only_direct_video_parent_to_recycler(tmp_path):
    folder = make_folder(tmp_path); calls = []
    result = DeletionService(tmp_path).delete([folder], recycler=calls.append)
    assert calls == [str(folder.resolve())]
    assert tmp_path.exists() and result[0].status == DeleteStatus.SUCCESS_RECYCLE


def test_rejects_scan_and_disk_root(tmp_path):
    service = DeletionService(tmp_path)
    with pytest.raises(DeletionSafetyError): service.validate_target(tmp_path)
    with pytest.raises(DeletionSafetyError): service.validate_target(Path(tmp_path.anchor))


def test_batch_records_safety_rejection(tmp_path):
    result = DeletionService(tmp_path).delete([tmp_path])
    assert result[0].status == DeleteStatus.SAFETY_REJECTED


def test_deduplicates_same_parent_and_nested_target(tmp_path):
    folder = make_folder(tmp_path); nested = folder / "Extras"; nested.mkdir()
    assert DeletionService(tmp_path).normalize_targets([folder, folder, nested]) == [folder.resolve()]


def test_batch_marks_nested_target_as_skipped(tmp_path):
    folder = make_folder(tmp_path); nested = folder / "Extras"; nested.mkdir()
    calls = []
    results = DeletionService(tmp_path).delete([nested, folder], recycler=calls.append)
    assert calls == [str(folder.resolve())]
    assert any(result.status == DeleteStatus.SKIPPED for result in results)


def test_preview_warns_about_multiple_codes_and_unrecognized(tmp_path):
    folder = make_folder(tmp_path); (folder / "DEF-456.mkv").write_bytes(b"x"); (folder / "random.mp4").write_bytes(b"x")
    preview = DeletionService(tmp_path).preview(folder)
    assert preview.has_multiple_codes and preview.has_unrecognized_video and preview.file_count == 4


def test_missing_after_confirmation_is_recorded(tmp_path):
    folder = make_folder(tmp_path); service = DeletionService(tmp_path); folder.rmdir() if False else None
    # Simulate a recycler race after validation/preview.
    result = service.delete([folder], recycler=lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    assert result[0].status == DeleteStatus.NOT_FOUND


def test_permanent_delete(tmp_path):
    folder = make_folder(tmp_path)
    result = DeletionService(tmp_path).delete([folder], permanent=True)
    assert result[0].status == DeleteStatus.SUCCESS_PERMANENT and not folder.exists()
