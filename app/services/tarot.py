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

    def generate_reading(self, question: str, draw_result: dict, user_name: str) -> str:
        """Sử dụng Gemini để luận giải các lá bài dựa trên câu hỏi."""
        key_card = draw_result["key_card"]
        supp_cards = draw_result["supporting_cards"]
        
        def format_card(card: DrawnCard):
            orientation = "Ngược" if card.is_reversed else "Xuôi"
            return f"**{card.name}** ({orientation})"
        
        key_str = format_card(key_card)
        supp_str = ", ".join([format_card(c) for c in supp_cards])
        
        prompt = (
            f"Bạn là một Tarot Reader chuyên nghiệp, thông thái, huyền bí nhưng cũng rất gần gũi và sâu sắc.\n"
            f"Người dùng '{user_name}' đã đặt câu hỏi: '{question}'\n\n"
            f"Trải bài của họ như sau:\n"
            f"- Lá bài chính (Key Card - phản ánh vấn đề trọng tâm, tổng quan nhất): {key_str}\n"
            f"- 3 lá bài phụ (Supporting Cards - bổ sung thêm chi tiết, diễn biến hoặc lời khuyên): {supp_str}\n\n"
            f"Dựa trên ý nghĩa chuẩn của các lá Tarot (bao gồm cả chiều xuôi và chiều ngược), hãy đưa ra lời luận giải chi tiết:\n"
            f"1. Bắt đầu bằng việc nhắc lại câu hỏi và tổng quan trải bài.\n"
            f"2. Phân tích lá bài chính ({key_card.name} - {'Ngược' if key_card.is_reversed else 'Xuôi'}) và ý nghĩa của nó đối với câu hỏi.\n"
            f"3. Phân tích sự kết hợp của 3 lá bài phụ để làm rõ thêm bối cảnh, nguyên nhân, thách thức hoặc diễn biến.\n"
            f"4. Đưa ra lời kết luận và lời khuyên cuối cùng dành cho {user_name}.\n\n"
            f"Lưu ý: Viết bài luận giải tự nhiên, mạch lạc, chia đoạn rõ ràng. Trình bày bằng văn bản thuần túy hoặc Markdown thân thiện với Discord (dùng in đậm, in nghiêng hợp lý, không cần dùng markdown code block cho toàn bộ bài viết)."
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
