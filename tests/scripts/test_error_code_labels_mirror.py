"""前端错因名镜像 ↔ ERROR_CODE_REGISTRY 同步闸（owner 方案 A：registry 名直展）。

单一权威=deeptutor/contracts/error_codes.py；前端 utils/error-code-labels.js 只是
只读镜像。本测试钉死两边逐码一致——registry 增删改码时镜像不同步即 CI 红。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _registry() -> dict[str, str]:
    src = (REPO / "deeptutor/contracts/error_codes.py").read_text(encoding="utf-8")
    return dict(re.findall(r'"([EM]\d+)":\s*\{"label":\s*"([^"]+)"', src))


def _mirror() -> dict[str, str]:
    src = (REPO / "yousenwebview/packageDeeptutor/utils/error-code-labels.js").read_text(
        encoding="utf-8"
    )
    return dict(re.findall(r'([EM]\d+):\s*"([^"]+)"', src))


def test_frontend_labels_mirror_registry_exactly() -> None:
    reg, mir = _registry(), _mirror()
    assert reg, "registry 解析为空——正则或文件路径坏了"
    assert mir == reg, (
        f"前端镜像与 registry 漂移: 缺={set(reg) - set(mir)} 多={set(mir) - set(reg)} "
        f"名不一致={ {k for k in set(reg) & set(mir) if reg[k] != mir[k]} }"
    )
