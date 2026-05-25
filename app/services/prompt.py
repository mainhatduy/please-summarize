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
