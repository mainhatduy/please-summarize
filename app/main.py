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
from app.services.kinhdich import KinhDichService
from app.services.tiktok import TikTokService

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
kinhdich_service = KinhDichService()
tiktok_service = TikTokService()

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

# Hàng đợi nhạc theo voice channel id
_song_queues: dict[int, list[dict]] = {}
_currently_playing: dict[int, dict] = {}
_queue_text_channels: dict[int, discord.abc.Messageable] = {}
_skip_requests: set[int] = set()
_queue_messages: dict[int, discord.Message] = {}  # Lưu tin nhắn queue cuối cùng để edit


def format_queue(channel_id: int) -> str:
    queue = _song_queues.get(channel_id, [])
    if not queue:
        return "(Không có bài nào trong hàng đợi.)"

    lines = [f"{idx}. {item['title']}" for idx, item in enumerate(queue, start=1)]
    return "\n".join(lines)


def _build_queue_text(channel_id: int, header: str = "") -> str:
    """Tạo nội dung text đầy đủ cho tin nhắn queue (bài đang phát + hàng đợi)."""
    currently = _currently_playing.get(channel_id)
    queue = _song_queues.get(channel_id, [])

    parts = []
    if header:
        parts.append(header)
    parts.append("")
    parts.append("🎵 **Danh sách phát nhạc:**")
    parts.append("")
    if currently:
        parts.append(f"▶️ **Đang phát:** {currently['title']}")
    if queue:
        parts.append("")
        parts.append("**📜 Hàng đợi:**")
        parts.append(format_queue(channel_id))
    elif currently:
        parts.append("")
        parts.append("*(Không có bài nào trong hàng đợi)*")
    return "\n".join(parts)


async def _update_queue_message(channel_id: int, header: str = ""):
    """Edit tin nhắn queue cuối cùng. Nếu không tìm thấy thì gửi tin nhắn mới."""
    text_channel = _queue_text_channels.get(channel_id)
    if not text_channel:
        log.debug(f"[queue_msg] Không có text channel lưu cho kênh {channel_id}.")
        return

    content = _build_queue_text(channel_id, header)
    existing_msg = _queue_messages.get(channel_id)

    if existing_msg:
        try:
            await existing_msg.edit(content=content)
            log.debug(f"[queue_msg] Đã edit tin nhắn queue cho kênh {channel_id}.")
            return
        except Exception as e:
            log.warning(f"[queue_msg] Không thể edit tin nhắn cũ: {e}. Sẽ gửi tin nhắn mới.")

    # Fallback: gửi tin nhắn mới nếu edit thất bại hoặc chưa có
    try:
        msg = await text_channel.send(content)
        _queue_messages[channel_id] = msg
        log.debug(f"[queue_msg] Đã gửi tin nhắn queue mới cho kênh {channel_id}.")
    except Exception as e:
        log.error(f"[queue_msg] Lỗi khi gửi tin nhắn queue: {e}", exc_info=True)


def get_voice_client_by_channel(channel_id: int):
    return next((vc for vc in bot.voice_clients if vc.channel.id == channel_id), None)


def _play_after(channel_id: int, error):
    if error:
        log.error(f"[play] Lỗi khi phát: {error}")

    if channel_id in _skip_requests:
        log.debug(f"[play] Bỏ qua callback after do lệnh skip đang xử lý ở kênh {channel_id}.")
        _skip_requests.discard(channel_id)
        return

    bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(_play_next_track(channel_id)))


