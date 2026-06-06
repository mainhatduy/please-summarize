import os
import json
import logging
import random
import time
import hashlib
from dataclasses import dataclass
from google import genai
from app.core.config import Config

log = logging.getLogger("bot.tarot")

# Major Arcana Vietnamese Display Names
MAJOR_ARCANA_VI = {
    "The_Fool_Meaning": "The Fool (Kẻ Khờ)",
    "The_Magician_Meaning": "The Magician (Pháp Sư)",
    "The_High_Priestess_Meaning": "The High Priestess (Nữ Tư Tế)",
    "The_Empress_Meaning": "The Empress (Hoàng Hậu)",
    "The_Emperor_Meaning": "The Emperor (Hoàng Đế)",
    "The_Hierophant_Meaning": "The Hierophant (Giáo Hoàng)",
    "The_Lovers_Meaning": "The Lovers (Tình Nhân)",
    "The_Chariot_Meaning": "The Chariot (Cỗ Xe)",
    "Strength_Meaning": "Strength (Sức Mạnh)",
    "The_Hermit_Meaning": "The Hermit (Ẩn Sĩ)",
    "The_Wheel_of_Fortune_Meaning": "Wheel of Fortune (Vòng Quay Số Phận)",
    "Justice_Meaning": "Justice (Công Lý)",
    "The_Hanged_Man_Meaning": "The Hanged Man (Người Treo Ngược)",
    "Death_Meaning": "Death (Tử Thần)",
    "Temperance_Meaning": "Temperance (Tiết Chế)",
    "The_Devil_Meaning": "The Devil (Ác Quỷ)",
    "The_Tower_Meaning": "The Tower (Tòa Tháp)",
    "The_Star_Meaning": "The Star (Ngôi Sao)",
    "The_Moon_Meaning": "The Moon (Mặt Trăng)",
    "The_Sun_Meaning": "The Sun (Mặt Trời)",
    "Judgement_Meaning": "Judgement (Phán Xét)",
    "The_World_Meaning": "The World (Thế Giới)",
}

def get_display_name(key: str) -> str:
    if key in MAJOR_ARCANA_VI:
        return MAJOR_ARCANA_VI[key]
    # Clean up name: e.g. "Page_of_Wands_Meaning" -> "Page of Wands"
    name = key.replace("_Meaning", "").replace("_", " ")
    return name

@dataclass
class DrawnCard:
    card_key: str
    name: str
    is_reversed: bool

