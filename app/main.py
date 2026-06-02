import asyncio
import logging
import random
import time
import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from app.core.config import Config
from app.services.summarize import SummarizeService
from app.services.music import MusicService
from app.services.fortune import FortuneService
from app.services.taixiu import TaiXiuService
from app.services.xinkeo import XinKeoService
from app.services.tarot import TarotService

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")
# Giảm noise từ thư viện bên ngoài, tắt duplicate do discord có handler riêng
for _lib in ("discord", "discord.http", "discord.gateway", "discord.client", "httpx", "httpcore"):
    _l = logging.getLogger(_lib)
    _l.setLevel(logging.INFO)
    _l.propagate = False  # Không đẩy lên root handler để tránh log bị in 2 lần

# ── Bot init ──────────────────────────────────────────────────────────────────
bot = commands.Bot(command_prefix=".", self_bot=True, help_command=None)
summarize_service = SummarizeService()
music_service = MusicService()
fortune_service = FortuneService()
taixiu_service = TaiXiuService()
xinkeo_service = XinKeoService()
tarot_service = TarotService()

# Cooldown tracker: {user_id: last_used_timestamp}
_COOLDOWN_SECONDS = 60
_cooldown_tracker: dict[int, float] = {}

# Rate limit giữa các lần fetch history theo channel
# Tránh spam Discord API, giảm nguy cơ bị detect là bot
_CHANNEL_RATE_LIMIT_SECONDS = 5       # delay tối thiểu (s) giữa 2 lần fetch cùng kênh
_channel_last_fetch: dict[int, float] = {}

# Jitter khi gửi nhiều chunk liên tiếp (send_long)
_SEND_JITTER_MIN = 0.3                # delay ngẫu nhiên tối thiểu giữa các chunk (s)
_SEND_JITTER_MAX = 0.8                # delay ngẫu nhiên tối đa giữa các chunk (s)

# Theo dõi thời gian bot ở một mình trong voice: {channel_id: alone_since_timestamp}
_alone_since: dict[int, float] = {}
_alone_checker_started = False


def get_connected_members(voice_client) -> list:
    """Trả về danh sách các thành viên đang kết nối trong cuộc gọi thoại."""
    channel = voice_client.channel
    if isinstance(channel, (discord.GroupChannel, discord.DMChannel)):
        connected = []
        # Kiểm tra bot của mình
        if channel.me and channel.me.voice and channel.me.voice.channel == channel:
            connected.append(channel.me)

        # Kiểm tra các thành viên khác
        if isinstance(channel, discord.GroupChannel):
            for user in channel.recipients:
                if user.voice and user.voice.channel == channel:
                    connected.append(user)
        elif isinstance(channel, discord.DMChannel):
            user = channel.recipient
            if user and user.voice and user.voice.channel == channel:
                connected.append(user)
        return connected
    else:
        # Kênh thoại Server (Guild VoiceChannel)
        if hasattr(channel, "members"):
            return channel.members
        return []


async def check_alone_voice_clients():
    """Tác vụ nền tự động rời voice nếu bot ở một mình quá 5 giây."""
    while not bot.is_closed():
        try:
            for voice_client in list(bot.voice_clients):
                if not voice_client.is_connected():
                    _alone_since.pop(voice_client.channel.id, None)
                    continue

                members = get_connected_members(voice_client)

                # Lọc ra các user thực sự khác ngoài bot
                active_users = [m for m in members if not m.bot and m.id != bot.user.id]

                if len(active_users) == 0:
                    # Không còn người dùng nào khác trong cuộc gọi thoại
                    if voice_client.channel.id not in _alone_since:
                        _alone_since[voice_client.channel.id] = time.monotonic()
                        log.info(f"[voice_alone] Bot ở một mình trong kênh {voice_client.channel.id}. Bắt đầu đếm ngược 5s...")
                    else:
                        elapsed = time.monotonic() - _alone_since[voice_client.channel.id]
                        if elapsed >= 5.0:
                            log.info(f"[voice_alone] Đã ở một mình quá 5s tại kênh {voice_client.channel.id}. Tự động rời voice.")
                            await voice_client.disconnect()
                            _alone_since.pop(voice_client.channel.id, None)
                else:
                    # Có người dùng khác trong cuộc gọi, reset bộ đếm thời gian
                    if voice_client.channel.id in _alone_since:
                        log.info(f"[voice_alone] Có người tham gia lại kênh {voice_client.channel.id}. Hủy đếm ngược.")
                        _alone_since.pop(voice_client.channel.id, None)
        except Exception as e:
            log.error(f"Lỗi trong tác vụ check_alone_voice_clients: {e}", exc_info=True)
        await asyncio.sleep(1.0)


