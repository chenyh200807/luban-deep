"""Building-case anchor helpers — re-export of the single source of truth.

锚点正则/抽取已收敛到 ``deeptutor.core.grounding``（单一定义，见 task#23 §簇3）。
本模块保留为既有 import 路径的薄转发，避免改动其它导入点；不要在这里重新定义副本。
"""

from __future__ import annotations

from deeptutor.core.grounding import (
    BUILDING_ANCHOR_RE,
    extract_anchor_terms,
    render_anchor_contract,
)

# 兼容旧的下划线别名（部分调用处历史上引用 _BUILDING_ANCHOR_RE）。
_BUILDING_ANCHOR_RE = BUILDING_ANCHOR_RE

__all__ = [
    "BUILDING_ANCHOR_RE",
    "extract_anchor_terms",
    "render_anchor_contract",
]
