import json

from app.deletion_log import DeletionLogger
from app.deletion_service import DeleteResult, DeleteStatus, FolderPreview


def test_deletion_log_records_actual_result(tmp_path):
    folder = tmp_path / "ABC-123"
    preview = FolderPreview(folder, file_count=3, total_size=42)
    logger = DeletionLogger(tmp_path / "logs" / "deletions.jsonl")
    logger.record_many(
        [DeleteResult(folder, DeleteStatus.SUCCESS_RECYCLE, preview)],
        "recycle_bin",
    )
    record = json.loads(logger.path.read_text(encoding="utf-8"))
    assert record["folder"] == str(folder)
    assert record["file_count"] == 3
    assert record["result"] == "已移至資源回收筒"
