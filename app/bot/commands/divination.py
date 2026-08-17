"""Luck, dice, divination-stick, and Tarot commands."""

import asyncio

from app.bot.helpers import apply_channel_rate_limit, send_long
from app.bot.logging import log
from app.bot.runtime import (
    bot,
    fortune_service,
    taixiu_service,
    tarot_service,
    xinkeo_service,
)


@bot.command(name="get_luck", aliases=["luck", "vanmay"])
async def get_luck(ctx):
    await apply_channel_rate_limit(ctx.channel.id)
    user_messages = []
    async for message in ctx.channel.history(limit=500):
        if message.id == ctx.message.id or message.author.id != ctx.author.id:
            continue
        if not message.content.strip() or message.content.strip().startswith(bot.command_prefix):
            continue
        user_messages.append(message.content.strip())
        if len(user_messages) >= 77:
            break

    user_messages.reverse()
    result = fortune_service.roll(ctx.author.id, messages=user_messages)
    if result.already_rolled:
        await ctx.send(
            f"🎲 **{ctx.author.name}**, bạn đã roll vận may hôm nay rồi!\n"
            "Hãy quay lại vào **00:00 ngày mai** để thử lại nhé. 🌙"
        )
        return

    tier = result.tier
    await ctx.send(
        f"`{ctx.author.name}`\n# **{tier.label}**\n## **{result.animal}**\n\n{result.fortune_msg}\n"
    )
    log.info("[get_luck] %s rolled Tier %s", ctx.author, tier.name)


@bot.command(name="taixiu", aliases=["tx"])
async def taixiu(ctx):
    result = taixiu_service.roll()
    await ctx.send(taixiu_service.get_result_text(ctx.author.name, result))
    log.info("[taixiu] %s -> %s", result["rolls"], result["result_type"])


@bot.command(name="xinkeo", aliases=["xk"])
async def xinkeo(ctx, *, wish: str = ""):
    if not wish.strip():
        await ctx.send(
            "🙏 Vui lòng nhập lời khấn nguyện. Ví dụ: `.xinkeo Con xin sức khỏe bình an.`"
        )
        return

    roll_result = xinkeo_service.roll()
    wait_msg = await ctx.send(
        f"⚪ ⚫ **{ctx.author.name}** đang thành tâm dâng hương khấn nguyện:\n"
        f'*"{wish}"*\n\n*Đang gieo quẻ xin keo...*'
    )
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(None, xinkeo_service.generate_luan_giai, wish, roll_result)
    result_type = roll_result["result"]
    await wait_msg.edit(
        content=(
            "🙏 **Quẻ Xin Keo**\n"
            f"**Người cầu:** {ctx.author.mention}\n"
            f'**Tâm nguyện:** *"{wish}"*\n'
            f"**Quẻ gieo:** {roll_result['icon1']} {roll_result['icon2']} ({result_type})\n\n"
            f"**Lời luận giải:**\n{reading}"
        )
    )
    log.info("[xinkeo] %s: %s", ctx.author.name, result_type)


@bot.command(name="tarot")
async def tarot(ctx, *, question: str = ""):
    if not question.strip():
        await ctx.send(
            "🔮 Vui lòng nhập câu hỏi của bạn. Ví dụ: `.tarot Hôm nay tôi có may mắn về tình duyên không?`"
        )
        return

    wait_msg = await ctx.send(
        f'🔮 **{ctx.author.name}** đang hỏi: *"{question}"*\n'
        "*Đang xáo bài và kết nối với các tinh linh...*"
    )
    draw_result = tarot_service.draw_cards()

    def format_card(card):
        return f"**{card.name}** ({'Ngược' if card.is_reversed else 'Xuôi'})"

    await wait_msg.edit(
        content=(
            f"🔮 **Trải bài của {ctx.author.name}**\n"
            f'**Câu hỏi:** *"{question}"*\n\n'
            f"✨ **Lá bài chính:** {format_card(draw_result['key_card'])}\n"
            "🃏 **3 lá bài phụ:** "
            + ", ".join(format_card(card) for card in draw_result["supporting_cards"])
            + "\n\n*Đang chờ thông điệp từ cõi tâm linh...*"
        )
    )
    loop = asyncio.get_event_loop()
    reading = await loop.run_in_executor(
        None, tarot_service.generate_reading, question, draw_result, ctx.author.name
    )
    final_text = (
        "🔮 **TRẢI BÀI TAROT**\n"
        f"**Người xem:** {ctx.author.mention}\n"
        f'**Câu hỏi:** *"{question}"*\n\n'
        f"✨ **Lá bài chính (Key):** {format_card(draw_result['key_card'])}\n"
        "🃏 **Lá bài phụ (Support):** "
        + ", ".join(format_card(card) for card in draw_result["supporting_cards"])
        + f"\n\n**📜 Lời Luận Giải:**\n{reading}"
    )
    if len(final_text) > 1900:
        await wait_msg.delete()
        await send_long(ctx, final_text)
    else:
        await wait_msg.edit(content=final_text)
