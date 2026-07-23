def build_summary_prompt(messages: list[str]) -> str:
    """Tạo prompt tóm tắt từ danh sách tin nhắn."""
    chat_log = "\n".join(messages)
    return (
        "Bạn là trợ lý tóm tắt hội thoại Discord bằng tiếng Việt.\n"
        "Hãy tóm tắt ngắn gọn đoạn hội thoại sau, dùng bullet points, "
        "nêu rõ ai nói gì quan trọng.\n"
        "Không bịa thêm thông tin ngoài đoạn hội thoại.\n\n"
        f"{chat_log}\n\n"
        "Tóm tắt:"
    )


def build_drama_question_prompt(messages: list[str], target_name: str) -> str:
    """Tạo prompt để tự động lấy chủ đề và tạo câu hỏi drama/thả thính cho một user."""
    chat_log = "\n".join(messages)
    return (
        "Bạn là một người có khiếu hài hước sắc sảo, giỏi chơi chữ và thả thính bằng tiếng Việt.\n\n"
        "LỊCH SỬ CHAT:\n"
        f"{chat_log}\n\n"
        f"NHIỆM VỤ:\n"
        f"Đọc lịch sử chat, nắm bắt không khí chung (đang bàn chuyện gì, ai làm gì, mood ra sao).\n"
        f"Sau đó đặt MỘT câu hỏi nhắm vào '{target_name}', dựa trên vibe của cuộc trò chuyện.\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Câu hỏi phải CÓ NGHĨA và TỰ NHIÊN – đọc lên phải hiểu được ngay, không cần giải thích.\n"
        "2. Nếu chơi chữ, phải chơi chữ ĐÚNG nghĩa tiếng Việt (ví dụ: 'thả thính' vừa có nghĩa câu cá vừa có nghĩa tán tỉnh). KHÔNG bịa từ mới hoặc ghép từ vô nghĩa.\n"
        "3. KHÔNG ép từ khóa trong chat vào ngoặc kép rồi gán nghĩa bóng không liên quan. Ví dụ xấu: '\"nhảy chữ\" với người khác' – cụm này vô nghĩa.\n"
        "4. Câu hỏi ngắn gọn, tối đa 1-2 câu.\n"
        "5. Phong cách: thả thính nhẹ nhàng, triết lý tình yêu, hoặc drama hài hước.\n\n"
        "VÍ DỤ TỐT (tự nhiên, có nghĩa, dí dỏm):\n"
        "- 'Nếu người ta thương mình mà lại thương người khác thì sao?'\n"
        "- 'Ê, hôm nay đi ăn nướng mà không rủ người ta, lương tâm có cắn rứt không?'\n"
        "- 'Liệu em không thích con trai thì anh có trở thành con gái để yêu em không?'\n\n"
        "VÍ DỤ XẤU (gượng ép, vô nghĩa):\n"
        "- 'Nếu anh cũng \"nhảy chữ\" với người khác...' – 'nhảy chữ' không phải cụm từ có nghĩa.\n"
        "- 'Bạn có đang \"deploy trái tim\" lên production không?' – ghép thuật ngữ IT vào tình cảm một cách gượng gạo.\n\n"
        "CHỈ trả về đúng câu hỏi (được phép dùng emoji). Trả lời bằng tiếng Việt.\n"
    )
