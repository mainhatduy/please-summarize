"""Shared video processing helpers for Discord uploads."""

import asyncio
import json
import logging
import os

DISCORD_TARGET_MB = 9.5


async def _is_h265(file_path: str, *, log: logging.Logger, source: str) -> bool | None:
    """Return whether the first video stream uses H.265/HEVC."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "v:0",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout)
        codec = info.get("streams", [{}])[0].get("codec_name", "")
        log.debug("[%s] Video codec: %s", source, codec)
        return codec in ("hevc", "h265")
    except Exception as error:
        log.warning("[%s] ffprobe check failed: %s", source, error)
        return None


async def _get_duration(file_path: str, *, log: logging.Logger, source: str) -> float:
    """Read the video duration in seconds with ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception as error:
        log.warning("[%s] ffprobe duration failed: %s", source, error)
        return 0


def _derived_path(src: str, suffix: str) -> str:
    stem, _ = os.path.splitext(src)
    return f"{stem}_{suffix}.mp4"


async def _convert_codec(src: str, *, log: logging.Logger, source: str) -> str:
    """Convert H.265 to H.264 while preserving the original resolution."""
    dst = _derived_path(src, "h264")
    log.info("[%s] Convert codec H.265 → H.264: %s", source, os.path.basename(src))

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            dst,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        log.warning("[%s] ffmpeg unavailable, keeping original video: %s", source, error)
        return src
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.error(
            "[%s] Convert codec failed: %s",
            source,
            stderr.decode(errors="replace")[-500:],
        )
        return src

    try:
        os.remove(src)
        os.rename(dst, src)
    except OSError:
        return dst

    log.info(
        "[%s] Convert codec xong: %.1f MB",
        source,
        os.path.getsize(src) / (1024 * 1024),
    )
    return src


async def _compress_to_fit(src: str, *, log: logging.Logger, source: str) -> str:
    """Scale to 720p and target a bitrate below Discord's upload limit."""
    duration = await _get_duration(src, log=log, source=source)
    if duration <= 0:
        log.warning("[%s] Không lấy được duration, bỏ qua compress", source)
        return src

    target_bits = DISCORD_TARGET_MB * 1024 * 1024 * 8
    audio_bitrate = 128_000
    video_bitrate = max(int(target_bits / duration - audio_bitrate), 100_000)
    src_size = os.path.getsize(src) / (1024 * 1024)
    log.info(
        "[%s] Compress %.1fMB → ≤%.1fMB (720p, %skbps, %.0fs)",
        source,
        src_size,
        DISCORD_TARGET_MB,
        video_bitrate // 1000,
        duration,
    )

    dst = _derived_path(src, "compressed")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-vf",
            "scale=-2:720",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            str(video_bitrate),
            "-maxrate",
            str(video_bitrate),
            "-bufsize",
            str(video_bitrate * 2),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            dst,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        log.warning("[%s] ffmpeg unavailable, keeping original video: %s", source, error)
        return src
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.error(
            "[%s] Compress failed: %s",
            source,
            stderr.decode(errors="replace")[-500:],
        )
        return src

    try:
        os.remove(src)
        os.rename(dst, src)
    except OSError:
        return dst

    log.info(
        "[%s] Compress xong: %.1f MB",
        source,
        os.path.getsize(src) / (1024 * 1024),
    )
    return src


async def ensure_discord_ready(file_path: str, *, log: logging.Logger, source: str) -> str:
    """Ensure a video is H.264 and targets a size below 10 MB."""
    is_h265 = await _is_h265(file_path, log=log, source=source)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    if is_h265 is None and file_size_mb <= DISCORD_TARGET_MB:
        return file_path

    if not is_h265 and file_size_mb <= DISCORD_TARGET_MB:
        log.debug("[%s] Video OK (H.264, %.1fMB) → gửi trực tiếp", source, file_size_mb)
        return file_path

    if is_h265 and file_size_mb <= DISCORD_TARGET_MB:
        file_path = await _convert_codec(file_path, log=log, source=source)
        new_size = os.path.getsize(file_path) / (1024 * 1024)
        if new_size <= DISCORD_TARGET_MB:
            return file_path
        log.info("[%s] Convert xong %.1fMB > limit → compress tiếp", source, new_size)

    return await _compress_to_fit(file_path, log=log, source=source)
