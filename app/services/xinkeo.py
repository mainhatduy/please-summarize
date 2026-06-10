"""
Xin Keo Service – Mô phỏng nghi lễ xin keo truyền thống
======================================================
Mỗi đồng keo có 2 mặt:
  - Mặt ngửa (âm) = 0 → icon: :white_circle:
  - Mặt sấp (dương) = 1 → icon: :black_circle:

Bảng kết quả:
  - [0, 0] → "Keo Âm"       — Chưa được, thần linh chưa chứng giám
  - [1, 1] → "Keo Dương"    — Chưa được, thần linh chưa đồng ý
  - [0, 1], [1, 0] → "Keo Âm Dương" — Được, thần linh đã chứng giám và đồng ý
"""

import logging
import random
from google import genai
from app.core.config import Config

log = logging.getLogger("bot.xinkeo")


class XinKeoService:
    """Xử lý logic xin keo và luận giải tâm nguyện bằng Gemini API."""

    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME

    def roll(self) -> dict:
        """Sinh ngẫu nhiên độc lập 2 đồng keo (0 hoặc 1) với xác suất 50/50."""
        secure_random = random.SystemRandom()
        keo1 = secure_random.choice([0, 1])
        keo2 = secure_random.choice([0, 1])

        icon1 = ":white_circle:" if keo1 == 0 else ":black_circle:"
        icon2 = ":white_circle:" if keo2 == 0 else ":black_circle:"

        # Xác định kết quả dựa trên cặp keo
        pair = (keo1, keo2)
        if pair == (0, 0):
            result = "Keo Âm"
        elif pair == (1, 1):
            result = "Keo Dương"
        else:
            result = "Keo Âm Dương"

        return {
            "keo1": keo1,
            "keo2": keo2,
            "icon1": icon1,
            "icon2": icon2,
            "result": result
        }

    def generate_luan_giai(self, wish: str, roll_result: dict, memory_context: str = "") -> str:
        """Gọi Gemini sinh lời luận giải ngắn gọn (2-4 câu) phù hợp với kết quả xin keo và nội dung lời khấn."""
        result_type = roll_result["result"]

        # Thiết lập fallback đề phòng lỗi kết nối
        fallback_map = {
            "Keo Âm": "Thần linh chưa chứng giám cho lời khấn nguyện này của bạn. Hãy bình tâm, gột rửa mọi tạp niệm và thành kính xin cầu lại để tỏ rõ tấm lòng thành.",
            "Keo Dương": "Thần linh chưa đồng ý với tâm nguyện hiện tại. Có thể thời điểm chưa chín muồi hoặc ước nguyện chưa thích hợp, bạn nên suy xét kỹ lại và kiên nhẫn chờ đợi.",
            "Keo Âm Dương": "Nguyện vọng của bạn đã được thần linh chứng giám và đồng ý. Hãy tiếp tục giữ tâm thành ý thiện, nỗ lực hết mình để mong ước sớm ngày thành hiện thực."
        }
        fallback = fallback_map.get(result_type, "")

        if not wish or not wish.strip():
            return fallback

        # Xây dựng prompt cho Gemini
        prompt = (
            "Bạn là một bậc trưởng thượng am hiểu tâm linh dân gian Việt Nam, có giọng văn trang trọng, bình tĩnh, ấm áp và thành kính.\n"
            f"{self._memory_prompt(memory_context)}"
            f"Người dùng vừa thực hiện nghi lễ xin keo với lời khấn sau: \"{wish}\"\n"
            f"Kết quả xin keo nhận được là: **{result_type}**.\n\n"
            "Hãy viết một đoạn luận giải ngắn gọn từ 2 đến 4 câu theo nguyên tắc sau:\n"
            "- Nếu là \"Keo Âm Dương\": Hãy khuyến khích, xác nhận nguyện vọng đã được chứng giám và đồng ý, nhắn nhủ người cầu tiếp tục giữ tâm thành ý thiện và nỗ lực hành động.\n"
            "- Nếu là \"Keo Âm\" hoặc \"Keo Dương\": Hãy an ủi nhẹ nhàng, khuyên người cầu hãy thành tâm cầu lại hoặc xem xét kỹ lại tâm nguyện của bản thân. Tuyệt đối không phán xét, không dọa dẫm hay gây lo lắng.\n"
            "- Luận giải phải liên quan trực tiếp đến nội dung lời khấn cụ thể của người dùng.\n\n"
            "Yêu cầu đặc biệt: Chỉ trả về duy nhất đoạn văn luận giải bằng tiếng Việt, không thêm bất cứ tiêu đề, lời mở đầu, hay ký hiệu đặc biệt nào khác."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            explanation = response.text.strip() if response.text else ""
            return explanation or fallback
        except Exception as e:
            log.error(f"[xinkeo] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return fallback

    @staticmethod
    def _memory_prompt(memory_context: str) -> str:
        if not memory_context.strip():
            return ""
        return (
            "Ngữ cảnh đã nhớ trong 2 ngày gần đây của kênh này:\n"
            f"{memory_context.strip()}\n"
            "Hãy dùng ngữ cảnh này để luận giải sát bối cảnh hơn, nhưng không bịa thêm dữ kiện.\n\n"
        )
