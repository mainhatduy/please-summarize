from app.services.tiktok import TikTokService


def test_detect_tiktok_url_supports_common_hosts() -> None:
    service = TikTokService.__new__(TikTokService)

    assert service.detect_tiktok_url("xem https://www.tiktok.com/@a/video/123 nhé") == (
        "https://www.tiktok.com/@a/video/123"
    )
    assert service.detect_tiktok_url("https://vm.tiktok.com/abc123/") == (
        "https://vm.tiktok.com/abc123/"
    )
    assert service.detect_tiktok_url("không có link") is None