@bot.event
async def on_ready():
    global _alone_checker_started
    log.info(f"Đã đăng nhập thành công với tài khoản: {bot.user} (ID: {bot.user.id})")
    if not _alone_checker_started:
        bot.loop.create_task(check_alone_voice_clients())
        _alone_checker_started = True


@bot.event
async def on_message(message):
    # Bỏ qua tin nhắn từ bot thực sự
    if message.author.bot:
        return

    # Nếu cấu hình CHANNEL_ID, chỉ nhận request từ channel đó
    if Config.CHANNEL_ID is not None and message.channel.id != Config.CHANNEL_ID:
        return

    content = message.content
    prefix = bot.command_prefix

    # Chỉ xử lý tin nhắn có tiền tố lệnh
    if not content.startswith(prefix):
        return

    # Parse tên lệnh và arguments
    without_prefix = content[len(prefix):]
    parts = without_prefix.split(maxsplit=1)
    if not parts:
        return

    command_name = parts[0].lower()
    args_str = parts[1] if len(parts) > 1 else ""

    log.info(
        f"Nhận lệnh | channel_id={message.channel.id} "
        f"| author={message.author} | command='{command_name}' | args='{args_str}'"
    )

    # Tìm lệnh trong bot (hỗ trợ cả alias)
    command = bot.get_command(command_name)
    if command is None:
        log.warning(f"Lệnh '{command_name}' không tồn tại trong bot.")
        return

    # Tạo context thủ công để bypass bộ lọc self_bot của discord.py-self
    ctx = await bot.get_context(message)
    ctx.command = command
    ctx.prefix = prefix
    ctx.invoked_with = command_name

    # Advance StringView qua prefix + command name để _parse_arguments
    # đọc đúng phần arguments (ví dụ '10'), không đọc lại '.tomtat 10'
    skip_len = len(prefix) + len(command_name)
    ctx.view.index = skip_len
    ctx.view.previous = skip_len

    log.debug(f"Đang invoke lệnh '{command.name}'...")
    try:
        await command.invoke(ctx)
    except Exception as e:
        log.error(f"Lỗi khi invoke lệnh '{command_name}': {e}", exc_info=True)
        await message.channel.send(f"⚠️ Có lỗi xảy ra: {e}")


@bot.event
async def on_command_error(ctx, error):
    log.error(f"Lỗi lệnh '{ctx.command}': {error}", exc_info=True)
    await ctx.send(f"⚠️ Có lỗi xảy ra khi thực hiện lệnh: {error}")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def send_long(ctx, text: str, chunk_size: int = 1900):
    """Chia text dài thành nhiều message để tránh giới hạn 2000 ký tự của Discord.
    Có random jitter delay giữa các chunk để hành vi giống người dùng thực.
    """
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    for idx, chunk in enumerate(chunks):
        await ctx.send(chunk)
        if idx < len(chunks) - 1:
            # Jitter ngẫu nhiên giữa các chunk, tránh flood
            delay = random.uniform(_SEND_JITTER_MIN, _SEND_JITTER_MAX)
            log.debug(f"[send_long] Jitter delay {delay:.2f}s trước chunk tiếp theo...")
            await asyncio.sleep(delay)


def _check_cooldown(user_id: int) -> float | None:
    """Kiểm tra cooldown. Trả về số giây còn lại nếu đang cooldown, None nếu OK."""
    now = time.monotonic()
    last_used = _cooldown_tracker.get(user_id)
    if last_used is not None:
        elapsed = now - last_used
        if elapsed < _COOLDOWN_SECONDS:
            return _COOLDOWN_SECONDS - elapsed
    _cooldown_tracker[user_id] = now
    return None


