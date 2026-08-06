"""Text summarization and conversation-question commands."""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from app.bot.helpers import apply_channel_rate_limit, check_cooldown, send_long
from app.bot.logging import log
from app.bot.runtime import bot, summarize_service


def _target_from_context(ctx, target_str):
    if ctx.message.mentions:
        return ctx.message.mentions[0].id, None
    if target_str:
        name = target_str[1:] if target_str.startswith("@") else target_str
        return None, name.lower()
    return None, None


def _matches_target(message, target_id, target_name) -> bool:
    if target_id and message.author.id != target_id:
        return False
    if target_name:
        author_name = message.author.name.lower()
        display_name = getattr(message.author, "display_name", "").lower()
        return target_name in author_name or target_name in display_name
    return True


def _is_summarizable(message) -> bool:
    return (
        message.author.id != bot.user.id
        and not message.author.bot
        and bool(message.content.strip())
        and not message.content.strip().startswith(bot.command_prefix)
    )


@bot.command(name="tomtat", aliases=["sum_msgs"])
async def tomtat(ctx, *args):
    n = 50
    target_str = None
    if args:
        try:
            n = int(args[0])
            target_str = " ".join(args[1:]) if len(args) > 1 else None
        except ValueError:
            target_str = " ".join(args)

    target_id, target_name = _target_from_context(ctx, target_str)
    log.info("[tomtat] n=%s | target=%s | channel=%s", n, target_str, ctx.channel.id)
    remaining = check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return
    if n <= 0 or n > 500:
        await ctx.send("Vui lòng nhập n từ 1 đến 500.")
        return

    await apply_channel_rate_limit(ctx.channel.id)
    messages = []
    skipped = skipped_bots = 0
    fetch_limit = 2000 if target_str else n + 1
    async for message in ctx.channel.history(limit=fetch_limit):
        if message.id == ctx.message.id or not _matches_target(
            message, target_id, target_name
        ):
            continue
        if message.author.bot or message.author.id == bot.user.id:
            skipped_bots += 1
            continue
        if not message.content.strip() or message.content.strip().startswith(
            bot.command_prefix
        ):
            skipped += 1
            continue
        messages.append(f"{message.author.name}: {message.content}")
        if len(messages) >= n:
            break

    messages.reverse()
    target_info = f" của **{target_str}**" if target_str else ""
    await ctx.send(
        f"📊 Thu thập được **{len(messages)}/{n}** tin nhắn text{target_info}"
        + (f" (bỏ qua {skipped} ảnh/file)" if skipped else "")
        + (f" (bỏ qua {skipped_bots} tin nhắn bot)" if skipped_bots else "")
        + "\nĐang gọi Gemini..."
    )
    summary = summarize_service.summarize(messages)
    await send_long(ctx, f"**Tóm tắt:**\n{summary}")
    log.info("[tomtat] Hoàn thành.")


@bot.command(name="tomtat_time", aliases=["sum_time"])
async def tomtat_time(ctx, *args):
    hours = 1.0
    target_str = None
    if args:
        try:
            hours = float(args[0])
            target_str = " ".join(args[1:]) if len(args) > 1 else None
        except ValueError:
            target_str = " ".join(args)

    target_id, target_name = _target_from_context(ctx, target_str)
    remaining = check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return
    if hours <= 0 or hours > 12:
        await ctx.send("Vui lòng nhập số giờ hợp lệ (từ 0.1 đến 12).")
        return

    after_time = datetime.now(UTC) - timedelta(hours=hours)
    await apply_channel_rate_limit(ctx.channel.id)
    messages = []
    skipped = skipped_bots = 0
    async for message in ctx.channel.history(limit=None):
        if message.id == ctx.message.id:
            continue
        if message.created_at < after_time:
            break
        if not _matches_target(message, target_id, target_name):
            continue
        if message.author.bot or message.author.id == bot.user.id:
            skipped_bots += 1
            continue
        if not message.content.strip() or message.content.strip().startswith(
            bot.command_prefix
        ):
            skipped += 1
            continue
        messages.append(f"{message.author.name}: {message.content}")
        if len(messages) >= 500:
            break

    if not messages:
        await ctx.send("Không có đoạn hội thoại nào trong thời gian này.")
        return
    messages.reverse()
    target_info = f" của **{target_str}**" if target_str else ""
    await ctx.send(
        f"📊 Thu thập được **{len(messages)}** tin nhắn text trong {hours} giờ qua{target_info}"
        + (f" (bỏ qua {skipped} ảnh/file)" if skipped else "")
        + (f" (bỏ qua {skipped_bots} tin nhắn bot)" if skipped_bots else "")
        + "\nĐang gọi Gemini..."
    )
    summary = summarize_service.summarize(messages)
    await send_long(ctx, f"**Tóm tắt:**\n{summary}")
    log.info("[tomtat_time] Hoàn thành.")


@bot.command(name="cau_hoi")
async def cau_hoi(ctx, *args):
    remaining = check_cooldown(ctx.author.id)
    if remaining is not None:
        await ctx.send(f"⏳ Bạn cần chờ **{remaining:.0f} giây** nữa để dùng lệnh này.")
        return

    after_time = datetime.now(UTC) - timedelta(hours=4)
    await apply_channel_rate_limit(ctx.channel.id)
    messages = []
    active_users = {}
    async for message in ctx.channel.history(limit=None):
        if message.id == ctx.message.id:
            continue
        if message.created_at < after_time:
            break
        if not _is_summarizable(message):
            continue
        messages.append(f"{message.author.name}: {message.content}")
        active_users[message.author.id] = message.author.name
        if len(messages) >= 500:
            break

    if not messages or not active_users:
        await ctx.send("Không có ai nói chuyện trong 4 giờ qua để đặt câu hỏi cả.")
        return
    target_id = random.choice(list(active_users))
    target_name = active_users[target_id]
    messages.reverse()
    wait_msg = await ctx.send(
        f"Đang ngẫm nghĩ một câu hỏi thật sâu sắc dành cho **{target_name}**..."
    )
    loop = asyncio.get_event_loop()
    question = await loop.run_in_executor(
        None, summarize_service.generate_drama_question, messages, target_name
    )
    await wait_msg.delete()
    await send_long(ctx, f"<@{target_id}> {question}")
