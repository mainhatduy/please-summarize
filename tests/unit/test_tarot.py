from app.services.tarot import DrawnCard, TarotService, get_display_name


def test_get_display_name_handles_major_and_minor_arcana() -> None:
    assert get_display_name("The_Fool_Meaning") == "The Fool (Kẻ Khờ)"
    assert get_display_name("Page_of_Wands_Meaning") == "Page of Wands"


def test_detect_category_uses_question_keywords() -> None:
    service = TarotService.__new__(TarotService)

    assert service.detect_category("Crush có yêu mình không?") == "love"
    assert service.detect_category("Kỳ thi và công việc sắp tới?") == "career"
    assert service.detect_category("Nên đầu tư tiền thế nào?") == "finance"
    assert service.detect_category("Ngày mai của mình ra sao?") == "general"


def test_build_context_uses_orientation_and_category_meaning() -> None:
    service = TarotService.__new__(TarotService)
    service.cards_data = {
        "Card_A": {
            "metadata": {
                "upright_keywords": ["hope"],
                "upright_meaning": "A bright beginning.",
                "upright_love_meaning": "A warm connection.",
            }
        }
    }
    draw = {
        "key_card": DrawnCard("Card_A", "Card A", False),
        "supporting_cards": [
            DrawnCard("Missing_B", "Card B", True),
            DrawnCard("Missing_C", "Card C", False),
            DrawnCard("Missing_D", "Card D", False),
        ],
    }

    context = service.build_context(draw, "love")

    assert "Keywords: hope" in context
    assert "A bright beginning." in context
    assert "A warm connection." in context
    assert "Card B** (Ngược)" in context

