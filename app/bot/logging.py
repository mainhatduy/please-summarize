"""Logging configuration for the Discord bot."""

import json
import logging
import queue
import ssl
import threading
import urllib.request

from app.core.config import Config

_LOG_QUEUE = queue.Queue()


class DiscordWebhookHandler(logging.Handler):
    def emit(self, record):
        try:
            _LOG_QUEUE.put(self.format(record))
        except Exception:
            self.handleError(record)


def _webhook_worker() -> None:
    while True:
        message = _LOG_QUEUE.get()
        try:
            request = urllib.request.Request(
                Config.DISCORD_WEBHOOK_URL,
                data=json.dumps({"content": message[:1900]}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                },
                method="POST",
            )
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            urllib.request.urlopen(request, timeout=5, context=context)
        except Exception:
            pass
        finally:
            _LOG_QUEUE.task_done()


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("bot")
    if Config.DISCORD_WEBHOOK_URL and not any(
        isinstance(handler, DiscordWebhookHandler) for handler in logger.handlers
    ):
        threading.Thread(target=_webhook_worker, daemon=True).start()
        handler = DiscordWebhookHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)

    for library in (
        "discord",
        "discord.http",
        "discord.gateway",
        "discord.client",
        "httpx",
        "httpcore",
    ):
        library_logger = logging.getLogger(library)
        library_logger.setLevel(logging.INFO)
        library_logger.propagate = False

    return logger


log = configure_logging()
