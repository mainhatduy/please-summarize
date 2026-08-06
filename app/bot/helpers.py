"""Reusable command throttling and Discord message helpers."""

import asyncio
import random
import time

from app.bot.logging import log

COOLDOWN_SECONDS = 60
SEND_JITTER_MIN = 0.3
SEND_JITTER_MAX = 0.8
CHANNEL_RATE_LIMIT_SECONDS = 5

_cooldown_tracker: dict[int, float] = {}
_channel_last_fetch: dict[int, float] = {}


async def send_long(ctx, text: str, chunk_size: int = 1900) -> None:
    """Send long text in Discord-sized chunks with a small random delay."""
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    for index, chunk in enumerate(chunks):
        await ctx.send(chunk)
        if index < len(chunks) - 1:
            delay = random.uniform(SEND_JITTER_MIN, SEND_JITTER_MAX)
            log.debug("[send_long] Chờ %.2fs trước chunk tiếp theo...", delay)
            await asyncio.sleep(delay)


def check_cooldown(user_id: int) -> float | None:
    """Return remaining cooldown seconds, or ``None`` when the command may run."""
    now = time.monotonic()
    last_used = _cooldown_tracker.get(user_id)
    if last_used is not None:
        elapsed = now - last_used
        if elapsed < COOLDOWN_SECONDS:
            return COOLDOWN_SECONDS - elapsed
    _cooldown_tracker[user_id] = now
    return None


async def apply_channel_rate_limit(channel_id: int) -> None:
    """Space history fetches per channel to avoid Discord API bursts."""
    now = time.monotonic()
    last_fetch = _channel_last_fetch.get(channel_id)
    if last_fetch is not None:
        elapsed = now - last_fetch
        if elapsed < CHANNEL_RATE_LIMIT_SECONDS:
            wait = CHANNEL_RATE_LIMIT_SECONDS - elapsed + random.uniform(0.2, 1.0)
            log.info("[rate_limit] Channel %s: chờ %.1fs...", channel_id, wait)
            await asyncio.sleep(wait)
    _channel_last_fetch[channel_id] = time.monotonic()