async def _apply_channel_rate_limit(channel_id: int):
    """Áp dụng rate limit theo channel: nếu fetch gần đây, sleep cho đủ khoảng cách.
    Giúp tránh spam Discord API và giảm nguy cơ bị nhận diện là bot.
    """
    now = time.monotonic()
    last_fetch = _channel_last_fetch.get(channel_id)
    if last_fetch is not None:
        elapsed = now - last_fetch
        if elapsed < _CHANNEL_RATE_LIMIT_SECONDS:
            wait = _CHANNEL_RATE_LIMIT_SECONDS - elapsed
            # Thêm jitter nhỏ để không quá đều
            wait += random.uniform(0.2, 1.0)
            log.info(f"[rate_limit] Channel {channel_id}: chờ {wait:.1f}s trước khi fetch...")
            await asyncio.sleep(wait)
    _channel_last_fetch[channel_id] = time.monotonic()


# ══════════════════════════════════════════════════════════════════════════════
# LỆNH HELP
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="help")
async def help_cmd(ctx):
    """Lệnh: .help – Hiển thị danh sách lệnh"""
    await ctx.send(
        "**📋 Danh sách lệnh:**\n"
        "`.tomtat [n]` – Tóm tắt n tin nhắn gần nhất (mặc định 50, tối đa 500)\n"
        "`.tomtat_time [giờ]` – Tóm tắt tin nhắn trong n giờ qua (mặc định 1, tối đa 12)\n"
        "`.get_luck` – Roll vận may hôm nay (1 lần/ngày, reset 00:00)\n"
        "`.taixiu` (hoặc `.tx`) – Chơi Tài Xỉu 3 xúc xắc (kèm chẵn lẻ)\n"
        "`.xinkeo <lời khấn>` (hoặc `.xk`) – Xin keo truyền thống\n"
        "`.tarot <câu hỏi>` – Xem bói Tarot (1 lá chính, 3 lá phụ)\n"
        "`.play <tên bài/link YouTube>` – Phát nhạc trong voice\n"
        "`.join` – Tham gia cuộc gọi thoại\n"
        "`.leave` / `.stop` – Rời cuộc gọi thoại\n"
        "`.help` – Hiển thị danh sách lệnh này\n"
        f"\n⏱️ Cooldown: {_COOLDOWN_SECONDS}s/user cho các lệnh tóm tắt."
    )


# ══════════════════════════════════════════════════════════════════════════════
# KÊNH TEXT – TÓM TẮT TIN NHẮN
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="tomtat", aliases=["sum_msgs"])
async def tomtat(ctx, n: int = 50):
    """Lệnh: .tomtat <n> – Tóm tắt n tin nhắn gần nhất (mặc định 50)"""
    log.info(f"[tomtat] Yêu cầu tóm tắt {n} tin nhắn | channel_id={ctx.channel.id}")

    # Kiểm tra cooldown
    remaining = _check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return

    if n <= 0 or n > 500:
        log.warning(f"[tomtat] Giá trị n={n} không hợp lệ")
        await ctx.send("Vui lòng nhập n từ 1 đến 500.")
        return

    await _apply_channel_rate_limit(ctx.channel.id)
    log.debug(f"[tomtat] Đang lấy lịch sử chat (limit={n + 1})...")
    messages = []
    skipped = 0
    skipped_bots = 0
    async for msg in ctx.channel.history(limit=n + 1):
        # Bỏ qua lệnh gọi bản thân
        if msg.id == ctx.message.id:
            continue
        # Bỏ qua tin nhắn từ bot thực sự HOẶC từ chính self-bot này
        # (self-bot là user account nên msg.author.bot == False, phải check id)
        if msg.author.bot or msg.author.id == bot.user.id:
            log.debug(f"[tomtat] Bỏ qua tin nhắn từ bot/self: {msg.author.name}")
            skipped_bots += 1
            continue
        # Bỏ qua tin nhắn chỉ có ảnh/file (không có nội dung text)
        if not msg.content.strip():
            log.debug(f"[tomtat] Bỏ qua tin nhắn không có text từ {msg.author.name} (chỉ có attachment/sticker)")
            skipped += 1
            continue
        # Bỏ qua tin nhắn là lệnh (bắt đầu bằng prefix)
        if msg.content.strip().startswith(bot.command_prefix):
            log.debug(f"[tomtat] Bỏ qua lệnh từ {msg.author.name}: {msg.content[:30]}")
            skipped += 1
            continue
        messages.append(f"{msg.author.name}: {msg.content}")

    messages.reverse()
    collected = len(messages)
    log.info(f"[tomtat] Đã thu thập được {collected} tin nhắn text – đang gọi Gemini API...")

    # Hiển thị metadata trước khi gọi Gemini
    await ctx.send(
        f"📊 Thu thập được **{collected}/{n}** tin nhắn text"
        + (f" (bỏ qua {skipped} ảnh/file)" if skipped else "")
        + (f" (bỏ qua {skipped_bots} tin nhắn bot)" if skipped_bots else "")
        + "\nĐang gọi Gemini..."
    )

    summary = summarize_service.summarize(messages)

    log.info(f"[tomtat] Gemini trả về kết quả ({len(summary)} ký tự) – đang gửi...")
    await send_long(ctx, f"**Tóm tắt:**\n{summary}")
    log.info("[tomtat] Hoàn thành.")