async def _play_next_track(channel_id: int):
    voice_client = get_voice_client_by_channel(channel_id)
    if not voice_client or not voice_client.is_connected():
        _song_queues.pop(channel_id, None)
        _currently_playing.pop(channel_id, None)
        _queue_text_channels.pop(channel_id, None)
        _queue_messages.pop(channel_id, None)
        return

    queue = _song_queues.get(channel_id, [])
    if not queue:
        _currently_playing.pop(channel_id, None)
        return

    next_track = queue.pop(0)
    if queue:
        _song_queues[channel_id] = queue
    else:
        _song_queues.pop(channel_id, None)

    try:
        source = discord.FFmpegPCMAudio(next_track['audio_url'], **music_service.ffmpeg_options)
        voice_client.play(
            source,
            after=lambda error: _play_after(channel_id, error)
        )
        _currently_playing[channel_id] = next_track

        # Edit tin nhắn queue cuối cùng thay vì gửi mới
        await _update_queue_message(channel_id, header=f"▶️ Đang phát tiếp: **{next_track['title']}**")
    except Exception as e:
        log.error(f"[play_after] Lỗi khi phát bài tiếp theo: {e}", exc_info=True)
        text_channel = _queue_text_channels.get(channel_id)
        if text_channel:
            await text_channel.send(f"Có lỗi khi phát bài tiếp theo: {str(e)}")


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

    # Bỏ qua tin nhắn từ chính mình (self-bot)
    if message.author.id == bot.user.id:
        return

    # Nếu cấu hình CHANNEL_ID, chỉ nhận request từ channel đó
    if Config.CHANNEL_ID is not None and message.channel.id != Config.CHANNEL_ID:
        return

    content = message.content

    # ── AUTO-DETECT TIKTOK ────────────────────────────────────────
    tiktok_url = tiktok_service.detect_tiktok_url(content)
    if tiktok_url:
        await handle_tiktok(message, tiktok_url)
        return  # Đã xử lý TikTok, không cần check command nữa
    # ──────────────────────────────────────────────────────────────

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
# AUTO TIKTOK – DOWNLOAD VIDEO / ẢNH
# ══════════════════════════════════════════════════════════════════════════════

async def handle_tiktok(message, url: str):
    """Tự động tải và gửi video/ảnh TikTok khi detect link."""
    log.info(f"[tiktok] Detected TikTok URL: {url} | channel_id={message.channel.id}")
    await message.add_reaction("⏳")

    result = None
    try:
        result = await tiktok_service.download(url)

        if result.content_type == "video":
            if result.file_size_mb > 10:
                await message.channel.send(result.direct_url)
            else:
                file = discord.File(result.file_path)
                await message.channel.send(file=file)

        elif result.content_type == "slideshow":
            batch_size = 10
            for i in range(0, len(result.image_paths), batch_size):
                batch = result.image_paths[i:i + batch_size]
                files = [discord.File(p) for p in batch]
                await message.channel.send(files=files)
                if i + batch_size < len(result.image_paths):
                    await asyncio.sleep(random.uniform(_SEND_JITTER_MIN, _SEND_JITTER_MAX))

        await message.remove_reaction("⏳", bot.user)
        await message.add_reaction("✅")
        log.info(f"[tiktok] Hoàn thành gửi {result.content_type} cho channel {message.channel.id}")

    except Exception as e:
        log.error(f"[tiktok] Error: {e}", exc_info=True)
        try:
            await message.remove_reaction("⏳", bot.user)
            await message.add_reaction("❌")
        except Exception:
            pass

    finally:
        if result is not None:
            paths_to_clean = []
            if result.file_path:
                paths_to_clean.append(result.file_path)
            if result.image_paths:
                paths_to_clean.extend(result.image_paths)
            tiktok_service.cleanup(*paths_to_clean)


