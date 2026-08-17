from app.services.kinhdich import HEXAGRAMS, KinhDichService


def test_draw_hexagram_returns_known_hexagram() -> None:
    service = KinhDichService.__new__(KinhDichService)

    result = service.draw_hexagram("Công việc sắp tới thế nào?")

    assert result in HEXAGRAMS
    assert 1 <= result["so"] <= 64


def test_format_hexagram_text_contains_core_fields() -> None:
    service = KinhDichService.__new__(KinhDichService)
    hexagram = HEXAGRAMS[0]

    text = service.format_hexagram_text(hexagram)

    assert "Quẻ 1" in text
    assert hexagram["ten"] in text
    assert hexagram["ngoai_quai"] in text
    assert hexagram["noi_quai"] in text