@bot.command(name="tomtat_time", aliases=["sum_time"])
async def tomtat_time(ctx, hours: float = 1.0):
    """Lệnh: .tomtat_time <hours> – Tóm tắt tin nhắn trong n giờ trước (mặc định 1)"""
    log.info(f"[tomtat_time] Yêu cầu tóm tắt {hours} giờ | channel_id={ctx.channel.id}")

    # Kiểm tra cooldown
    remaining = _check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return

    if hours <= 0 or hours > 12:
        log.warning(f"[tomtat_time] Giá trị hours={hours} không hợp lệ")
        await ctx.send("Vui lòng nhập số giờ hợp lệ (từ 0.1 đến 12).")
        return

    after_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    await _apply_channel_rate_limit(ctx.channel.id)
    log.debug(f"[tomtat_time] Lấy tin nhắn sau: {after_time.isoformat()}")

    messages = []
    skipped = 0
    skipped_bots = 0
    # Lấy lịch sử tin nhắn từ mới nhất về cũ nhất
    async for msg in ctx.channel.history(limit=None):
        if msg.id == ctx.message.id:
            continue
        # Bỏ qua tin nhắn từ bot thực sự HOẶC từ chính self-bot này
        if msg.author.bot or msg.author.id == bot.user.id:
            log.debug(f"[tomtat_time] Bỏ qua tin nhắn từ bot/self: {msg.author.name}")
            skipped_bots += 1
            continue
        # Nếu gặp tin nhắn có thời gian cũ hơn after_time, dừng lại
        if msg.created_at < after_time:
            break
        # Bỏ qua tin nhắn chỉ có ảnh/file (không có nội dung text)
        if not msg.content.strip():
            log.debug(f"[tomtat_time] Bỏ qua tin nhắn không có text từ {msg.author.name}")
            skipped += 1
            continue
        # Bỏ qua tin nhắn là lệnh (bắt đầu bằng prefix)
        if msg.content.strip().startswith(bot.command_prefix):
            log.debug(f"[tomtat_time] Bỏ qua lệnh từ {msg.author.name}: {msg.content[:30]}")
            skipped += 1
            continue
        messages.append(f"{msg.author.name}: {msg.content}")
        # Giới hạn tối đa 500 cuộc trò chuyện
        if len(messages) >= 500:
            break

    if not messages:
        log.info("[tomtat_time] Không có tin nhắn nào trong khoảng thời gian này.")
        await ctx.send("Không có đoạn hội thoại nào trong thời gian này.")
        return

    # Đảo ngược thứ tự để có thứ tự thời gian tăng dần (cũ đến mới) trước khi gửi cho Gemini
    messages.reverse()
    collected = len(messages)
    log.info(f"[tomtat_time] Đã thu thập được {collected} tin nhắn text – đang gọi Gemini API...")

    # Hiển thị metadata trước khi gọi Gemini
    await ctx.send(
        f"📊 Thu thập được **{collected}** tin nhắn text trong {hours} giờ qua"
        + (f" (bỏ qua {skipped} ảnh/file)" if skipped else "")
        + (f" (bỏ qua {skipped_bots} tin nhắn bot)" if skipped_bots else "")
        + "\nĐang gọi Gemini..."
    )

    summary = summarize_service.summarize(messages)

    log.info(f"[tomtat_time] Gemini trả về kết quả ({len(summary)} ký tự) – đang gửi...")
    await send_long(ctx, f"**Tóm tắt:**\n{summary}")
    log.info("[tomtat_time] Hoàn thành.")