# ══════════════════════════════════════════════════════════════════════════════
# LỆNH HELP
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="help")
async def help_cmd(ctx):
    """Lệnh: .help – Hiển thị danh sách lệnh"""
    await ctx.send(
        "**📋 Danh sách lệnh:**\n"
        "🎬 **Auto TikTok:** Paste link TikTok → bot tự gửi video/ảnh\n"
        "`.tomtat [n]` – Tóm tắt n tin nhắn gần nhất (mặc định 50, tối đa 500)\n"
        "`.tomtat_time [giờ]` – Tóm tắt tin nhắn trong n giờ qua (mặc định 1, tối đa 12)\n"
        "`.get_luck` – Roll vận may hôm nay (1 lần/ngày, reset 00:00)\n"
        "`.taixiu` (hoặc `.tx`) – Chơi Tài Xỉu 3 xúc xắc (kèm chẵn lẻ)\n"
        "`.xinkeo <lời khấn>` (hoặc `.xk`) – Xin keo truyền thống\n"
        "`.tarot <câu hỏi>` – Xem bói Tarot (1 lá chính, 3 lá phụ)\n"
        "`.rutque <câu hỏi>` (hoặc `.rq`) – Rút quẻ Kinh Dịch\n"
        "`.luachon <câu hỏi và các lựa chọn>` (hoặc `.lc`) – Kinh Dịch đưa ra quyết định\n"
        "`.play <tên bài/link YouTube>` – Phát nhạc trong voice\n"
        "`.next` – Chuyển sang bài hát tiếp theo trong hàng đợi\n"
        "`.queue` – Xem danh sách hàng đợi nhạc\n"
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
        f"**Người cầu:** {ctx.author.mention}\n"
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
    draw_result = tarot_service.draw_cards()
    
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
        f"**Người xem:** {ctx.author.mention}\n"
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
# RÚT QUẺ KINH DỊCH
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="rutque", aliases=["rq", "kinhdich"])
async def rutque(ctx, *, question: str = ""):
    """Lệnh: .rutque <câu hỏi> – Rút quẻ Kinh Dịch và luận giải"""
    log.info(f"[rutque] Yêu cầu rút quẻ | author={ctx.author} | question='{question}' | channel_id={ctx.channel.id}")
    if not question.strip():
        await ctx.send("☰ Vui lòng nhập câu hỏi của bạn. Ví dụ: `.rutque Hôm nay tôi có nên đầu tư không?`")
        return

    wait_msg = await ctx.send(
        f"☰ **{ctx.author.name}** đang hỏi: *\"{question}\"*\n"
        f"*Đang thành tâm rút quẻ Kinh Dịch...*"
    )

    # Rút quẻ
    hexagram = kinhdich_service.draw_hexagram(question)
    hex_text = kinhdich_service.format_hexagram_text(hexagram)

    # Hiển thị quẻ đã rút, chờ luận giải
    drawn_text = (
        f"☰ **Quẻ Kinh Dịch của {ctx.author.name}**\n"
        f"**Câu hỏi:** *\"{question}\"*\n\n"
        f"{hex_text}\n"
        f"*Đang luận giải quẻ dịch...*"
    )
    await wait_msg.edit(content=drawn_text)

    # Sinh luận giải bằng Gemini
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None, kinhdich_service.generate_reading, question, hexagram, ctx.author.name
    )

    final_text = (
        f"☰ **QUẺ KINH DỊCH**\n"
        f"**Người hỏi:** {ctx.author.mention}\n"
        f"**Câu hỏi:** *\"{question}\"*\n\n"
        f"{hex_text}\n"
        f"**📜 Lời Luận Giải:**\n{reading}"
    )

    # Chia nhỏ nếu vượt giới hạn Discord
    if len(final_text) > 1900:
        await wait_msg.delete()
        await send_long(ctx, final_text)
    else:
        await wait_msg.edit(content=final_text)

    # Gửi hình minh họa quẻ dịch
    image_url = f"https://dich.kabala.vn/img/bai-kinh-dich/{hexagram['so']}.png"
    await ctx.send(image_url)

    log.info(f"[rutque] Hoàn thành rút quẻ cho {ctx.author.name}")


