"""
Fortune Service – Random Vận May (Animal Fortune & Tier)
=========================================================
Mỗi user được roll **1 lần/ngày** (reset 00:00 theo giờ server).
Kết quả gồm: Tier (SSS→D), tên động vật bản mệnh, và lời bình do Gemini sinh
dựa trên 77 tin nhắn gần nhất của user trong kênh.
"""

import logging
import random
import os
import json
from google import genai
from app.core.config import Config

log = logging.getLogger("bot.fortune")
from dataclasses import dataclass
from datetime import date, datetime


# ── Cấu hình Tier ─────────────────────────────────────────────────────────────

@dataclass
class Tier:
    name: str          # SSS, S, A, B, C, D
    label: str         # Tên đầy đủ
    weight: int        # Tỷ lệ xuất hiện (tổng = 100)
    color: int         # Màu Discord Embed (hex int)
    animals: list[str] # Danh sách động vật kèm emoji
    fortune_msg: str   # Lời bình vận may


TIERS: list[Tier] = [
    Tier(
        name="SSS",
        label="⚡ Thần Thoại",
        weight=5,
        color=0xFFD700,  # Vàng kim
        animals=[
            "🐉 Rồng Phương Đông",
            "🦄 Kỳ Lân Huyền Bí",
            "🦅 Đại Bàng Kim Cương",
            "🦚 Công Hoàng Gia",
            "🐳 Cá Voi Xanh Thần Thánh",
        ],
        fortune_msg=(
            "**Nhân phẩm bùng nổ!** Hôm nay làm gì cũng thắng, bước ra đường là nhặt được tiền.\n"
            "Crush sẽ chủ động nhắn tin cho bạn. 💰🔥"
        ),
    ),
    Tier(
        name="S",
        label="✨ Đại Cát",
        weight=10,
        color=0xFFA500,  # Cam vàng
        animals=[
            "🦁 Sư Tử Hoàng Kim",
            "🐯 Hổ Bạch Tuyết",
            "🦋 Bướm Rồng May Mắn",
            "🦜 Vẹt Vàng Thông Thái",
            "🐬 Cá Heo Thần Tài",
        ],
        fortune_msg=(
            "**Ngày mới tràn đầy năng lượng!** Mọi việc tiến triển thuận lợi.\n"
            "Crush có thể sẽ rep tin nhắn bạn đó. 😊✨"
        ),
    ),
    Tier(
        name="A",
        label="🌟 Cát Tường",
        weight=14,
        color=0x00CED1,  # Xanh ngọc
        animals=[
            "🐱 Mèo Thần Tài",
            "🐶 Chó Lục Địa",
            "🦊 Cáo Chân Thành",
            "🦦 Rái Cá Vui Vẻ",
            "🦭 Hải Cẩu Tinh Nghịch",
            "🐼 Gấu Trúc Thong Thả",
        ],
        fortune_msg=(
            "**Một ngày khá mượt mà!** Chơi game ít gặp tạ, code ít bug hơn thường ngày.\n"
            "Cứ tự tin mà tiến thôi! 🐾"
        ),
    ),
    Tier(
        name="B",
        label="☁️ Bình An",
        weight=50,
        color=0x7289DA,  # Discord blurple
        animals=[
            "🐢 Cụ Rùa Thảnh Thơi",
            "🦥 Lười Biếng Đạt Đạo",
            "🦆 Vịt Vui Vẻ",
            "🐑 Cừu Non Ngơ Ngác",
            "🐇 Thỏ Trắng Bình Yên",
        ],
        fortune_msg=(
            "**Cuộc sống êm đềm, không tốt không xấu.**\n"
            "Bình thường là một hạnh phúc. Hôm nay cứ flow theo nhịp cuộc đời thôi! 🌿"
        ),
    ),
    Tier(
        name="C",
        label="⚠️ Hung",
        weight=20,
        color=0xE67E22,  # Cam đỏ
        animals=[
            "🦙 Lạc Đà Vô Tri",
            "🦟 Muỗi Phiền Toái",
            "🐒 Khỉ Tấu Hài",
            "🕊️ Bồ Câu Bay Qua Đầu",
            "🐸 Ếch Dự Báo Mưa",
        ],
        fortune_msg=(
            "**Bước xuống giường bằng chân trái rồi...**\n"
            "Cẩn thận đổ vỡ hoặc mất tiền oan. Nhớ nhìn trước nhìn sau khi ra đường! 😬"
        ),
    ),
    Tier(
        name="D",
        label="💀 Đại Hung",
        weight=1,
        color=0x2F3136,  # Xám xịt đen
        animals=[
            "🪳 Gián Bay Ban Đêm",
            "🐷 Heo Đất Rỗng Ruột",
            "🦈 Cá Mập Mắc Cạn",
            "🐛 Sâu Đen Bất Hạnh",
        ],
        fortune_msg=(
            "**\"Chúa tể hẩm hiu\" đã giáng thế!** 💀\n"
            "Khuyến cáo: ở nhà đắp chăn ngủ, đừng làm gì cả. "
            "Tránh xa ví tiền, tránh xa crush, tránh xa mọi quyết định hôm nay."
        ),
    ),
]

