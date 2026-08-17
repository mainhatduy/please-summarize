"""Automatic Facebook Reel handling."""

import discord

from app.bot.logging import log
from app.bot.runtime import bot, facebook_service


async def handle_facebook_reel(message, url: str) -> None:
    log.info("[facebook] Detected Reel URL: %s | channel_id=%s", url, message.channel.id)
    await message.add_reaction("⏳")
    result = None
    try:
        result = await facebook_service.download(url)
        if result.file_size_mb > 10:
            await message.channel.send(result.direct_url)
        else:
            await message.channel.send(file=discord.File(result.file_path))

        await message.remove_reaction("⏳", bot.user)
        await message.add_reaction("✅")
        log.info("[facebook] Hoàn thành gửi Reel")
    except Exception as error:
        log.error("[facebook] Error: %s", error, exc_info=True)
        try:
            await message.remove_reaction("⏳", bot.user)
            await message.add_reaction("❌")
        except Exception:
            pass
    finally:
        if result is not None:
            facebook_service.cleanup(result.file_path)