# ══════════════════════════════════════════════════════════════════════════════
# RANDOM VẬN MAY – GET LUCK
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="get_luck", aliases=["luck", "vanmay"])
async def get_luck(ctx):
    """Lệnh: .get_luck – Roll vận may hôm nay (1 lần/ngày, reset 00:00)"""
    log.info(f"[get_luck] Yêu cầu roll vận may | author={ctx.author} | channel_id={ctx.channel.id}")

    # Fetch tối đa 77 tin nhắn của chính user gọi lệnh trong kênh
    await _apply_channel_rate_limit(ctx.channel.id)
    user_messages: list[str] = []
    async for msg in ctx.channel.history(limit=500):
        if msg.id == ctx.message.id:
            continue
        if msg.author.id != ctx.author.id:
            continue
        if not msg.content.strip() or msg.content.strip().startswith(bot.command_prefix):
            continue
        user_messages.append(msg.content.strip())
        if len(user_messages) >= 77:
            break

    user_messages.reverse()  # cũ → mới
    log.info(f"[get_luck] Thu thập {len(user_messages)} tin nhắn của {ctx.author} để gửi Gemini.")

    result = fortune_service.roll(ctx.author.id, messages=user_messages)

    if result.already_rolled:
        log.info(f"[get_luck] User {ctx.author} đã roll hôm nay rồi.")
        await ctx.send(
            f"🎲 **{ctx.author.name}**, bạn đã roll vận may hôm nay rồi!\n"
            "Hãy quay lại vào **00:00 ngày mai** để thử lại nhé. 🌙"
        )
        return

    tier = result.tier
    embed_data = fortune_service.get_embed(result, ctx.author.name)
    embed = discord.Embed(**embed_data)
    embed.add_field(
        name="📊 Tỷ lệ xuất hiện",
        value=f"`{tier.weight}%` – {'Cực hiếm! 🔥' if tier.weight <= 5 else 'Hiếm! ✨' if tier.weight <= 14 else 'Thường gặp'}",
        inline=False,
    )
    embed.set_footer(text="Roll lại vào ngày mai | Chúc bạn một ngày tốt lành! 🍀")

    log.info(f"[get_luck] {ctx.author} rolled Tier {tier.name} – {result.animal}")

    # Discord self-bot không dùng send(embed=...) được trực tiếp như bot thường,
    # nên gửi dạng text đẹp thay thế
    tier_bar = {
        "SSS": "🟡🟡🟡🟡🟡",
        "S":   "🟠🟠🟠🟠⬜",
        "A":   "🟢🟢🟢⬜⬜",
        "B":   "🔵🔵⬜⬜⬜",
        "C":   "🔴🔴⬜⬜⬜",
        "D":   "⚫⬜⬜⬜⬜",
    }
    bar = tier_bar.get(tier.name, "")

    text = (
        f"`{ctx.author.name}`\n"
        f"# **{tier.label}**\n"
        f"## **{result.animal}**\n"
        f"\n"
        f"{result.fortune_msg}\n"
    )
    await ctx.send(text)
    log.info("[get_luck] Hoàn thành.")


# ══════════════════════════════════════════════════════════════════════════════
# GAME TÀI XỈU - TAI XIU
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="taixiu", aliases=["tx"])
async def taixiu(ctx):
    """Lệnh: .taixiu – Chơi Tài Xỉu 3 xúc xắc ngẫu nhiên"""
    log.info(f"[taixiu] Yêu cầu chơi Tài Xỉu | author={ctx.author} | channel_id={ctx.channel.id}")
    
    result = taixiu_service.roll()
    text = taixiu_service.get_result_text(ctx.author.name, result)
    
    await ctx.send(text)
    log.info(f"[taixiu] Hoàn thành roll cho {ctx.author.name}: {result['rolls']} -> {result['result_type']}")