# ══════════════════════════════════════════════════════════════════════════════
# LỰA CHỌN KINH DỊCH
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="luachon", aliases=["lc", "chon"])
async def luachon(ctx, *, question_and_choices: str = ""):
    """Lệnh: .luachon <câu hỏi và các lựa chọn> – Nhờ quẻ Kinh Dịch quyết định lựa chọn"""
    log.info(f"[luachon] Yêu cầu lựa chọn | author={ctx.author} | question='{question_and_choices}' | channel_id={ctx.channel.id}")
    if not question_and_choices.strip():
        await ctx.send("☰ Vui lòng nhập câu hỏi và các lựa chọn. Ví dụ: `.luachon Trưa nay ăn gì? Phở hay Cơm tấm?`")
        return

    wait_msg = await ctx.send(
        f"☰ **{ctx.author.name}** đang phân vân: *\"{question_and_choices}\"*\n"
        f"*Đang rút quẻ Kinh Dịch để tìm ra lựa chọn tốt nhất...*"
    )

    # Rút quẻ
    hexagram = kinhdich_service.draw_hexagram(question_and_choices)
    hex_text = kinhdich_service.format_hexagram_text(hexagram)

    # Hiển thị quẻ đã rút, chờ luận giải
    drawn_text = (
        f"☰ **Quẻ Kinh Dịch của {ctx.author.name}**\n"
        f"**Phân vân:** *\"{question_and_choices}\"*\n\n"
        f"{hex_text}\n"
        f"*Đang xin lời khuyên từ cõi tâm linh để đưa ra quyết định...*"
    )
    await wait_msg.edit(content=drawn_text)

    # Sinh luận giải bằng Gemini
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None, kinhdich_service.generate_choice_reading, question_and_choices, hexagram, ctx.author.name
    )

    final_text = (
        f"☰ **QUYẾT ĐỊNH TỪ KINH DỊCH**\n"
        f"**Người hỏi:** {ctx.author.mention}\n"
        f"**Phân vân:** *\"{question_and_choices}\"*\n\n"
        f"{hex_text}\n"
        f"{reading}"
    )

    # Chia nhỏ nếu vượt giới hạn Discord
    if len(final_text) > 1900:
        await wait_msg.delete()
        await send_long(ctx, final_text)
    else:
        await wait_msg.edit(content=final_text)

    log.info(f"[luachon] Hoàn thành lựa chọn cho {ctx.author.name}")


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
            _skip_requests.add(voice_client.channel.id)
            voice_client.stop()
            log.debug("[leave] Đã dừng phát nhạc.")
        await voice_client.disconnect()
        _song_queues.pop(voice_client.channel.id, None)
        _currently_playing.pop(voice_client.channel.id, None)
        _queue_text_channels.pop(voice_client.channel.id, None)
        _queue_messages.pop(voice_client.channel.id, None)
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

    search_msg = await ctx.send(f"Đang tìm kiếm bài hát: `{query}`...")

    try:
        log.debug(f"[play] Đang trích xuất thông tin từ yt-dlp cho query='{query}'...")
        info = await music_service.extract_info(query)
        # Xóa tin nhắn tìm kiếm sau khi có kết quả
        try:
            await search_msg.delete()
        except Exception:
            pass
        audio_url = info.get('url')
        title = info.get('title', 'Không rõ tiêu đề')
        log.info(f"[play] Tìm thấy bài: '{title}'")

        if not audio_url:
            log.error("[play] Không tìm thấy URL audio trong kết quả yt-dlp.")
            await ctx.send("Không thể lấy đường dẫn audio từ video này.")
            return

        channel_id = voice_client.channel.id
        _queue_text_channels[channel_id] = ctx.channel

        if voice_client.is_playing():
            queue = _song_queues.setdefault(channel_id, [])
            queue.append({
                'query': query,
                'title': title,
                'audio_url': audio_url,
            })
            log.info(f"[play] Đã xếp hàng bài mới: '{title}' vào kênh {channel_id}.")
            # Edit tin nhắn queue cuối cùng thay vì gửi mới
            await _update_queue_message(channel_id, header=f"⏳ Đã thêm vào hàng đợi: **{title}**")
            return

        source = discord.FFmpegPCMAudio(audio_url, **music_service.ffmpeg_options)
        voice_client.play(
            source,
            after=lambda error: _play_after(channel_id, error)
        )
        _currently_playing[channel_id] = {'query': query, 'title': title, 'audio_url': audio_url}
        log.info(f"[play] Đang phát: '{title}'")
        # Gửi tin nhắn queue mới khi bắt đầu phát bài đầu tiên
        await _update_queue_message(channel_id, header=f"🎶 Đang phát: **{title}**")
    except Exception as e:
        log.error(f"[play] Lỗi không mong muốn: {e}", exc_info=True)
        await ctx.send(f"Có lỗi xảy ra khi phát nhạc: {str(e)}")


