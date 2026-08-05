"""Compose and start the Discord application."""

# Importing these modules registers commands and events on the shared bot.
from app.bot import commands as _commands  # noqa: F401
from app.bot import events as _events  # noqa: F401
from app.bot.logging import log
from app.bot.runtime import bot
from app.core.config import Config


def _has_valid_configuration() -> bool:
    discord_token = Config.DISCORD_TOKEN.strip()
    return bool(
        discord_token
        and "your_discord" not in discord_token.lower()
        and len(discord_token) >= 20
        and Config.GEMINI_API_KEY
        and "your_gemini" not in Config.GEMINI_API_KEY.lower()
    )


def run() -> None:
    """Validate configuration and start the Discord client."""
    if not _has_valid_configuration():
        log.critical("Vui lòng thiết lập DISCORD_TOKEN và GEMINI_API_KEY hợp lệ!")
        return
    log.info("Đang khởi động bot...")
    bot.run(Config.DISCORD_TOKEN.strip())
