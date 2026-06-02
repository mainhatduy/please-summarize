import logging
from google import genai
from app.core.config import Config
from app.services.prompt import build_summary_prompt

log = logging.getLogger("bot.summarize")

MAX_PROMPT_CHARS = 1_200_000


class SummarizeService:
    def __init__(self):
        log.info(f"Khởi tạo SummarizeService với model='{Config.MODEL_NAME}'")
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME

    def summarize(self, messages: list[str]) -> str:
        if not messages:
            log.warning("summarize() được gọi với danh sách tin nhắn rỗng.")
            return "Không có nội dung nào để tóm tắt."

        prompt = build_summary_prompt(messages)
        log.debug(f"Prompt đã build: {len(messages)} tin nhắn, ~{len(prompt)} ký tự – đang gọi Gemini ({self.model})...")

        # Truncate prompt từ đầu nếu vượt giới hạn context window,
        # giữ lại phần cuối để ưu tiên tin nhắn mới nhất
        if len(prompt) > MAX_PROMPT_CHARS:
            log.warning(
                f"Prompt quá dài ({len(prompt)} ký tự > {MAX_PROMPT_CHARS}), "
                "đang truncate từ đầu để giữ tin nhắn mới nhất..."
            )
            prompt = prompt[-MAX_PROMPT_CHARS:]

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                request_options={"timeout": 30},
            )
            result = response.text if response.text else "Không nhận được phản hồi từ mô hình."
            log.info(f"Gemini phản hồi thành công ({len(result)} ký tự).")
            return result
        except Exception as e:
            log.error(f"Lỗi khi gọi Gemini API: {e}", exc_info=True)
            return f"Có lỗi xảy ra khi tóm tắt: {str(e)}"
