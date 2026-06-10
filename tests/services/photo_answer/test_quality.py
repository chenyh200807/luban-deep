"""图像质检启发式测试（PIL 合成图，零真实样本依赖）。"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter

from deeptutor.services.photo_answer.quality import assess_image_quality


def _img_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _sharp_text_image() -> Image.Image:
    img = Image.new("L", (1200, 1600), color=245)
    draw = ImageDraw.Draw(img)
    for row in range(12):
        y = 80 + row * 120
        draw.line([(60, y), (1140, y)], fill=20, width=4)
        for x in range(80, 1100, 90):
            draw.rectangle([x, y - 40, x + 40, y - 5], outline=10, width=3)
    return img


def test_sharp_well_lit_image_passes():
    q = assess_image_quality(_img_bytes(_sharp_text_image()))
    assert q["ok"] is True
    assert q["issues"] == []
    assert q["width"] == 1200 and q["height"] == 1600


def test_blurry_image_flagged():
    blurred = _sharp_text_image().filter(ImageFilter.GaussianBlur(radius=8))
    q = assess_image_quality(_img_bytes(blurred))
    assert q["ok"] is False
    assert "blurry" in q["issues"]


def test_dark_image_flagged():
    dark = Image.new("L", (1200, 1600), color=18)
    q = assess_image_quality(_img_bytes(dark))
    assert q["ok"] is False
    assert "too_dark" in q["issues"]


def test_tiny_image_flagged():
    tiny = Image.new("L", (200, 260), color=240)
    q = assess_image_quality(_img_bytes(tiny))
    assert q["ok"] is False
    assert "low_resolution" in q["issues"]


def test_invalid_bytes_flagged_not_raised():
    q = assess_image_quality(b"not an image at all")
    assert q["ok"] is False
    assert "unreadable" in q["issues"]
