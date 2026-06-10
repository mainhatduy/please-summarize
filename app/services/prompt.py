def build_summary_prompt(messages: list[str], memory_context: str = "") -> str:
    """Tạo prompt tóm tắt từ danh sách tin nhắn."""
    chat_log = "\n".join(messages)
    memory_section = ""
    if memory_context.strip():
        memory_section = (
            "Ngữ cảnh đã nhớ trong 2 ngày gần đây của kênh này:\n"
            f"{memory_context.strip()}\n\n"
            "Chỉ dùng ngữ cảnh này để hiểu bối cảnh; nội dung tóm tắt chính vẫn phải dựa trên đoạn hội thoại bên dưới.\n\n"
        )
    return (
        "Bạn là trợ lý tóm tắt hội thoại Discord bằng tiếng Việt.\n"
        "Hãy tóm tắt ngắn gọn đoạn hội thoại sau, dùng bullet points, "
        "nêu rõ ai nói gì quan trọng.\n"
        "Không bịa thêm thông tin ngoài đoạn hội thoại.\n\n"
        f"{memory_section}"
        f"{chat_log}\n\n"
        "Tóm tắt:"
    )
