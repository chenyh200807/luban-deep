"""Image quality heuristics — pre-OCR gate (plan §5 worker step 1).

PIL-only on purpose: no numpy/OpenCV dependency. Heuristics are coarse —
their job is catching obviously unusable shots before we pay for OCR, and
feeding the "建议重拍" client hint. Thresholds are conservative so we never
block a usable photo (false reject costs a user; false accept costs 0.01元).
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageFilter, ImageStat

MIN_DIMENSION_PX = 480
DARK_MEAN_FLOOR = 40.0  # 0-255 grayscale mean below this = severely underexposed
BLUR_EDGE_STDDEV_FLOOR = 18.0  # edge stddev: 合成清晰文本图 ~49，高斯模糊后 ~13；M0 真实样本再标定

PREPROCESS_VERSION = "quality-v1"


def assess_image_quality(image_bytes: bytes) -> dict[str, Any]:
    issues: list[str] = []
    width = height = 0
    brightness = 0.0
    edge_stddev = 0.0
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        return {
            "ok": False,
            "issues": ["unreadable"],
            "width": 0,
            "height": 0,
            "brightness": 0.0,
            "edge_stddev": 0.0,
        }

    width, height = img.size
    gray = img.convert("L")
    brightness = float(ImageStat.Stat(gray).mean[0])
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stddev = float(ImageStat.Stat(edges).stddev[0])

    if min(width, height) < MIN_DIMENSION_PX:
        issues.append("low_resolution")
    if brightness < DARK_MEAN_FLOOR:
        issues.append("too_dark")
    # 全黑/低分辨率图的 edge 能量天然低，避免重复报 blurry
    elif edge_stddev < BLUR_EDGE_STDDEV_FLOOR and "low_resolution" not in issues:
        issues.append("blurry")

    return {
        "ok": not issues,
        "issues": issues,
        "width": width,
        "height": height,
        "brightness": round(brightness, 2),
        "edge_stddev": round(edge_stddev, 2),
    }
