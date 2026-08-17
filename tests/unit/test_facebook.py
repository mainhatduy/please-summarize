import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import app.services.facebook as facebook_module
import app.services.video as video_module
from app.services.facebook import FacebookResult, FacebookService

os.environ.setdefault("GEMINI_API_KEY", "test-api-key")

import app.bot.facebook as facebook_handler  # noqa: E402


def test_detect_facebook_reel_url_supports_reel_and_share_links() -> None:
    service = FacebookService.__new__(FacebookService)

    assert (
        service.detect_facebook_reel_url("xem https://www.facebook.com/reel/2281511879286424 nhé")
        == "https://www.facebook.com/reel/2281511879286424"
    )
    assert (
        service.detect_facebook_reel_url("https://m.facebook.com/share/r/AbC_123-x/?mibextid=abc")
        == "https://m.facebook.com/share/r/AbC_123-x/?mibextid=abc"
    )
    assert (
        service.detect_facebook_reel_url("(https://mbasic.facebook.com/reel/12345/)")
        == "https://mbasic.facebook.com/reel/12345/"
    )


def test_detect_facebook_reel_url_rejects_other_urls() -> None:
    service = FacebookService.__new__(FacebookService)

    assert service.detect_facebook_reel_url("https://www.facebook.com/watch/123") is None
    assert service.detect_facebook_reel_url("https://www.facebook.com/posts/123") is None
    assert service.detect_facebook_reel_url("https://facebook.com.example/reel/123") is None


def test_download_uses_ytdlp_without_cookies(monkeypatch, tmp_path) -> None:
    captured_options = {}
    processed_paths = []

    class FakeYoutubeDL:
        def __init__(self, options):
            captured_options.update(options)
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url, *, download):
            assert download is True
            assert url == "https://www.facebook.com/reel/2281511879286424"
            output_dir = os.path.dirname(self.options["outtmpl"])
            file_path = os.path.join(output_dir, "2281511879286424.mp4")
            with open(file_path, "wb") as video:
                video.write(b"public reel")
            return {
                "id": "2281511879286424",
                "ext": "mp4",
                "webpage_url": url,
                "requested_downloads": [{"filepath": file_path}],
            }

        def prepare_filename(self, info):
            raise AssertionError("requested_downloads filepath should be used")

    async def fake_ensure_discord_ready(file_path, **kwargs):
        processed_paths.append(file_path)
        assert kwargs["source"] == "facebook"
        return file_path

    monkeypatch.setattr(facebook_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(facebook_module, "ensure_discord_ready", fake_ensure_discord_ready)

    service = FacebookService()
    service._download_dir = str(tmp_path)
    url = "https://www.facebook.com/reel/2281511879286424"
    result = asyncio.run(service.download(url))

    assert captured_options["format"] == "best[ext=mp4]/best"
    assert captured_options["noplaylist"] is True
    assert "cookiefile" not in captured_options
    assert "cookiesfrombrowser" not in captured_options
    assert processed_paths == [result.file_path]
    assert result.direct_url == url
    assert result.file_size_mb > 0

    request_dir = os.path.dirname(result.file_path)
    service.cleanup(result.file_path)
    assert not os.path.exists(result.file_path)
    assert not os.path.exists(request_dir)


def test_small_video_is_kept_when_ffprobe_is_unavailable(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "reel.mp4"
    file_path.write_bytes(b"video")

    async def missing_binary(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(video_module.asyncio, "create_subprocess_exec", missing_binary)

    result = asyncio.run(
        video_module.ensure_discord_ready(
            str(file_path), log=facebook_module.log, source="facebook"
        )
    )

    assert result == str(file_path)


def _message_mock():
    channel = SimpleNamespace(id=123, send=AsyncMock())
    return SimpleNamespace(
        channel=channel,
        add_reaction=AsyncMock(),
        remove_reaction=AsyncMock(),
    )


def test_handle_facebook_reel_sends_file_and_cleans_up(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "reel.mp4"
    file_path.write_bytes(b"video")
    url = "https://www.facebook.com/reel/2281511879286424"
    result = FacebookResult(str(file_path), 1.0, url)
    service = SimpleNamespace(download=AsyncMock(return_value=result), cleanup=Mock())
    bot = SimpleNamespace(user=object())
    message = _message_mock()

    monkeypatch.setattr(facebook_handler, "facebook_service", service)
    monkeypatch.setattr(facebook_handler, "bot", bot)
    monkeypatch.setattr(facebook_handler.discord, "File", lambda path: ("file", path))

    asyncio.run(facebook_handler.handle_facebook_reel(message, url))

    message.channel.send.assert_awaited_once_with(file=("file", str(file_path)))
    assert message.add_reaction.await_args_list[0].args == ("⏳",)
    assert message.add_reaction.await_args_list[1].args == ("✅",)
    message.remove_reaction.assert_awaited_once_with("⏳", bot.user)
    service.cleanup.assert_called_once_with(str(file_path))


def test_handle_facebook_reel_falls_back_to_url_when_too_large(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "large.mp4"
    file_path.write_bytes(b"video")
    url = "https://www.facebook.com/reel/2281511879286424"
    result = FacebookResult(str(file_path), 10.1, url)
    service = SimpleNamespace(download=AsyncMock(return_value=result), cleanup=Mock())
    message = _message_mock()

    monkeypatch.setattr(facebook_handler, "facebook_service", service)

    asyncio.run(facebook_handler.handle_facebook_reel(message, url))

    message.channel.send.assert_awaited_once_with(url)
    service.cleanup.assert_called_once_with(str(file_path))


def test_handle_facebook_reel_marks_failure(monkeypatch) -> None:
    service = SimpleNamespace(
        download=AsyncMock(side_effect=RuntimeError("download failed")), cleanup=Mock()
    )
    bot = SimpleNamespace(user=object())
    message = _message_mock()

    monkeypatch.setattr(facebook_handler, "facebook_service", service)
    monkeypatch.setattr(facebook_handler, "bot", bot)

    asyncio.run(
        facebook_handler.handle_facebook_reel(
            message, "https://www.facebook.com/reel/2281511879286424"
        )
    )

    message.channel.send.assert_not_awaited()
    assert message.add_reaction.await_args_list[0].args == ("⏳",)
    assert message.add_reaction.await_args_list[1].args == ("❌",)
    message.remove_reaction.assert_awaited_once_with("⏳", bot.user)
    service.cleanup.assert_not_called()
