"""Voice connection and music queue commands."""

import asyncio
import time

import discord

from app.bot.logging import log
from app.bot.runtime import bot, music_service

_song_queues: dict[int, list[dict]] = {}
_currently_playing: dict[int, dict] = {}
_queue_text_channels: dict[int, discord.abc.Messageable] = {}
_queue_messages: dict[int, discord.Message] = {}
_skip_requests: set[int] = set()
_alone_since: dict[int, float] = {}


def format_queue(channel_id: int) -> str:
    queue = _song_queues.get(channel_id, [])
    if not queue:
        return "(Không có bài nào trong hàng đợi.)"
    return "\n".join(
        f"{index}. {item['title']}" for index, item in enumerate(queue, start=1)
    )


def _build_queue_text(channel_id: int, header: str = "") -> str:
    current = _currently_playing.get(channel_id)
    queue = _song_queues.get(channel_id, [])
    parts = [header] if header else []
    parts.extend(["", "🎵 **Danh sách phát nhạc:**", ""])
    if current:
        parts.append(f"▶️ **Đang phát:** {current['title']}")
    if queue:
        parts.extend(["", "**📜 Hàng đợi:**", format_queue(channel_id)])
    elif current:
        parts.extend(["", "*(Không có bài nào trong hàng đợi)*"])
    return "\n".join(parts)


async def _update_queue_message(channel_id: int, header: str = "") -> None:
    text_channel = _queue_text_channels.get(channel_id)
    if not text_channel:
        return
    content = _build_queue_text(channel_id, header)
    existing = _queue_messages.get(channel_id)
    if existing:
        try:
            await existing.edit(content=content)
            return
        except Exception as error:
            log.warning("[queue] Không thể edit tin nhắn cũ: %s", error)
    try:
        _queue_messages[channel_id] = await text_channel.send(content)
    except Exception as error:
        log.error("[queue] Không thể gửi tin nhắn: %s", error, exc_info=True)


def _voice_client(channel_id: int):
    return next(
        (client for client in bot.voice_clients if client.channel.id == channel_id),
        None,
    )


def _clear_channel(channel_id: int) -> None:
    _song_queues.pop(channel_id, None)
    _currently_playing.pop(channel_id, None)
    _queue_text_channels.pop(channel_id, None)
    _queue_messages.pop(channel_id, None)


def _play_after(channel_id: int, error) -> None:
    if error:
        log.error("[play] Lỗi khi phát: %s", error)
    if channel_id in _skip_requests:
        _skip_requests.discard(channel_id)
        return
    bot.loop.call_soon_threadsafe(
        lambda: asyncio.create_task(_play_next_track(channel_id))
    )


async def _play_next_track(channel_id: int) -> None:
    voice_client = _voice_client(channel_id)
    if not voice_client or not voice_client.is_connected():
        _clear_channel(channel_id)
        return
    queue = _song_queues.get(channel_id, [])
    if not queue:
        _currently_playing.pop(channel_id, None)
        return
    track = queue.pop(0)
    if not queue:
        _song_queues.pop(channel_id, None)
    try:
        source = discord.FFmpegPCMAudio(
            track["audio_url"], **music_service.ffmpeg_options
        )
        voice_client.play(source, after=lambda error: _play_after(channel_id, error))
        _currently_playing[channel_id] = track
        await _update_queue_message(
            channel_id, header=f"▶️ Đang phát tiếp: **{track['title']}**"
        )
    except Exception as error:
        log.error("[play] Lỗi khi phát bài tiếp: %s", error, exc_info=True)
        if text_channel := _queue_text_channels.get(channel_id):
            await text_channel.send(f"Có lỗi khi phát bài tiếp theo: {error}")


def _connected_members(voice_client) -> list:
    channel = voice_client.channel
    if isinstance(channel, (discord.GroupChannel, discord.DMChannel)):
        members = []
        if channel.me and channel.me.voice and channel.me.voice.channel == channel:
            members.append(channel.me)
        recipients = (
            channel.recipients
            if isinstance(channel, discord.GroupChannel)
            else [channel.recipient]
        )
        members.extend(
            user
            for user in recipients
            if user and user.voice and user.voice.channel == channel
        )
        return members
    return getattr(channel, "members", [])


