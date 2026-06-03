"""TikTok download service – dùng TikWM API (chính) + yt-dlp (fallback)."""

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Literal

import httpx

log = logging.getLogger("bot.tiktok")

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TikTokResult:
    content_type: Literal["video", "slideshow"]
    # Video fields
    file_path: str | None = None
    file_size_mb: float = 0.0
    direct_url: str | None = None
    # Slideshow fields
    image_paths: list[str] = field(default_factory=list)


# ── Service ───────────────────────────────────────────────────────────────────

class TikTokService:
    """Xử lý download video/ảnh từ link TikTok qua TikWM API."""

    # Regex bắt các dạng URL TikTok phổ biến
    TIKTOK_URL_PATTERN = re.compile(
        r'https?://(?:(?:www|vm|vt)\.)?tiktok\.com/\S+',
        re.IGNORECASE,
    )

    TIKWM_API_URL = "https://www.tikwm.com/api/"

    _BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self):
        self._download_dir = tempfile.mkdtemp(prefix="tiktok_dl_")
        log.info(f"[tiktok] Download dir: {self._download_dir}")

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_tiktok_url(self, text: str) -> str | None:
        """Trả về URL TikTok đầu tiên tìm thấy trong text, hoặc None."""
        match = self.TIKTOK_URL_PATTERN.search(text)
        return match.group(0) if match else None

    async def download(self, url: str) -> TikTokResult:
        """Download video hoặc ảnh slideshow từ TikTok URL qua TikWM API."""
        log.info(f"[tiktok] Fetching TikWM API for: {url}")

        try:
            data = await self._fetch_tikwm(url)
        except Exception as e:
            log.error(f"[tiktok] TikWM API failed: {e}", exc_info=True)
            # Fallback: thử yt-dlp
            log.info("[tiktok] Falling back to yt-dlp...")
            return await self._download_with_ytdlp(url)

        if data is None:
            log.warning("[tiktok] TikWM returned no data, falling back to yt-dlp...")
            return await self._download_with_ytdlp(url)

        # Kiểm tra slideshow hay video
        images = data.get("images")
        if images and isinstance(images, list) and len(images) > 0:
            return await self._download_slideshow(images)
        else:
            return await self._download_video(data)

    def cleanup(self, *paths: str):
        """Xóa các file tạm đã cho."""
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    log.debug(f"[tiktok] Cleaned up: {p}")
                except OSError as e:
                    log.warning(f"[tiktok] Failed to cleanup {p}: {e}")

    # ── TikWM API ─────────────────────────────────────────────────────────────

    async def _fetch_tikwm(self, url: str) -> dict | None:
        """Gọi TikWM API, trả về data dict hoặc None nếu lỗi."""
        params = {
            "url": url,
            "count": 12,
            "cursor": 0,
            "web": 1,
            "hd": 1,
        }

        async with httpx.AsyncClient(
            headers=self._BROWSER_HEADERS,
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            resp = await client.get(self.TIKWM_API_URL, params=params)
            resp.raise_for_status()
            result = resp.json()

        if result.get("code") != 0:
            log.warning(f"[tiktok] TikWM API error: {result.get('msg', 'Unknown')}")
            return None

        return result.get("data")

    # ── Video download ────────────────────────────────────────────────────────

    async def _download_video(self, data: dict) -> TikTokResult:
        """Tải video từ URL trả về bởi TikWM API."""
        # TikWM trả về URL không watermark trong field "play"
        # và URL HD trong field "hdplay"
        video_url = data.get("hdplay") or data.get("play")
        if not video_url:
            raise ValueError("TikWM API did not return a video URL")

        # Thêm domain TikWM nếu URL là relative
        if video_url.startswith("/"):
            video_url = f"https://www.tikwm.com{video_url}"

        video_id = data.get("id", "unknown")
        file_path = os.path.join(self._download_dir, f"{video_id}.mp4")

        log.info(f"[tiktok] Downloading video: {video_url[:80]}...")

        async with httpx.AsyncClient(
            headers=self._BROWSER_HEADERS,
            follow_redirects=True,
            timeout=60.0,
        ) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        log.info(f"[tiktok] Video downloaded: {file_path} ({file_size_mb:.1f} MB)")

        return TikTokResult(
            content_type="video",
            file_path=file_path,
            file_size_mb=file_size_mb,
            direct_url=video_url,
        )

    # ── Slideshow download ────────────────────────────────────────────────────

    async def _download_slideshow(self, image_urls: list[str]) -> TikTokResult:
        """Tải từng ảnh slideshow từ URLs trả về bởi TikWM API."""
        log.info(f"[tiktok] Downloading {len(image_urls)} slideshow images...")

        paths: list[str] = []

        async with httpx.AsyncClient(
            headers=self._BROWSER_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for idx, img_url in enumerate(image_urls):
                try:
                    # Thêm domain nếu relative
                    if img_url.startswith("/"):
                        img_url = f"https://www.tikwm.com{img_url}"

                    resp = await client.get(img_url)
                    resp.raise_for_status()

                    # Xác định extension từ content-type
                    content_type = resp.headers.get("content-type", "")
                    ext = ".jpg"
                    if "png" in content_type:
                        ext = ".png"
                    elif "webp" in content_type:
                        ext = ".webp"

                    file_path = os.path.join(self._download_dir, f"slide_{idx:03d}{ext}")
                    with open(file_path, "wb") as f:
                        f.write(resp.content)

                    paths.append(file_path)
                    log.debug(f"[tiktok] Downloaded image {idx + 1}/{len(image_urls)}")

                except Exception as e:
                    log.warning(f"[tiktok] Failed to download image {idx + 1}: {e}")

        if not paths:
            raise ValueError("Failed to download any slideshow images")

        log.info(f"[tiktok] Downloaded {len(paths)}/{len(image_urls)} images")
        return TikTokResult(
            content_type="slideshow",
            image_paths=paths,
        )

    # ── yt-dlp fallback ──────────────────────────────────────────────────────

    async def _download_with_ytdlp(self, url: str) -> TikTokResult:
        """Fallback: tải video bằng yt-dlp khi TikWM API thất bại."""
        import yt_dlp

        log.info(f"[tiktok] yt-dlp fallback download: {url}")

        def _extract_and_download():
            ydl_opts = {
                "format": "best",
                "outtmpl": os.path.join(self._download_dir, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "source_address": "0.0.0.0",
                "extractor_args": {"tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if "entries" in info:
                    info = info["entries"][0]
                file_path = ydl.prepare_filename(info)
                return info, file_path

        info, file_path = await asyncio.to_thread(_extract_and_download)

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024) if os.path.exists(file_path) else 0
        direct_url = info.get("webpage_url") or info.get("url") or url

        log.info(f"[tiktok] yt-dlp video downloaded: {file_path} ({file_size_mb:.1f} MB)")

        return TikTokResult(
            content_type="video",
            file_path=file_path,
            file_size_mb=file_size_mb,
            direct_url=direct_url,
        )
