from app.services.taixiu import TaiXiuService
from app.services.xinkeo import XinKeoService


def test_taixiu_roll_has_valid_invariants() -> None:
    result = TaiXiuService().roll()

    assert len(result["rolls"]) == 3
    assert all(1 <= die <= 6 for die in result["rolls"])
    assert result["total"] == sum(result["rolls"])
    assert result["even_odd"] == ("Chẵn" if result["total"] % 2 == 0 else "Lẻ")
    assert result["result_type"] in {"Tài", "Xỉu", "Bão"}


def test_taixiu_formats_triple_result() -> None:
    result = {
        "rolls": [3, 3, 3],
        "emojis": ["⚂", "⚂", "⚂"],
        "total": 9,
        "result_type": "Bão",
        "even_odd": "Lẻ",
        "is_triple": True,
    }

    text = TaiXiuService().get_result_text("An", result)

    assert "**Bão** (⚂ ⚂ ⚂)" in text
    assert "Tổng điểm: **9**" in text


def test_xinkeo_roll_has_consistent_result() -> None:
    service = XinKeoService.__new__(XinKeoService)
    result = service.roll()
    expected = {
        (0, 0): "Keo Âm",
        (1, 1): "Keo Dương",
        (0, 1): "Keo Âm Dương",
        (1, 0): "Keo Âm Dương",
    }

    assert result["result"] == expected[(result["keo1"], result["keo2"])]
    assert result["icon1"] in {":white_circle:", ":black_circle:"}
    assert result["icon2"] in {":white_circle:", ":black_circle:"}
