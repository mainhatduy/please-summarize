from types import SimpleNamespace

from app.services.summarize import SummarizeService


class _Models:
    def __init__(self, text: str | None):
        self.text = text
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


def _service_with_response(text: str | None) -> tuple[SummarizeService, _Models]:
    models = _Models(text)
    service = SummarizeService.__new__(SummarizeService)
    service.client = SimpleNamespace(models=models)
    service.model = "test-model"
    return service, models


def test_summarize_returns_early_for_empty_messages() -> None:
    service, models = _service_with_response("unused")

    assert service.summarize([]) == "Không có nội dung nào để tóm tắt."
    assert models.calls == []


def test_summarize_calls_model_with_built_prompt() -> None:
    service, models = _service_with_response("- An chào Bình")

    result = service.summarize(["An: Chào Bình"])

    assert result == "- An chào Bình"
    assert models.calls[0]["model"] == "test-model"
    assert "An: Chào Bình" in models.calls[0]["contents"]


def test_generate_drama_question_strips_response() -> None:
    service, _ = _service_with_response("  Đi ăn cùng mình không?  ")

    result = service.generate_drama_question(["An: Đói quá"], "An")

    assert result == "Đi ăn cùng mình không?"