@bot.command(name="next", aliases=["skip"])
async def next_track(ctx):
    """Lệnh: .next (hoặc .skip) – Chuyển sang bài hát tiếp theo trong hàng đợi"""
    log.info(f"[next] Yêu cầu chuyển bài kế tiếp | channel_id={ctx.channel.id}")
    
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        log.warning("[next] Bot không ở trong cuộc gọi thoại nào.")
        await ctx.send("❌ Bot không ở trong cuộc gọi thoại nào. Hãy dùng `.play` để phát nhạc trước.")
        return
    
    if not voice_client.is_playing():
        log.warning("[next] Không có bài hát nào đang phát.")
        await ctx.send("❌ Không có bài hát nào đang phát. Hãy dùng `.play` để phát nhạc trước.")
        return
    
    channel_id = voice_client.channel.id
    queue = _song_queues.get(channel_id, [])
    
    if not queue:
        log.info(f"[next] Không có bài kế tiếp trong hàng đợi của kênh {channel_id}.")
        await ctx.send("❌ Không có bài kế tiếp trong hàng đợi.")
        return
    
    # Chỉ peek bài tiếp theo để thông báo, KHÔNG pop — để _play_next_track tự xử lý
    next_song_title = queue[0]['title']
    log.info(f"[next] Đang skip bài hiện tại, bài tiếp theo sẽ là: '{next_song_title}'")
    
    # Dừng bài hiện tại — callback _play_after sẽ tự gọi _play_next_track
    # để pop bài tiếp theo từ queue và phát, tránh race condition double-pop
    # _play_next_track sẽ tự edit tin nhắn queue
    voice_client.stop()


@bot.command(name="queue")
async def show_queue(ctx):
    """Lệnh: .queue – Xem danh sách hàng đợi nhạc hiện tại"""
    log.info(f"[queue] Yêu cầu xem hàng đợi | channel_id={ctx.channel.id}")
    
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        log.warning("[queue] Bot không ở trong cuộc gọi thoại nào.")
        await ctx.send("❌ Bot không ở trong cuộc gọi thoại nào.")
        return
    
    channel_id = voice_client.channel.id
    currently = _currently_playing.get(channel_id)
    queue = _song_queues.get(channel_id, [])
    
    if not currently and not queue:
        log.info("[queue] Không có bài nào đang phát hoặc trong hàng đợi.")
        await ctx.send("Không có bài hát nào đang phát hoặc trong hàng đợi.")
        return
    
    # .queue luôn gửi tin nhắn MỚI và lưu reference để các lần update sau edit vào đây
    text = _build_queue_text(channel_id)
    msg = await ctx.send(text)
    _queue_messages[channel_id] = msg
    
    log.info(f"[queue] Gửi danh sách hàng đợi mới với {len(queue)} bài")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    is_placeholder_discord = not Config.DISCORD_TOKEN or "your_discord_bot_token" in Config.DISCORD_TOKEN
    is_placeholder_gemini = not Config.GEMINI_API_KEY or "your_gemini_api_key" in Config.GEMINI_API_KEY

    if is_placeholder_discord or is_placeholder_gemini:
        log.critical("Vui lòng thiết lập DISCORD_TOKEN và GEMINI_API_KEY thực tế trong file .env")
    else:
        log.info("Đang khởi động bot...")
        bot.run(Config.DISCORD_TOKEN)
