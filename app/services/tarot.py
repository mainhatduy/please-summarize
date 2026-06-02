import logging
import random
from dataclasses import dataclass
from google import genai
from app.core.config import Config

log = logging.getLogger("bot.tarot")

TAROT_CARDS = [
    # Major Arcana (22)
    "The Fool (Kẻ Khờ)", "The Magician (Pháp Sư)", "The High Priestess (Nữ Tư Tế)", 
    "The Empress (Hoàng Hậu)", "The Emperor (Hoàng Đế)", "The Hierophant (Giáo Hoàng)", 
    "The Lovers (Tình Nhân)", "The Chariot (Cỗ Xe)", "Strength (Sức Mạnh)", 
    "The Hermit (Ẩn Sĩ)", "Wheel of Fortune (Vòng Quay Số Phận)", "Justice (Công Lý)", 
    "The Hanged Man (Người Treo Ngược)", "Death (Tử Thần)", "Temperance (Tiết Chế)", 
    "The Devil (Ác Quỷ)", "The Tower (Tòa Tháp)", "The Star (Ngôi Sao)", 
    "The Moon (Mặt Trăng)", "The Sun (Mặt Trời)", "Judgement (Phán Xét)", 
    "The World (Thế Giới)",
    
    # Minor Arcana - Wands (14)
    "Ace of Wands", "Two of Wands", "Three of Wands", "Four of Wands", 
    "Five of Wands", "Six of Wands", "Seven of Wands", "Eight of Wands", 
    "Nine of Wands", "Ten of Wands", "Page of Wands", "Knight of Wands", 
    "Queen of Wands", "King of Wands",
    
    # Minor Arcana - Cups (14)
    "Ace of Cups", "Two of Cups", "Three of Cups", "Four of Cups", 
    "Five of Cups", "Six of Cups", "Seven of Cups", "Eight of Cups", 
    "Nine of Cups", "Ten of Cups", "Page of Cups", "Knight of Cups", 
    "Queen of Cups", "King of Cups",
    
    # Minor Arcana - Swords (14)
    "Ace of Swords", "Two of Swords", "Three of Swords", "Four of Swords", 
    "Five of Swords", "Six of Swords", "Seven of Swords", "Eight of Swords", 
    "Nine of Swords", "Ten of Swords", "Page of Swords", "Knight of Swords", 
    "Queen of Swords", "King of Swords",
    
    # Minor Arcana - Pentacles (14)
    "Ace of Pentacles", "Two of Pentacles", "Three of Pentacles", "Four of Pentacles", 
    "Five of Pentacles", "Six of Pentacles", "Seven of Pentacles", "Eight of Pentacles", 
    "Nine of Pentacles", "Ten of Pentacles", "Page of Pentacles", "Knight of Pentacles", 
    "Queen of Pentacles", "King of Pentacles"
]

@dataclass
class DrawnCard:
    name: str
    is_reversed: bool

class TarotService:
    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME

    def draw_cards(self) -> dict:
        """Rút 4 lá bài ngẫu nhiên không trùng lập: 1 lá key, 3 lá phụ. Trả về tên và chiều (xuôi/ngược)."""
        selected = random.sample(TAROT_CARDS, 4)
        drawn = [DrawnCard(name=card, is_reversed=random.choice([True, False])) for card in selected]
        
        return {
            "key_card": drawn[0],
            "supporting_cards": drawn[1:4]
        }

    def generate_reading(self, question: str, draw_result: dict, user_name: str, recent_messages: list[str] = None) -> str:
        """Sử dụng Gemini để luận giải các lá bài dựa trên câu hỏi."""
        key_card = draw_result["key_card"]
        supp_cards = draw_result["supporting_cards"]
        
        def format_card(card: DrawnCard):
            orientation = "Ngược" if card.is_reversed else "Xuôi"
            return f"**{card.name}** ({orientation})"
        
        key_str = format_card(key_card)
        supp_str = ", ".join([format_card(c) for c in supp_cards])
        
        chat_log = "\n".join(recent_messages) if recent_messages else "Không có thông tin trò chuyện gần đây."
        
        prompt = (
            f"Người dùng hỏi: '{question}'\n"
            f"Lá chính: {key_str} | 3 lá phụ: {supp_str}\n\n"
            f"Thông tin bổ sung - Các tin nhắn gần đây của người dùng:\n"
            f"\"\"\"\n{chat_log}\n\"\"\"\n\n"
            f"Dựa vào các tin nhắn trên, hãy cảm nhận tâm trạng/cảm xúc hiện tại của người dùng để điều chỉnh văn phong (đồng cảm, an ủi, hoặc động viên) cho phù hợp.\n\n"
            f"Yêu cầu luận giải cực kỳ ngắn gọn. KHÔNG chào hỏi, KHÔNG viết dòng thừa, ĐI THẲNG vào vấn đề theo ĐÚNG form sau:\n\n"
            f"**Tổng quan:** (1-2 câu tóm tắt nhanh tình hình)\n\n"
            f"**Phân tích:**\n"
            f"- **{key_card.name}**: (Ý nghĩa ngắn gọn của lá chính)\n"
            f"- **{supp_cards[0].name}**: (Ý nghĩa ngắn gọn)\n"
            f"- **{supp_cards[1].name}**: (Ý nghĩa ngắn gọn)\n"
            f"- **{supp_cards[2].name}**: (Ý nghĩa ngắn gọn)\n\n"
            f"**Lời khuyên:** (Đúng 2 câu chốt lại hướng đi cuối cùng)"
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or "Các linh hồn Tarot đang bối rối, xin hãy thử lại sau..."
        except Exception as e:
            log.error(f"[tarot] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return "Đã có lỗi xảy ra khi kết nối với cõi tâm linh (Lỗi AI). Xin hãy thử lại sau."
