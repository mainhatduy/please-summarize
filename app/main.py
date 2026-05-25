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


@bot.event
async def on_ready():
    log.info(f"Đã đăng nhập thành công với tài khoản: {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message):
    # Bỏ qua tin nhắn từ bot thực sự
    if message.author.bot:
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
        "`.tomtat [n]` – Tóm tắt n tin nhắn gần nhất (mặc định 300, tối đa 300)\n"
        "`.tomtat_time [phút]` – Tóm tắt tin nhắn trong n phút qua (mặc định 30, tối đa 1440)\n"
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
async def tomtat(ctx, n: int = 300):
    """Lệnh: .tomtat <n> – Tóm tắt n tin nhắn gần nhất (mặc định 300)"""
    log.info(f"[tomtat] Yêu cầu tóm tắt {n} tin nhắn | channel_id={ctx.channel.id}")

    # Kiểm tra cooldown
    remaining = _check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return

    if n <= 0 or n > 300:
        log.warning(f"[tomtat] Giá trị n={n} không hợp lệ")
        await ctx.send("Vui lòng nhập n từ 1 đến 300.")
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
async def tomtat_time(ctx, minutes: int = 30):
    """Lệnh: .tomtat_time <minutes> – Tóm tắt tin nhắn trong n phút trước (mặc định 30)"""
    log.info(f"[tomtat_time] Yêu cầu tóm tắt {minutes} phút | channel_id={ctx.channel.id}")

    # Kiểm tra cooldown
    remaining = _check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return

    if minutes <= 0 or minutes > 1440:
        log.warning(f"[tomtat_time] Giá trị minutes={minutes} không hợp lệ")
        await ctx.send("Vui lòng nhập số phút hợp lệ (1-1440).")
        return

    after_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    await _apply_channel_rate_limit(ctx.channel.id)
    log.debug(f"[tomtat_time] Lấy tin nhắn sau: {after_time.isoformat()}")

    messages = []
    skipped = 0
    skipped_bots = 0
    # limit=None để không bỏ sót tin nhắn trong giờ cao điểm,
    # chỉ giới hạn bởi khoảng thời gian after=
    async for msg in ctx.channel.history(limit=None, after=after_time):
        if msg.id == ctx.message.id:
            continue
        # Bỏ qua tin nhắn từ bot thực sự HOẶC từ chính self-bot này
        if msg.author.bot or msg.author.id == bot.user.id:
            log.debug(f"[tomtat_time] Bỏ qua tin nhắn từ bot/self: {msg.author.name}")
            skipped_bots += 1
            continue
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

    if not messages:
        log.info("[tomtat_time] Không có tin nhắn nào trong khoảng thời gian này.")
        await ctx.send("Không có đoạn hội thoại nào trong thời gian này.")
        return

    collected = len(messages)
    log.info(f"[tomtat_time] Đã thu thập được {collected} tin nhắn text – đang gọi Gemini API...")

    # Hiển thị metadata trước khi gọi Gemini
    await ctx.send(
        f"📊 Thu thập được **{collected}** tin nhắn text trong {minutes} phút qua"
        + (f" (bỏ qua {skipped} ảnh/file)" if skipped else "")
        + (f" (bỏ qua {skipped_bots} tin nhắn bot)" if skipped_bots else "")
        + "\nĐang gọi Gemini..."
    )

    summary = summarize_service.summarize(messages)

    log.info(f"[tomtat_time] Gemini trả về kết quả ({len(summary)} ký tự) – đang gửi...")
    await send_long(ctx, f"**Tóm tắt:**\n{summary}")
    log.info("[tomtat_time] Hoàn thành.")


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
