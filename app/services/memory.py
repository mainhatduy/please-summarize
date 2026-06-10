import json
import logging
import os
from datetime import datetime, timedelta, timezone

from google import genai

from app.core.config import Config

log = logging.getLogger("bot.memory")


class MemoryService:
    """Short-lived persistent channel memory stored as JSON."""

    def __init__(self):
        self.file_path = Config.data_path("memory.json")
        self.ttl = timedelta(hours=Config.MEMORY_TTL_HOURS)
        self.max_chars = Config.MEMORY_MAX_CHARS
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME

    def get_context(self, channel_id: int) -> str:
        data = self._load()
        key = str(channel_id)
        record = data.get(key)
        if not record:
            return ""

        expires_at = self._parse_dt(record.get("expires_at"))
        if not expires_at or expires_at <= self._now():
            data.pop(key, None)
            self._save(data)
            return ""

        summary = str(record.get("summary", "")).strip()
        return summary[: self.max_chars]

    def update(self, channel_id: int, new_context: str, command_name: str) -> None:
        new_context = (new_context or "").strip()
        if not new_context:
            return

        data = self._load()
        self._prune_expired(data)

        key = str(channel_id)
        previous = str(data.get(key, {}).get("summary", "")).strip()
        summary = self._summarize(previous, new_context, command_name)
        if not summary:
            return

        now = self._now()
        data[key] = {
            "summary": summary[: self.max_chars],
            "updated_at": now.isoformat(),
            "expires_at": (now + self.ttl).isoformat(),
        }
        self._save(data)

    def _summarize(self, previous: str, new_context: str, command_name: str) -> str:
        prompt = (
            "Bạn đang duy trì bộ nhớ ngắn hạn cho một bot Discord.\n"
            "Hãy cập nhật memory bằng tiếng Việt, thật ngắn gọn, chỉ giữ thông tin còn hữu ích "
            "để các lần trả lời sau đúng ngữ cảnh hơn.\n"
            "Không lưu nguyên văn tin nhắn dài, không thêm suy đoán, không lưu bí mật/token/key.\n"
            f"Giới hạn tối đa khoảng {self.max_chars} ký tự.\n\n"
            f"Memory cũ:\n{previous or '(chưa có)'}\n\n"
            f"Ngữ cảnh mới từ lệnh {command_name}:\n{new_context[:12000]}\n\n"
            "Memory mới:"
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result[: self.max_chars]
        except Exception as e:
            log.error(f"[memory] Lỗi khi cập nhật memory bằng Gemini: {e}", exc_info=True)
            merged = "\n".join(part for part in [previous, new_context] if part).strip()
            return merged[-self.max_chars :]

    def _load(self) -> dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            log.error(f"[memory] Lỗi khi đọc memory file: {e}", exc_info=True)
            return {}

    def _save(self, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            tmp_path = f"{self.file_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            log.error(f"[memory] Lỗi khi ghi memory file: {e}", exc_info=True)

    def _prune_expired(self, data: dict) -> None:
        now = self._now()
        expired = [
            key for key, record in data.items()
            if self._parse_dt(record.get("expires_at")) is None
            or self._parse_dt(record.get("expires_at")) <= now
        ]
        for key in expired:
            data.pop(key, None)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_dt(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
