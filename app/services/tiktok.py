"""TikTok download service – video (yt-dlp) & slideshow images (httpx scraper)."""

import asyncio
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Literal

import httpx
import yt_dlp
from bs4 import BeautifulSoup
import json

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
    """Xử lý download video/ảnh từ link TikTok."""

    # Regex bắt các dạng URL TikTok phổ biến
    TIKTOK_URL_PATTERN = re.compile(
        r'https?://(?:(?:www|vm|vt)\.)?tiktok\.com/\S+',
        re.IGNORECASE,
    )

    # Headers giả lập trình duyệt để bypass anti-bot cơ bản
    _BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.tiktok.com/",
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
        """Download video hoặc ảnh slideshow từ TikTok URL."""
        if self._is_slideshow_url(url):
            log.info(f"[tiktok] Detected slideshow URL: {url}")
            result = await self._download_slideshow(url)
            if result is not None:
                return result
            # Fallback: nếu scrape slideshow thất bại → thử yt-dlp (sẽ ra video)
            log.warning("[tiktok] Slideshow scrape failed, falling back to yt-dlp video download")

        return await self._download_video(url)

    def cleanup(self, *paths: str):
        """Xóa các file tạm đã cho."""
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    log.debug(f"[tiktok] Cleaned up: {p}")
                except OSError as e:
                    log.warning(f"[tiktok] Failed to cleanup {p}: {e}")

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _is_slideshow_url(url: str) -> bool:
        """Heuristic: URL chứa /photo/ → slideshow."""
        return "/photo/" in url

    # ── Video download (yt-dlp) ───────────────────────────────────────────────

    async def _download_video(self, url: str) -> TikTokResult:
        """Tải video TikTok bằng yt-dlp, chạy trong thread riêng."""
        log.info(f"[tiktok] Downloading video: {url}")

        def _extract_and_download():
            ydl_opts = {
                "format": "best",
                "outtmpl": os.path.join(self._download_dir, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "source_address": "0.0.0.0",
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

        log.info(f"[tiktok] Video downloaded: {file_path} ({file_size_mb:.1f} MB)")

        return TikTokResult(
            content_type="video",
            file_path=file_path,
            file_size_mb=file_size_mb,
            direct_url=direct_url,
        )

    # ── Slideshow download (httpx + BeautifulSoup) ────────────────────────────

    async def _download_slideshow(self, url: str) -> TikTokResult | None:
        """Scrape ảnh slideshow từ trang TikTok.

        Trả về TikTokResult nếu thành công, None nếu thất bại (để fallback).
        """
        log.info(f"[tiktok] Scraping slideshow images: {url}")

        try:
            image_urls = await self._scrape_image_urls(url)
            if not image_urls:
                log.warning("[tiktok] No image URLs found from scraping")
                return None

            log.info(f"[tiktok] Found {len(image_urls)} images, downloading...")
            image_paths = await self._download_images(image_urls)

            if not image_paths:
                log.warning("[tiktok] Failed to download any images")
                return None

            log.info(f"[tiktok] Downloaded {len(image_paths)} images successfully")
            return TikTokResult(
                content_type="slideshow",
                image_paths=image_paths,
            )

        except Exception as e:
            log.error(f"[tiktok] Slideshow scrape error: {e}", exc_info=True)
            return None

    async def _scrape_image_urls(self, url: str) -> list[str]:
        """Fetch trang TikTok, parse JSON để lấy danh sách URL ảnh."""
        async with httpx.AsyncClient(
            headers=self._BROWSER_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        script_tag = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if not script_tag or not script_tag.string:
            log.warning("[tiktok] __UNIVERSAL_DATA_FOR_REHYDRATION__ script tag not found")
            return []

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            log.error(f"[tiktok] Failed to parse rehydration JSON: {e}")
            return []

        # Trích xuất image URLs theo data path đã biết
        return self._extract_image_urls_from_data(data)

    @staticmethod
    def _extract_image_urls_from_data(data: dict) -> list[str]:
        """Trích xuất URL ảnh từ TikTok rehydration JSON.

        Path: __DEFAULT_SCOPE__ → webapp.video-detail → itemInfo
              → itemStruct → imagePost → images[] → imageURL.urlList[0]
        """
        image_urls: list[str] = []

        try:
            default_scope = data.get("__DEFAULT_SCOPE__", {})
            video_detail = default_scope.get("webapp.video-detail", {})
            item_info = video_detail.get("itemInfo", {})
            item_struct = item_info.get("itemStruct", {})
            image_post = item_struct.get("imagePost", {})
            images = image_post.get("images", [])

            for img in images:
                # Thử nhiều key có thể chứa URL ảnh
                url_list = None
                for key in ("imageURL", "displayImage", "ownerWatermarkImage"):
                    url_obj = img.get(key)
                    if isinstance(url_obj, dict):
                        url_list = url_obj.get("urlList", [])
                        if url_list:
                            break

                if url_list:
                    image_urls.append(url_list[0])
                    
        except (KeyError, TypeError, IndexError) as e:
            log.error(f"[tiktok] Error extracting image URLs from JSON: {e}")

        return image_urls

    async def _download_images(self, image_urls: list[str]) -> list[str]:
        """Download danh sách ảnh, trả về list đường dẫn file đã tải."""
        paths: list[str] = []

        async with httpx.AsyncClient(
            headers=self._BROWSER_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            for idx, img_url in enumerate(image_urls):
                try:
                    resp = await client.get(img_url)
                    resp.raise_for_status()

                    # Xác định extension từ content-type
                    content_type = resp.headers.get("content-type", "")
                    ext = ".jpg"  # mặc định
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
                    # Bỏ qua ảnh lỗi, tiếp tục download các ảnh còn lại

        return paths
