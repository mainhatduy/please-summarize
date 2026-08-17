import pytest

from app.core.config import Config
from app.services.fortune import TIERS, FortuneService
from app.services.kinhdich import HEXAGRAMS, KinhDichService
from app.services.summarize import SummarizeService
from app.services.tarot import TarotService
from app.services.xinkeo import XinKeoService

pytestmark = pytest.mark.ai


@pytest.fixture(scope="session", autouse=True)
def require_real_gemini_key() -> None:
    key = Config.GEMINI_API_KEY.strip()
    if not key or "your_gemini" in key.lower():
        pytest.fail("AI tests require a real GEMINI_API_KEY in the local .env file.")


def test_summarize_and_question_features_call_gemini() -> None:
    service = SummarizeService()

    summary = service.summarize(["An: Chiều nay họp lúc 3 giờ.", "Bình: Mình sẽ tham gia."])
    question = service.generate_drama_question(["An: Chiều nay đi cà phê nhé."], "Bình")

    assert summary.strip()
    assert not summary.startswith("Có lỗi xảy ra")
    assert question.strip()
    assert question != "Bị nghẹn lời rồi, thử lại sau nhé..."


def test_fortune_feature_calls_gemini() -> None:
    service = FortuneService()
    tier = TIERS[0]

    result = service.generate_fortune_msg(
        tier, tier.animals[0], ["Hôm nay mình vừa hoàn thành một dự án khó."]
    )

    assert result.strip()
    assert result != tier.fortune_msg


def test_xinkeo_feature_calls_gemini() -> None:
    service = XinKeoService()
    roll = {"result": "Keo Âm Dương"}

    result = service.generate_luan_giai("Mong dự án tuần này thuận lợi", roll)

    assert result.strip()
    assert "Nguyện vọng của bạn đã được thần linh" not in result


def test_tarot_feature_calls_gemini() -> None:
    service = TarotService()
    draw = service.draw_cards()

    result = service.generate_reading("Công việc tuần tới thế nào?", draw, "Codex")

    assert result.strip()
    assert "Lỗi AI" not in result


def test_kinhdich_feature_calls_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    service = KinhDichService()
    monkeypatch.setattr(service, "fetch_detail", lambda _slug: "")

    reading = service.generate_reading("Nên tập trung điều gì tuần tới?", HEXAGRAMS[0], "Codex")
    choice = service.generate_choice_reading("Nên đọc sách hay đi bộ?", HEXAGRAMS[0], "Codex")
    statistics = service.generate_thongke(
        "Codex", ["Quẻ Thiên Vi Càn - Đại Cát", "Tier A - Cát Tường"]
    )

    assert reading.strip() and "Lỗi AI" not in reading
    assert choice.strip() and "Lỗi AI" not in choice
    assert statistics.strip() and "Lỗi AI" not in statistics
