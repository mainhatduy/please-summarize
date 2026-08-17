"""Automatic TikTok link handling."""

import asyncio
import random

import discord

from app.bot.helpers import SEND_JITTER_MAX, SEND_JITTER_MIN
from app.bot.logging import log
from app.bot.runtime import bot, tiktok_service


async def handle_tiktok(message, url: str) -> None:
    log.info("[tiktok] Detected URL: %s | channel_id=%s", url, message.channel.id)
    await message.add_reaction("⏳")
    result = None
    try:
        result = await tiktok_service.download(url)
        if result.content_type == "video":
            if result.file_size_mb > 10:
                await message.channel.send(result.direct_url)
            else:
                await message.channel.send(file=discord.File(result.file_path))
        elif result.content_type == "slideshow":
            batch_size = 10
            for index in range(0, len(result.image_paths), batch_size):
                paths = result.image_paths[index : index + batch_size]
                await message.channel.send(files=[discord.File(path) for path in paths])
                if index + batch_size < len(result.image_paths):
                    await asyncio.sleep(random.uniform(SEND_JITTER_MIN, SEND_JITTER_MAX))

        await message.remove_reaction("⏳", bot.user)
        await message.add_reaction("✅")
        log.info("[tiktok] Hoàn thành gửi %s", result.content_type)
    except Exception as error:
        log.error("[tiktok] Error: %s", error, exc_info=True)
        try:
            await message.remove_reaction("⏳", bot.user)
            await message.add_reaction("❌")
        except Exception:
            pass
    finally:
        if result is not None:
            paths = ([result.file_path] if result.file_path else []) + list(
                result.image_paths or []
            )
            tiktok_service.cleanup(*paths)
