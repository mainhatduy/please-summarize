"""
Tai Xiu Service – Game Tài Xỉu 3 viên xúc xắc
===========================================
Lắc 3 viên xúc xắc ngẫu nhiên. Trả về kết quả Tài/Xỉu/Bão và Chẵn/Lẻ.
"""

import random


class TaiXiuService:
    """Xử lý logic xúc xắc và định dạng kết quả game Tài Xỉu."""

    # Unicode ký tự tương ứng với các mặt xúc xắc từ 1 đến 6
    DICE_EMOJIS = {
        1: "⚀",
        2: "⚁",
        3: "⚂",
        4: "⚃",
        5: "⚄",
        6: "⚅"
    }

    def roll(self) -> dict:
        """Đổ 3 viên xúc xắc ngẫu nhiên bằng SystemRandom để đảm bảo an toàn bảo mật."""
        secure_random = random.SystemRandom()
        rolls = [secure_random.randint(1, 6) for _ in range(3)]
        total = sum(rolls)
        
        # Xác định Bão (3 viên cùng một mặt)
        is_triple = (rolls[0] == rolls[1] == rolls[2])
        
        if is_triple:
            result_type = "Bão"
        elif 4 <= total <= 10:
            result_type = "Xỉu"
        elif 11 <= total <= 17:
            result_type = "Tài"
        else:
            # Fallback phòng hờ (như tổng 3 và 18 thực chất luôn là Bão)
            result_type = "Bão"
            
        even_odd = "Chẵn" if total % 2 == 0 else "Lẻ"
        
        return {
            "rolls": rolls,
            "emojis": [self.DICE_EMOJIS[r] for r in rolls],
            "total": total,
            "result_type": result_type,
            "even_odd": even_odd,
            "is_triple": is_triple
        }

    def get_result_text(self, author_name: str, result: dict) -> str:
        """Trả về chuỗi kết quả đã được format đẹp mắt để gửi qua Discord."""
        dice_str = "  ".join(result["emojis"])
        rolls_detail = " + ".join(map(str, result["rolls"]))
        
        if result["is_triple"]:
            # Ví dụ: Bão (⚂ ⚂ ⚂)
            emoji = result["emojis"][0]
            result_type_str = f"**Bão** ({emoji} {emoji} {emoji})"
        else:
            result_type_str = f"**{result['result_type']}**"

        text = (
            f"# {dice_str}\n"
            f"Tổng điểm: **{result['total']}**\n"
            f"Kết quả: {result_type_str}\n"
            f"Chẵn/Lẻ: **{result['even_odd']}**"
        )
        return text