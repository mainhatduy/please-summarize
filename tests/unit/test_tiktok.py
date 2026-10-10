from unittest.mock import AsyncMock, patch

import pytest

from app.services.tiktok import TikTokResult, TikTokService


def test_detect_tiktok_url_supports_common_hosts() -> None:
    service = TikTokService.__new__(TikTokService)

    assert service.detect_tiktok_url("xem https://www.tiktok.com/@a/video/123 nhé") == (
        "https://www.tiktok.com/@a/video/123"
    )
    assert service.detect_tiktok_url("https://vm.tiktok.com/abc123/") == (
        "https://vm.tiktok.com/abc123/"
    )
    assert service.detect_tiktok_url("https://vt.tiktok.com/abc123/") == (
        "https://vt.tiktok.com/abc123/"
    )
    assert service.detect_tiktok_url("https://m.tiktok.com/v/123.html") == (
        "https://m.tiktok.com/v/123.html"
    )
    assert service.detect_tiktok_url("https://www.tt.site/t/ZSbWbfaD7/") == (
        "https://www.tt.site/t/ZSbWbfaD7/"
    )
    assert service.detect_tiktok_url("https://tt.site/t/ZSbWbfaD7/") == (
        "https://tt.site/t/ZSbWbfaD7/"
    )
    assert service.detect_tiktok_url("<https://www.tt.site/t/ZSbWbfaD7/>") == (
        "https://www.tt.site/t/ZSbWbfaD7/"
    )
    assert service.detect_tiktok_url("(https://www.tt.site/t/ZSbWbfaD7/).") == (
        "https://www.tt.site/t/ZSbWbfaD7/"
    )
    assert service.detect_tiktok_url("không có link") is None
    assert service.detect_tiktok_url("https://fakett.site/t/123") is None
    assert service.detect_tiktok_url("https://not-tiktok.com/123") is None


@pytest.mark.anyio
async def test_resolve_url_resolves_redirect() -> None:
    service = TikTokService.__new__(TikTokService)
    service._BROWSER_HEADERS = {}

    target_url = "https://www.tiktok.com/@user/video/123"

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.url = target_url

    mock_client = AsyncMock()
    mock_client.head.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        resolved = await service._resolve_url("https://www.tt.site/t/ZSbWbfaD7/")
        assert resolved == target_url


@pytest.mark.anyio
async def test_download_resolves_tt_site_url_before_fetching_tikwm() -> None:
    service = TikTokService.__new__(TikTokService)
    service._download_dir = "/tmp"

    resolved_url = "https://www.tiktok.com/@user/video/7694615842121665813"
    service._resolve_url = AsyncMock(return_value=resolved_url)
    service._fetch_tikwm = AsyncMock(return_value={"id": "123", "play": "http://cdn/123.mp4"})
    expected_result = TikTokResult(
        content_type="video",
        file_path="/tmp/123.mp4",
        file_size_mb=1.5,
        direct_url="http://cdn/123.mp4",
    )
    service._download_video = AsyncMock(return_value=expected_result)

    result = await service.download("https://www.tt.site/t/ZSbWbfaD7/")

    service._resolve_url.assert_awaited_once_with("https://www.tt.site/t/ZSbWbfaD7/")
    service._fetch_tikwm.assert_awaited_once_with(resolved_url)
    assert result == expected_result
