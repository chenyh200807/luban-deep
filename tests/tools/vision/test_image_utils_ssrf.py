"""SSRF guard for image URL fetching — must reject internal/metadata addresses."""

from __future__ import annotations

import pytest

from deeptutor.tools.vision.image_utils import (
    ImageError,
    _is_ssrf_safe_host,
    fetch_image_from_url,
)


def test_ssrf_guard_rejects_internal_and_metadata_hosts() -> None:
    assert _is_ssrf_safe_host("127.0.0.1") is False
    assert _is_ssrf_safe_host("localhost") is False
    assert _is_ssrf_safe_host("169.254.169.254") is False  # cloud metadata
    assert _is_ssrf_safe_host("100.100.100.200") is False  # Aliyun metadata
    assert _is_ssrf_safe_host("10.0.0.5") is False
    assert _is_ssrf_safe_host("192.168.1.1") is False
    assert _is_ssrf_safe_host("::1") is False


def test_ssrf_guard_allows_public_host() -> None:
    assert _is_ssrf_safe_host("8.8.8.8") is True


@pytest.mark.asyncio
async def test_fetch_image_refuses_metadata_endpoint() -> None:
    with pytest.raises(ImageError, match="non-public address"):
        await fetch_image_from_url("http://169.254.169.254/latest/meta-data/")
