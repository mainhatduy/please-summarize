"""General bot commands."""

from app.bot.helpers import COOLDOWN_SECONDS
from app.bot.runtime import bot


@bot.command(name="help")
async def help_cmd(ctx):
    await ctx.send(
        "**📋 Danh sách lệnh:**\n"
        "🎬 **Auto TikTok:** Paste link TikTok → bot tự gửi video/ảnh\n"
        "`.tomtat [n] [@user]` – Tóm tắt n tin nhắn gần nhất (mặc định 50, tối đa 500)\n"
        "`.tomtat_time [giờ] [@user]` – Tóm tắt tin nhắn trong n giờ qua (mặc định 1, tối đa 12)\n"
        "`.get_luck` – Roll vận may hôm nay (1 lần/ngày, reset 00:00)\n"
        "`.taixiu` (hoặc `.tx`) – Chơi Tài Xỉu 3 xúc xắc (kèm chẵn lẻ)\n"
        "`.xinkeo <lời khấn>` (hoặc `.xk`) – Xin keo truyền thống\n"
        "`.tarot <câu hỏi>` – Xem bói Tarot (1 lá chính, 3 lá phụ)\n"
        "`.rutque <câu hỏi>` (hoặc `.rq`) – Rút quẻ Kinh Dịch\n"
        "`.luachon <câu hỏi và các lựa chọn>` (hoặc `.lc`) – Kinh Dịch đưa ra quyết định\n"
        "`.thongke_kinhdich [@user]` (hoặc `.tk_kd`) – Thống kê & luận giải Kinh Dịch trong ngày\n"
        "`.cau_hoi` – Tạo câu hỏi drama/thả thính từ ngữ cảnh 4h qua\n"
        "`.play <tên bài/link YouTube>` – Phát nhạc trong voice\n"
        "`.next` – Chuyển sang bài hát tiếp theo trong hàng đợi\n"
        "`.queue` – Xem danh sách hàng đợi nhạc\n"
        "`.join` – Tham gia cuộc gọi thoại\n"
        "`.leave` / `.stop` – Rời cuộc gọi thoại\n"
        "`.help` – Hiển thị danh sách lệnh này\n"
        f"\n⏱️ Cooldown: {COOLDOWN_SECONDS}s/user cho các lệnh tóm tắt."
    )
