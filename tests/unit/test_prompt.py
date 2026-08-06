from app.services.prompt import build_drama_question_prompt, build_summary_prompt


def test_build_summary_prompt_keeps_messages_and_instructions() -> None:
    prompt = build_summary_prompt(["An: Xin chào", "Bình: Chào An"])

    assert "An: Xin chào\nBình: Chào An" in prompt
    assert "Không bịa thêm thông tin" in prompt
    assert prompt.endswith("Tóm tắt:")


def test_build_drama_question_prompt_includes_target_and_chat() -> None:
    prompt = build_drama_question_prompt(["An: Đi ăn nướng không?"], "Bình")

    assert "An: Đi ăn nướng không?" in prompt
    assert "nhắm vào 'Bình'" in prompt
    assert "CHỈ trả về đúng câu hỏi" in prompt

