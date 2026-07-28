from app.code_parser import extract_codes, extract_part, normalize_code


def test_normalizes_common_code_styles():
    assert normalize_code("abc_0123") == "ABC-0123"
    assert extract_codes("[x] ABC123 1080p") == ["ABC-123"]


def test_ignores_video_technical_tokens():
    assert extract_codes("movie_1920x1080_h265_10bit") == []


def test_cd_parts_share_the_same_base_code():
    assert extract_codes("ABC-123-CD1") == ["ABC-123"]
    assert extract_codes("ABC-123-CD2") == ["ABC-123"]
    assert extract_part("ABC-123-CD1") == 1
    assert extract_part("ABC-123-CD2") == 2