# ══════════════════════════════════════════════════════════════════════════════
# XIN KEO TRUYỀN THỐNG - XIN KEO
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="xinkeo", aliases=["xk"])
async def xinkeo(ctx, *, wish: str = ""):
    """Lệnh: .xinkeo <lời khấn> – Mô phỏng nghi lễ xin keo truyền thống"""
    log.info(f"[xinkeo] Yêu cầu xin keo | author={ctx.author} | wish='{wish}' | channel_id={ctx.channel.id}")
    if not wish.strip():
        await ctx.send("🙏 Vui lòng nhập lời khấn nguyện. Ví dụ: `.xinkeo Con xin sức khỏe bình an.`")
        return

    # Sinh kết quả gieo keo
    roll_result = xinkeo_service.roll()
    
    wait_msg = await ctx.send(
        f"⚪ ⚫ **{ctx.author.name}** đang thành tâm dâng hương khấn nguyện:\n"
        f"*\"{wish}\"*\n\n"
        f"*Đang gieo quẻ xin keo...*"
    )

    loop = asyncio.get_event_loop()
    luan_giai = await loop.run_in_executor(None, xinkeo_service.generate_luan_giai, wish, roll_result)

    result_type = roll_result["result"]
    icon1 = roll_result["icon1"]
    icon2 = roll_result["icon2"]
    
    result_text = (
        f"🙏 **Quẻ Xin Keo**\n"
        f"**Người cầu:** {ctx.author.name}\n"
        f"**Tâm nguyện:** *\"{wish}\"*\n"
        f"**Quẻ gieo:** {icon1} {icon2} ({result_type})\n\n"
        f"**Lời luận giải:**\n{luan_giai}"
    )
    
    
    await wait_msg.edit(content=result_text)
    log.info(f"[xinkeo] Hoàn thành gieo keo cho {ctx.author.name}: {result_type}")


# ══════════════════════════════════════════════════════════════════════════════
# TAROT ĐỌC BÀI - TAROT
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="tarot")
async def tarot(ctx, *, question: str = ""):
    """Lệnh: .tarot <câu hỏi> – Xem Tarot (1 lá chính, 3 lá phụ)"""
    log.info(f"[tarot] Yêu cầu xem bói | author={ctx.author} | question='{question}' | channel_id={ctx.channel.id}")
    if not question.strip():
        await ctx.send("🔮 Vui lòng nhập câu hỏi của bạn. Ví dụ: `.tarot Hôm nay tôi có may mắn về tình duyên không?`")
        return

    wait_msg = await ctx.send(
        f"🔮 **{ctx.author.name}** đang hỏi: *\"{question}\"*\n"
        f"*Đang xáo bài và kết nối với các tinh linh...*"
    )

    # Rút bài với seed từ câu hỏi và thời gian hiện tại
    draw_result = tarot_service.draw_cards(question)
    
    # Render tên bài đang rút (hiệu ứng)
    def fmt_card(c):
        return f"**{c.name}** ({'Ngược' if c.is_reversed else 'Xuôi'})"
        
    drawn_text = (
        f"🔮 **Trải bài của {ctx.author.name}**\n"
        f"**Câu hỏi:** *\"{question}\"*\n\n"
        f"✨ **Lá bài chính:** {fmt_card(draw_result['key_card'])}\n"
        f"🃏 **3 lá bài phụ:** " + ", ".join(fmt_card(c) for c in draw_result["supporting_cards"]) + "\n\n"
        f"*Đang chờ thông điệp từ cõi tâm linh...*"
    )
    await wait_msg.edit(content=drawn_text)
    
    # Sinh luận giải
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(None, tarot_service.generate_reading, question, draw_result, ctx.author.name)
    
    final_text = (
        f"🔮 **TRẢI BÀI TAROT**\n"
        f"**Người xem:** {ctx.author.name}\n"
        f"**Câu hỏi:** *\"{question}\"*\n\n"
        f"✨ **Lá bài chính (Key):** {fmt_card(draw_result['key_card'])}\n"
        f"🃏 **Lá bài phụ (Support):** " + ", ".join(fmt_card(c) for c in draw_result["supporting_cards"]) + "\n\n"
        f"**📜 Lời Luận Giải:**\n{reading}"
    )
    
    # Chia nhỏ nếu độ dài vượt quá giới hạn discord
    if len(final_text) > 1900:
        await wait_msg.delete()
        await send_long(ctx, final_text)
    else:
        await wait_msg.edit(content=final_text)
        
    log.info(f"[tarot] Hoàn thành đọc Tarot cho {ctx.author.name}")