async def check_alone_voice_clients() -> None:
    """Leave voice after the account has been alone for five seconds."""
    while not bot.is_closed():
        try:
            for voice_client in list(bot.voice_clients):
                channel_id = voice_client.channel.id
                if not voice_client.is_connected():
                    _alone_since.pop(channel_id, None)
                    continue
                active = [
                    member
                    for member in _connected_members(voice_client)
                    if not member.bot and member.id != bot.user.id
                ]
                if active:
                    _alone_since.pop(channel_id, None)
                    continue
                alone_since = _alone_since.setdefault(channel_id, time.monotonic())
                if time.monotonic() - alone_since >= 5:
                    await voice_client.disconnect()
                    _alone_since.pop(channel_id, None)
                    _clear_channel(channel_id)
        except Exception as error:
            log.error("Lỗi kiểm tra voice: %s", error, exc_info=True)
        await asyncio.sleep(1)


@bot.command(name="join")
async def join(ctx):
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if voice_client and voice_client.is_connected():
        await ctx.send("Bot đã ở trong cuộc gọi thoại.")
        return
    try:
        if isinstance(ctx.channel, (discord.GroupChannel, discord.DMChannel)):
            await ctx.channel.connect(ring=False)
        else:
            await ctx.channel.connect()
        await ctx.send("Đã kết nối vào cuộc gọi thoại.")
    except Exception as error:
        log.error("[join] Không thể kết nối: %s", error, exc_info=True)
        await ctx.send(f"Không thể tham gia cuộc gọi thoại: {error}")


@bot.command(name="leave", aliases=["stop"])
async def leave(ctx):
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        await ctx.send("Bot không ở trong cuộc gọi thoại nào của kênh này.")
        return
    channel_id = voice_client.channel.id
    if voice_client.is_playing():
        _skip_requests.add(channel_id)
        voice_client.stop()
    await voice_client.disconnect()
    _clear_channel(channel_id)
    await ctx.send("Đã rời cuộc gọi thoại.")


@bot.command(name="play")
async def play(ctx, *, query: str):
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        try:
            if isinstance(ctx.channel, (discord.GroupChannel, discord.DMChannel)):
                voice_client = await ctx.channel.connect(ring=False)
            else:
                voice_client = await ctx.channel.connect()
        except Exception as error:
            await ctx.send(
                f"Không thể kết nối vào cuộc gọi thoại để phát nhạc: {error}"
            )
            return

    search_msg = await ctx.send(f"Đang tìm kiếm bài hát: `{query}`...")
    try:
        info = await music_service.extract_info(query)
        try:
            await search_msg.delete()
        except Exception:
            pass
        audio_url = info.get("url")
        title = info.get("title", "Không rõ tiêu đề")
        if not audio_url:
            await ctx.send("Không thể lấy đường dẫn audio từ video này.")
            return
        channel_id = voice_client.channel.id
        _queue_text_channels[channel_id] = ctx.channel
        track = {"query": query, "title": title, "audio_url": audio_url}
        if voice_client.is_playing():
            _song_queues.setdefault(channel_id, []).append(track)
            await _update_queue_message(
                channel_id, header=f"⏳ Đã thêm vào hàng đợi: **{title}**"
            )
            return
        source = discord.FFmpegPCMAudio(audio_url, **music_service.ffmpeg_options)
        voice_client.play(source, after=lambda error: _play_after(channel_id, error))
        _currently_playing[channel_id] = track
        await _update_queue_message(channel_id, header=f"🎶 Đang phát: **{title}**")
    except Exception as error:
        log.error("[play] Lỗi: %s", error, exc_info=True)
        await ctx.send(f"Có lỗi xảy ra khi phát nhạc: {error}")


@bot.command(name="next", aliases=["skip"])
async def next_track(ctx):
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        await ctx.send(
            "❌ Bot không ở trong cuộc gọi thoại nào. Hãy dùng `.play` trước."
        )
        return
    if not voice_client.is_playing():
        await ctx.send("❌ Không có bài hát nào đang phát. Hãy dùng `.play` trước.")
        return
    if not _song_queues.get(voice_client.channel.id):
        await ctx.send("❌ Không có bài kế tiếp trong hàng đợi.")
        return
    voice_client.stop()


@bot.command(name="queue")
async def show_queue(ctx):
    voice_client = discord.utils.get(bot.voice_clients, channel=ctx.channel)
    if not voice_client or not voice_client.is_connected():
        await ctx.send("❌ Bot không ở trong cuộc gọi thoại nào.")
        return
    channel_id = voice_client.channel.id
    if not _currently_playing.get(channel_id) and not _song_queues.get(channel_id):
        await ctx.send("Không có bài hát nào đang phát hoặc trong hàng đợi.")
        return
    _queue_messages[channel_id] = await ctx.send(_build_queue_text(channel_id))
