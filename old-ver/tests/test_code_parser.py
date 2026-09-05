from app.code_parser import extract_codes, normalize_code


def test_normalizes_common_code_styles():
    assert normalize_code("abc_0123") == "ABC-0123"
    assert extract_codes("[x] ABC123 1080p") == ["ABC-123"]


def test_ignores_video_technical_tokens():
    assert extract_codes("movie_1920x1080_h265_10bit") == []