# ══════════════════════════════════════════════════════════════════════════════
# KÊNH VOICE – PHÁT NHẠC YOUTUBE
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="join")
async def join(ctx):
    """Lệnh: .join – Tham gia vào cuộc gọi thoại hiện tại của nhóm chat"""
    log.info(f"[join] Yêu cầu tham gia voice | channel_id={ctx.channel.id}")
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if voice_client and voice_client.is_connected():
        log.info("[join] Bot đã ở trong cuộc gọi thoại rồi.")
        await ctx.send("Bot đã ở trong cuộc gọi thoại.")
        return

    try:
        if isinstance(ctx.channel, (discord.GroupChannel, discord.DMChannel)):
            await ctx.channel.connect(ring=False)
        else:
            await ctx.channel.connect()
        log.info("[join] Đã kết nối vào cuộc gọi thoại thành công.")
        await ctx.send("Đã kết nối vào cuộc gọi thoại.")
    except Exception as e:
        log.error(f"[join] Không thể kết nối: {e}", exc_info=True)
        await ctx.send(f"Không thể tham gia cuộc gọi thoại: {str(e)}")


@bot.command(name="leave", aliases=["stop"])
async def leave(ctx):
    """Lệnh: .leave – Rời cuộc gọi thoại và dừng phát nhạc"""
    log.info(f"[leave] Yêu cầu rời voice | channel_id={ctx.channel.id}")
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if voice_client and voice_client.is_connected():
        if voice_client.is_playing():
            voice_client.stop()
            log.debug("[leave] Đã dừng phát nhạc.")
        await voice_client.disconnect()
        log.info("[leave] Đã rời cuộc gọi thoại.")
        await ctx.send("Đã rời cuộc gọi thoại.")
    else:
        log.warning("[leave] Bot không ở trong cuộc gọi thoại của kênh này.")
        await ctx.send("Bot không ở trong cuộc gọi thoại nào của kênh này.")


@bot.command(name="play")
async def play(ctx, *, query: str):
    """Lệnh: .play <tên bài hát hoặc link YouTube> – Phát nhạc trong cuộc gọi thoại"""
    log.info(f"[play] Yêu cầu phát nhạc | query='{query}' | channel_id={ctx.channel.id}")

    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        log.debug("[play] Chưa kết nối voice – đang tham gia...")
        try:
            if isinstance(ctx.channel, (discord.GroupChannel, discord.DMChannel)):
                voice_client = await ctx.channel.connect(ring=False)
            else:
                voice_client = await ctx.channel.connect()
            log.info("[play] Đã kết nối voice thành công.")
        except Exception as e:
            log.error(f"[play] Không thể kết nối voice: {e}", exc_info=True)
            await ctx.send(f"Không thể kết nối vào cuộc gọi thoại để phát nhạc: {str(e)}")
            return

    await ctx.send(f"Đang tìm kiếm bài hát: `{query}`...")

    try:
        log.debug(f"[play] Đang trích xuất thông tin từ yt-dlp cho query='{query}'...")
        info = await music_service.extract_info(query)
        audio_url = info.get('url')
        title = info.get('title', 'Không rõ tiêu đề')
        log.info(f"[play] Tìm thấy bài: '{title}'")

        if not audio_url:
            log.error("[play] Không tìm thấy URL audio trong kết quả yt-dlp.")
            await ctx.send("Không thể lấy đường dẫn audio từ video này.")
            return

        if voice_client.is_playing():
            log.debug("[play] Đang phát bài khác – dừng lại để phát bài mới.")
            voice_client.stop()

        source = discord.FFmpegPCMAudio(audio_url, **music_service.ffmpeg_options)
        voice_client.play(
            source,
            after=lambda e: log.error(f"[play] Lỗi khi phát: {e}") if e else log.info("[play] Phát nhạc hoàn tất.")
        )
        log.info(f"[play] Đang phát: '{title}'")
        await ctx.send(f"🎶 Đang phát: **{title}**")
    except Exception as e:
        log.error(f"[play] Lỗi không mong muốn: {e}", exc_info=True)
        await ctx.send(f"Có lỗi xảy ra khi phát nhạc: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_placeholder_discord = not Config.DISCORD_TOKEN or "your_discord_bot_token" in Config.DISCORD_TOKEN
    is_placeholder_gemini = not Config.GEMINI_API_KEY or "your_gemini_api_key" in Config.GEMINI_API_KEY

    if is_placeholder_discord or is_placeholder_gemini:
        log.critical("Vui lòng thiết lập DISCORD_TOKEN và GEMINI_API_KEY thực tế trong file .env")
    else:
        log.info("Đang khởi động bot...")
        bot.run(Config.DISCORD_TOKEN)
