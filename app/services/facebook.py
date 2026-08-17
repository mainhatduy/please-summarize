"""Download public Facebook Reels with yt-dlp."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

import yt_dlp

from app.services.video import ensure_discord_ready

log = logging.getLogger("bot.facebook")


@dataclass
class FacebookResult:
    file_path: str
    file_size_mb: float
    direct_url: str


class FacebookService:
    """Download and prepare public Facebook Reels for Discord."""

    FACEBOOK_REEL_URL_PATTERN = re.compile(
        r"https?://(?:(?:www|m|mbasic)\.)?facebook\.com/"
        r"(?:reel/\d+|share/r/[A-Za-z0-9_-]+)"
        r"(?:/?\?[^\s<>()]*)?/?",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._download_dir = tempfile.mkdtemp(prefix="facebook_dl_")
        log.info("[facebook] Download dir: %s", self._download_dir)

    def detect_facebook_reel_url(self, text: str) -> str | None:
        """Return the first supported Facebook Reel URL found in text."""
        match = self.FACEBOOK_REEL_URL_PATTERN.search(text)
        if match is None:
            return None
        return match.group(0).rstrip(".,;:!?)]}>\"'")

    async def download(self, url: str) -> FacebookResult:
        """Download a public Reel without authentication cookies."""
        request_dir = tempfile.mkdtemp(prefix="reel_", dir=self._download_dir)
        log.info("[facebook] yt-dlp download: %s", url)

        def _extract_and_download() -> tuple[dict, str]:
            options = {
                "format": "best[ext=mp4]/best",
                "outtmpl": os.path.join(request_dir, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "source_address": "0.0.0.0",
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if "entries" in info:
                    entries = info.get("entries") or []
                    if not entries:
                        raise ValueError("Facebook Reel did not contain a video")
                    info = entries[0]

                requested_downloads = info.get("requested_downloads") or []
                file_path = next(
                    (item.get("filepath") for item in requested_downloads if item.get("filepath")),
                    None,
                )
                file_path = file_path or info.get("filepath") or info.get("_filename")
                return info, file_path or ydl.prepare_filename(info)

        try:
            info, file_path = await asyncio.to_thread(_extract_and_download)
            if not os.path.isfile(file_path):
                raise FileNotFoundError("yt-dlp did not create the Facebook Reel file")

            file_path = await ensure_discord_ready(file_path, log=log, source="facebook")
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            direct_url = info.get("webpage_url") or info.get("original_url") or url
            log.info(
                "[facebook] Video downloaded: %s (%.1f MB)",
                file_path,
                file_size_mb,
            )
            return FacebookResult(
                file_path=file_path,
                file_size_mb=file_size_mb,
                direct_url=direct_url,
            )
        except Exception:
            shutil.rmtree(request_dir, ignore_errors=True)
            raise

    def cleanup(self, *paths: str) -> None:
        """Remove downloaded files and their now-empty request directories."""
        for path in paths:
            if not path:
                continue
            try:
                if os.path.exists(path):
                    os.remove(path)
                    log.debug("[facebook] Cleaned up: %s", path)
                parent = os.path.dirname(path)
                if os.path.commonpath((self._download_dir, parent)) == self._download_dir:
                    try:
                        os.rmdir(parent)
                    except OSError:
                        pass
            except OSError as error:
                log.warning("[facebook] Failed to cleanup %s: %s", path, error)