class TarotService:
    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME
        
        # Load database
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(current_dir, "..", "database", "cards_data.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                self.cards_data = json.load(f)
            log.info(f"Loaded tarot card database from {db_path}. Total cards: {len(self.cards_data)}")
        except Exception as e:
            log.error(f"Failed to load tarot database from {db_path}: {e}", exc_info=True)
            self.cards_data = {}

    def draw_cards(self) -> dict:
        """Rút 4 lá bài ngẫu nhiên không trùng lặp: 1 lá chính (key), 3 lá phụ (supporting)."""
        secure_random = random.SystemRandom()
        if not self.cards_data:
            log.error("Card database is empty, cannot draw cards.")
            return {}
            
        selected_keys = secure_random.sample(list(self.cards_data.keys()), 4)
        drawn = []
        for key in selected_keys:
            is_reversed = secure_random.choice([True, False])
            name = get_display_name(key)
            drawn.append(DrawnCard(card_key=key, name=name, is_reversed=is_reversed))
            
        return {
            "key_card": drawn[0],
            "supporting_cards": drawn[1:4]
        }

    def detect_category(self, question: str) -> str:
        """Nhận diện danh mục câu hỏi (Tình duyên, Sự nghiệp, Tài chính, hay Tổng quan)."""
        q = question.lower()
        love_keywords = ["yêu", "tình", "bạn đời", "người yêu", "love", "crush", "hôn nhân", "cưới", "hẹn hò", "nửa kia", "đối phương"]
        career_keywords = ["công việc", "sự nghiệp", "học", "thi", "làm", "career", "job", "dự án", "sếp", "đồng nghiệp", "kinh doanh", "công ty", "phỏng vấn"]
        finance_keywords = ["tiền", "tài chính", "giàu", "mua", "bán", "đầu tư", "money", "finance", "lương", "nợ", "giá", "tiêu xài"]
        
        if any(k in q for k in love_keywords):
            return "love"
        if any(k in q for k in career_keywords):
            return "career"
        if any(k in q for k in finance_keywords):
            return "finance"
        return "general"

    def build_context(self, draw_result: dict, category: str) -> str:
        """
        Xây dựng bối cảnh ý nghĩa của các lá bài được rút (đã được lọc thông tin cần thiết):
        - Từ khóa (Keywords) và Ý nghĩa cụ thể theo chiều (Xuôi/Ngược) của từng lá bài.
        - Ý nghĩa theo danh mục cụ thể (Tình yêu, Công việc, Tài chính) nếu được phát hiện.
        - Các quy tắc kết hợp (combination rules) được kích hoạt giữa các cặp lá bài trong trải bài.
        """
        key_card = draw_result["key_card"]
        supp_cards = draw_result["supporting_cards"]
        all_drawn = [key_card] + supp_cards
        
        # 1. Chi tiết từng lá bài trong trải bài
        context_parts = ["### Card Details in this Reading:"]
        for idx, dc in enumerate(all_drawn):
            role = "Key Card (Lá chính - Trọng tâm)" if idx == 0 else f"Supporting Card {idx} (Lá phụ)"
            card_info = self.cards_data.get(dc.card_key)
            if not card_info:
                context_parts.append(f"- **{dc.name}** ({'Ngược' if dc.is_reversed else 'Xuôi'}) - [{role}]")
                continue
                
            metadata = card_info.get("metadata", {})
            orientation = "reversed" if dc.is_reversed else "upright"
            
            # Keywords
            kw_key = "reversed_keywords" if dc.is_reversed else "upright_keywords"
            keywords = ", ".join(metadata.get(kw_key, []))
            
            # General meaning for orientation
            meaning_key = "reversal_meaning" if dc.is_reversed else "upright_meaning"
            general_meaning = metadata.get(meaning_key, "")
            
            # Category-specific meaning
            category_meaning = ""
            if category == "love":
                cat_key = "reversal_love_meaning" if dc.is_reversed else "upright_love_meaning"
                category_meaning = metadata.get(cat_key, "")
            elif category == "career":
                cat_key = "reversal_career_meaning" if dc.is_reversed else "upright_career_meaning"
                category_meaning = metadata.get(cat_key, "")
            elif category == "finance":
                cat_key = "reversal_finances_meaning" if dc.is_reversed else "upright_finances_meaning"
                category_meaning = metadata.get(cat_key, "")
                
            card_str = f"- **{dc.name}** ({'Ngược' if dc.is_reversed else 'Xuôi'}) - [{role}]\n"
            card_str += f"  * Keywords: {keywords}\n"
            if general_meaning:
                card_str += f"  * General Meaning ({orientation}): {general_meaning.strip()}\n"
            if category_meaning:
                card_str += f"  * Category-specific Meaning ({category} - {orientation}): {category_meaning.strip()}\n"
                
            context_parts.append(card_str)
            
        # 2. Kiểm tra các tổ hợp (combinations) được kích hoạt
        combo_parts = []
        seen_pairs = set()
        for i in range(len(all_drawn)):
            for j in range(i + 1, len(all_drawn)):
                c1 = all_drawn[i]
                c2 = all_drawn[j]
                pair = tuple(sorted([c1.card_key, c2.card_key]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                
                # Tìm trong card_data của c1
                c1_data = self.cards_data.get(c1.card_key, {})
                combos = c1_data.get("metadata", {}).get("combinations", {})
                found_combo = None
                
                for rel in ["reinforcing", "opposing"]:
                    for cb in combos.get(rel, []):
                        if tuple(sorted(cb.get("cards", []))) == pair:
                            found_combo = cb
                            break
                    if found_combo:
                        break
                        
                # Nếu không tìm thấy trong c1, kiểm tra c2
                if not found_combo:
                    c2_data = self.cards_data.get(c2.card_key, {})
                    combos2 = c2_data.get("metadata", {}).get("combinations", {})
                    for rel in ["reinforcing", "opposing"]:
                        for cb in combos2.get(rel, []):
                            if tuple(sorted(cb.get("cards", []))) == pair:
                                found_combo = cb
                                break
                        if found_combo:
                            break
                            
                if found_combo:
                    combo_str = f"- **{found_combo['name']}** ({found_combo['relationship'].upper()}):\n"
                    combo_str += f"  * Explanation: {found_combo['explanation'].strip()}\n"
                    if found_combo.get("contrasts"):
                        combo_str += "  * Contrasts:\n"
                        for contrast in found_combo["contrasts"]:
                            combo_str += f"    - {contrast['left']} vs {contrast['right']}\n"
                    combo_parts.append(combo_str)
                    
        if combo_parts:
            context_parts.append("\n### Card Combinations Triggered in this Spread:")
            context_parts.extend(combo_parts)
            
        return "\n".join(context_parts)

    def generate_reading(self, question: str, draw_result: dict, user_name: str) -> str:
        """Sử dụng Gemini để luận giải các lá bài dựa trên câu hỏi và tên người cầu."""
        if not draw_result:
            return "Đã xảy ra lỗi khi rút bài. Xin hãy thử lại sau."
            
        key_card = draw_result["key_card"]
        supp_cards = draw_result["supporting_cards"]
        
        # Nhận diện danh mục câu hỏi và xây dựng bối cảnh
        category = self.detect_category(question)
        context = self.build_context(draw_result, category)
        
        category_vi = {
            "love": "tình cảm/mối quan hệ",
            "career": "công việc/học tập",
            "finance": "tài chính/tiền bạc",
            "general": "cuộc sống/tổng quan"
        }
        category_desc = category_vi.get(category, "cuộc sống/tổng quan")

        def format_card(card: DrawnCard):
            orientation = "Ngược" if card.is_reversed else "Xuôi"
            return f"**{card.name}** ({orientation})"
        
        key_str = format_card(key_card)
        supp_str = ", ".join([format_card(c) for c in supp_cards])
        
        def card_header(card: DrawnCard):
            return f"{card.name} ({'Ngược' if card.is_reversed else 'Xuôi'})"
            
        prompt = (
            f"Người cầu: {user_name}\n"
            f"Câu hỏi: '{question}'\n"
            f"Lá chính: {key_str}\n"
            f"3 lá phụ: {supp_str}\n\n"
            
            f"Dưới đây là thông tin chi tiết về các lá bài được rút và mối quan hệ của chúng để bạn sử dụng làm bối cảnh luận giải:\n"
            f"{context}\n\n"

            f"Bạn là một chuyên gia giải Tarot thấu cảm, sâu sắc và thực tế. Hãy luận giải trải bài này để trả lời câu hỏi cụ thể của {user_name}.\n\n"

            f"Nguyên tắc luận giải quan trọng:\n"
            f"1. TÔN TRỌNG TỔNG QUAN LÁ BÀI: Kết luận đưa ra PHẢI dựa hoàn toàn vào sắc thái (tích cực/tiêu cực) của các lá bài được rút. Nếu bài ra tốt, hãy mạnh dạn đưa ra lời khuyên tích cực, ủng hộ và khích lệ người hỏi. TUYỆT ĐỐI KHÔNG để các bộ lọc an toàn hay định kiến tự nhiên của AI (như luôn khuyên cẩn trọng khi hỏi về người yêu cũ/đầu tư mạo hiểm) làm lu mờ đi ý nghĩa tốt đẹp của các lá bài.\n"
            f"2. TRẢ LỜI TRỰC DIỆN & THẤU CẢM: Đưa ra nhận định rõ ràng, ấm áp và hướng tới việc chữa lành/khích lệ. Đi thẳng vào vấn đề của {user_name} nhưng không được khô khan hay phán xét.\n"
            f"3. KHÔNG SAO CHÉP HAY DỊCH THÔ TỪ KHÓA: Hãy chuyển hóa ý nghĩa các lá bài thành tình huống thực tế cụ thể trong khía cạnh {category_desc} của {user_name}, dùng văn phong tự nhiên.\n"
            f"4. LIÊN KẾT TRẢI BÀI: Lá chính là năng lượng cốt lõi, các lá phụ bổ trợ/giải thích/cảnh báo. Hãy liên kết các lá bài thành một thông điệp thống nhất.\n\n"

            f"Yêu cầu trả lời cực kỳ ngắn gọn theo đúng định dạng sau (đảm bảo mỗi ý phân tích chỉ viết trong 1 câu ngắn gọn, không lan man):\n\n"

            f"**Tổng quan:**\n"
            f"(1-2 câu trả lời thẳng vào câu hỏi, tóm tắt tình thế và kết luận chính cho câu hỏi của {user_name})\n\n"

            f"**Phân tích:**\n"
            f"- **{card_header(key_card)}** (lá chính): (1 câu ngắn gọn chỉ ra vấn đề cốt lõi hoặc trạng thái {category_desc} hiện tại của {user_name} liên quan đến câu hỏi)\n"
            f"- **{card_header(supp_cards[0])}**: (1 câu ngắn gọn chỉ ra cách lá này tác động, cản trước hoặc làm rõ thêm khía cạnh nào cho tình huống trên)\n"
            f"- **{card_header(supp_cards[1])}**: (1 câu ngắn gọn chỉ ra cảnh báo cụ thể hoặc bài học cần lưu ý)\n"
            f"- **{card_header(supp_cards[2])}**: (1 câu ngắn gọn chỉ ra kết quả tiềm năng hoặc lưu ý về mặt hành động của {user_name})\n\n"

            f"**Lời khuyên:**\n"
            f"(1 câu ngắn gọn, thực tế và có tính hành động ngay lập tức dành cho {user_name})"
        )
        
        try:
            print(prompt)
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or "Các linh hồn Tarot đang bối rối, xin hãy thử lại sau..."
        except Exception as e:
            log.error(f"[tarot] Lỗi khi gọi Gemini: {e}", exc_info=True)
            return "Đã có lỗi xảy ra khi kết nối với cõi tâm linh (Lỗi AI). Xin hãy thử lại sau."
