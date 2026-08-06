"""I Ching commands."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

from app.bot.helpers import apply_channel_rate_limit, send_long
from app.bot.logging import log
from app.bot.runtime import bot, kinhdich_service


async def _show_reading(ctx, wait_msg, final_text: str) -> None:
    if len(final_text) > 1900:
        await wait_msg.delete()
        await send_long(ctx, final_text)
    else:
        await wait_msg.edit(content=final_text)


@bot.command(name="rutque", aliases=["rq", "kinhdich"])
async def rutque(ctx, *, question: str = ""):
    if not question.strip():
        await ctx.send(
            "☰ Vui lòng nhập câu hỏi của bạn. Ví dụ: `.rutque Hôm nay tôi có nên đầu tư không?`"
        )
        return
    wait_msg = await ctx.send(
        f'☰ **{ctx.author.name}** đang hỏi: *"{question}"*\n'
        "*Đang thành tâm rút quẻ Kinh Dịch...*"
    )
    hexagram = kinhdich_service.draw_hexagram(question)
    hex_text = kinhdich_service.format_hexagram_text(hexagram)
    await wait_msg.edit(
        content=(
            f"☰ **Quẻ Kinh Dịch của {ctx.author.name}**\n"
            f'**Câu hỏi:** *"{question}"*\n\n{hex_text}\n'
            "*Đang luận giải quẻ dịch...*"
        )
    )
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None, kinhdich_service.generate_reading, question, hexagram, ctx.author.name
    )
    await _show_reading(
        ctx,
        wait_msg,
        "☰ **QUẺ KINH DỊCH**\n"
        f"**Người hỏi:** {ctx.author.mention}\n"
        f'**Câu hỏi:** *"{question}"*\n\n{hex_text}\n'
        f"**📜 Lời Luận Giải:**\n{reading}",
    )


@bot.command(name="luachon", aliases=["lc", "chon"])
async def luachon(ctx, *, question_and_choices: str = ""):
    if not question_and_choices.strip():
        await ctx.send(
            "☰ Vui lòng nhập câu hỏi và các lựa chọn. Ví dụ: `.luachon Trưa nay ăn gì? Phở hay Cơm tấm?`"
        )
        return
    wait_msg = await ctx.send(
        f'☰ **{ctx.author.name}** đang phân vân: *"{question_and_choices}"*\n'
        "*Đang rút quẻ Kinh Dịch để tìm ra lựa chọn tốt nhất...*"
    )
    hexagram = kinhdich_service.draw_hexagram(question_and_choices)
    hex_text = kinhdich_service.format_hexagram_text(hexagram)
    await wait_msg.edit(
        content=(
            f"☰ **Quẻ Kinh Dịch của {ctx.author.name}**\n"
            f'**Phân vân:** *"{question_and_choices}"*\n\n{hex_text}\n'
            "*Đang xin lời khuyên từ cõi tâm linh để đưa ra quyết định...*"
        )
    )
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None,
        kinhdich_service.generate_choice_reading,
        question_and_choices,
        hexagram,
        ctx.author.name,
    )
    await _show_reading(
        ctx,
        wait_msg,
        "☰ **QUYẾT ĐỊNH TỪ KINH DỊCH**\n"
        f"**Người hỏi:** {ctx.author.mention}\n"
        f'**Phân vân:** *"{question_and_choices}"*\n\n{hex_text}\n{reading}',
    )


@bot.command(name="thongke_kinhdich", aliases=["tk_kd"])
async def thongke_kinhdich(ctx, *, target_str: str = ""):
    target_id = None
    target_name = None
    if ctx.message.mentions:
        target_id = ctx.message.mentions[0].id
        target_name = ctx.message.mentions[0].name.lower()
    elif target_str:
        target_name = (
            target_str[1:].lower() if target_str.startswith("@") else target_str.lower()
        )
    else:
        await ctx.send(
            "Vui lòng nhập người cần thống kê. Ví dụ: `.thongke_kinhdich @huuannnn`"
        )
        return

    vn_timezone = timezone(timedelta(hours=7))
    now_vn = datetime.now(UTC).astimezone(vn_timezone)
    start_of_day = now_vn.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
        UTC
    )
    await apply_channel_rate_limit(ctx.channel.id)
    display_name = target_str or (f"@{target_name}" if target_name else "bạn")
    wait_msg = await ctx.send(
        f"Đang thu thập dữ liệu gieo quẻ hôm nay của {display_name}..."
    )
    history_texts = []
    result_markers = (
        "QUẺ KINH DỊCH",
        "QUYẾT ĐỊNH TỪ KINH DỊCH",
        "Quẻ Xin Keo",
        "Trải bài của",
        "TRẢI BÀI TAROT",
        "Tier",
        "Quẻ gieo:",
    )
    async for message in ctx.channel.history(limit=None):
        if message.created_at < start_of_day:
            break
        if message.author.id != bot.user.id:
            continue
        mentioned_id = f"<@{target_id}>" if target_id else ""
        refers_to_target = (target_name and target_name in message.content.lower()) or (
            mentioned_id and mentioned_id in message.content
        )
        if refers_to_target and any(
            marker in message.content for marker in result_markers
        ):
            history_texts.append(message.content)

    if not history_texts:
        await wait_msg.edit(
            content=f"Không tìm thấy lịch sử gieo quẻ nào của {display_name} trong ngày hôm nay."
        )
        return
    history_texts.reverse()
    await wait_msg.edit(
        content=(
            f"Đã tìm thấy {len(history_texts)} lần gieo quẻ/vận may của "
            f"{display_name} hôm nay. Đang phân tích và luận giải..."
        )
    )
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None, kinhdich_service.generate_thongke, display_name, history_texts
    )
    await _show_reading(
        ctx,
        wait_msg,
        "📊 **THỐNG KÊ KINH DỊCH TRONG NGÀY**\n"
        f"**Người xem:** {display_name}\n\n{reading}",
    )
    log.info("[thongke_kinhdich] Hoàn thành cho %s", target_name)
