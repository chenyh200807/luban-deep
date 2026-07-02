"""Dockerfile COPY 源 ↔ .dockerignore 可见性守卫。

复发类防线（2026-07-02 #344 事故）：Dockerfile 给 build 加 COPY 后，
`.dockerignore` 把源文件挡在 build context 外——CI 不 build 生产 stage，
错误只在远端部署时爆（failed to calculate checksum ... not found）。
本测试在 CI 层面钉死：每个显式文件型 COPY 源都必须对 build context 可见。
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _dockerignore_patterns() -> list[str]:
    lines = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def _excluded(path: str, patterns: list[str]) -> bool:
    # dockerignore 语义近似: 逐条匹配, last-match-wins, `!` 为反排除
    verdict = False
    for pat in patterns:
        neg = pat.startswith("!")
        core = (pat[1:] if neg else pat).rstrip("/")
        hit = (
            fnmatch.fnmatch(path, core)
            or path.startswith(core + "/")
            or fnmatch.fnmatch(path, core + "/*")
        )
        if hit:
            verdict = not neg
    return verdict


def _copy_sources() -> list[str]:
    """抽取 Dockerfile 里显式文件型 COPY 源（JSON 形式与空格形式；忽略 --from= 阶段拷贝与通配）。"""
    sources: list[str] = []
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY") or "--from=" in line:
            continue
        rest = line[4:].strip()
        parts: list[str]
        if rest.startswith("["):
            try:
                parts = json.loads(rest)
            except Exception:
                continue
        else:
            parts = [p for p in re.split(r"\s+", rest) if not p.startswith("--")]
        for src in parts[:-1]:  # 最后一个是目的地
            src = src.strip().lstrip("./")
            if not src or "*" in src or "?" in src:
                continue
            sources.append(src)
    return sources


def test_every_dockerfile_copy_source_visible_to_build_context() -> None:
    patterns = _dockerignore_patterns()
    invisible = []
    for src in _copy_sources():
        # 目录型源: 只要目录本身没被整体排除即可(内部逐文件由 docker 处理)
        if _excluded(src, patterns):
            invisible.append(src)
    assert not invisible, (
        f"Dockerfile COPY 源被 .dockerignore 挡在 build context 外(远端 build 必败): {invisible}; "
        "在 .dockerignore 里给它们加 `!` 反排除, 或改 COPY 路径"
    )


def test_double_wheel_supply_files_visible() -> None:
    """#344 的两个供给文件必须可见(退化守卫, 防有人删反排除行)。"""
    patterns = _dockerignore_patterns()
    for f in (
        "docs/原始数据/考点原料/成品/_pack_manifest.json",
        "docs/原始数据/考点原料/成品/_S05_variant_bank.v0.json",
    ):
        assert not _excluded(f, patterns), f"{f} 被 .dockerignore 排除"