# Danh sách tier và trọng số để dùng cho random.choices
_TIER_WEIGHTS = [t.weight for t in TIERS]


# ── Cooldown tracker (JSON File Persistence) ──────────────────────────────────
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database",
    "fortune_history.json"
)


def load_history() -> dict[str, str]:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"[fortune] Lỗi khi load history file: {e}")
        return {}


def save_history(history: dict[str, str]):
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log.error(f"[fortune] Lỗi khi save history file: {e}")


@dataclass
class FortuneResult:
    tier: Tier
    animal: str
    fortune_msg: str = ""       # Lời bình do Gemini sinh
    already_rolled: bool = False


class FortuneService:
    """Xử lý logic random vận may theo ngày."""

    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = Config.MODEL_NAME

    def generate_fortune_msg(self, tier: Tier, animal: str, messages: list[str]) -> str:
        """Gọi Gemini sinh lời bình vận may dựa trên tin nhắn thực của user."""
        if not messages:
            return tier.fortune_msg  # fallback về text cứng nếu không có tin nhắn

        chat_log = "\n".join(messages)
        # Tách bỏ emoji ở đầu tên động vật (ví dụ "🐉 Rồng Phương Đông" -> "Rồng Phương Đông")
        animal_name = " ".join(animal.split()[1:]) if len(animal.split()) > 1 else animal
        prompt = (
            f"Bạn là nhà tiên tri hài hước trên Discord.\n"
            f"User vừa roll được Tier **{tier.name}** ({tier.label.strip()}) – {animal_name} bản mệnh.\n"
            f"Dựa vào các tin nhắn gần đây của user dưới đây, hãy viết 2-3 câu luận giải vận may HÔM NAY cho họ.\n"
            f"Phong cách: hài hước, dí dỏm, có thể khen hoặc chọc nhẹ. Viết bằng tiếng Việt. Không cần chào hỏi.\n"
            f"Tier {tier.name} có nghĩa: {tier.fortune_msg.split(chr(10))[0]}\n\n"
            f"Tin nhắn gần đây của user:\n{chat_log}\n\n"
            f"Luận giải vận may:"
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result = response.text.strip() if response.text else ""
            return result or tier.fortune_msg
        except Exception as e:
            log.error(f"[fortune] Lỗi Gemini: {e}", exc_info=True)
            return tier.fortune_msg  # fallback

    def roll(self, user_id: int, messages: list[str] | None = None) -> FortuneResult:
        """Roll vận may cho user.

        Args:
            user_id: ID Discord của user.
            messages: Danh sách tin nhắn gần nhất của user (tối đa 77).
                      Nếu None/rỗng, dùng fortune_msg mặc định của Tier.
        """
        today = date.today()
        history = load_history()
        user_key = str(user_id)

        if user_key in history:
            try:
                last_roll_dt = datetime.fromisoformat(history[user_key])
                if last_roll_dt.date() == today:
                    return FortuneResult(tier=None, animal="", already_rolled=True)  # type: ignore[arg-type]
            except Exception as e:
                log.error(f"[fortune] Lỗi khi parse thời gian roll cũ của user {user_id}: {e}")

        secure_random = random.SystemRandom()
        tier: Tier = secure_random.choices(TIERS, weights=_TIER_WEIGHTS, k=1)[0]
        animal: str = secure_random.choice(tier.animals)
        fortune_msg = self.generate_fortune_msg(tier, animal, messages or [])

        history[user_key] = datetime.now().isoformat()
        save_history(history)
        return FortuneResult(tier=tier, animal=animal, fortune_msg=fortune_msg, already_rolled=False)

    def get_embed(self, result: FortuneResult, author_name: str) -> dict:
        """Trả về dict tham số để tạo discord.Embed từ FortuneResult.

        Caller tạo embed từ dict này, ví dụ:
            embed = discord.Embed(**service.get_embed(result, name))
        """
        tier = result.tier
        return {
            "title": f"🎲 Vận May Hôm Nay Của {author_name}",
            "description": (
                f"**Tier:** {tier.label}\n"
                f"**Động vật bản mệnh:** {result.animal}\n\n"
                f"{result.fortune_msg}"
            ),
            "color": tier.color,
        }
