"""鲁班站点卡 lesson viewmodel——投影门（双轮 v3.2 §7）的第一个 runtime 消费者。

Thin 投影层（§3 所有权表）：本模块**只读投影、零生成**——
- 签发真值唯一来源 = `_pack_manifest.json`（manifest 绿灯 =
  ``published ∧ jury_clean ∧ not explicitly_barred_default_entry``，fail-closed：
  不在绿灯集合的 pack 与不存在的 pack 同样不可见，防未签发内容泄漏）；
- 变体池只报数量与 sha（runtime 抽取归复测链路，本模块不展开题面）；
- 讲懂卡 URL = 业务托管基址（env ``LUBAN_LESSON_CARD_BASE``）+ pack slug 约定，
  卡产物按压缩预研 0.39MB 口径产出并开 Content-Encoding（托管侧职责）；
- ``content_sha256`` 透传给客户端作缓存键（§9-D7/D8：pack 升版 → sha 变 → 重取）。

学习证据边界（防第四 builder）：本模块**不写任何学习证据**。档位①②轻练走既有
``learner_signal`` 路由（非 promoting），档位③走判分链路——写侧一个不加。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = (
    _REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
)
_VARIANT_BANK_TEMPLATE = "_{pack_id}_variant_bank.v0.json"
_CARD_BASE_ENV = "LUBAN_LESSON_CARD_BASE"


class LessonNotAvailable(Exception):
    """pack 不存在或未过投影门——两者对外同形（fail-closed，不泄漏未签发存在性）。"""


def _load_manifest(manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or _MANIFEST_PATH
    if not path.exists():
        # manifest 缺失 = 供给面不可用，整体 fail-closed
        return {"projection_green": [], "packs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"projection_green": [], "packs": []}


def _card_url(pack_id: str) -> str:
    base = str(os.getenv(_CARD_BASE_ENV) or "").strip().rstrip("/")
    if not base:
        return ""  # 托管未配置：viewmodel 仍可用（练档数据不依赖卡），客户端按无卡降级
    return f"{base}/{pack_id.lower()}/lesson.html"


def _variant_summary(pack_id: str, manifest_dir: Path) -> dict[str, Any]:
    path = manifest_dir / _VARIANT_BANK_TEMPLATE.format(pack_id=pack_id)
    if not path.exists():
        return {"available": False, "count": 0}
    try:
        bank = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "count": 0}
    variants = bank.get("variants") or []
    return {
        "available": bool(variants),
        "count": len(variants),
        "bank_status": str(bank.get("status") or ""),
        "source_pack_sha256": str(bank.get("source_pack_sha256") or ""),
    }


def list_green_lessons(*, manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """绿灯站点列表投影（地图/路线消费）；只含绿灯包，锁定站的露脸文案归上层。"""
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    rows = []
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        rows.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "content_sha256": str(pack.get("content_sha256") or ""),
            }
        )
    return sorted(rows, key=lambda r: r["pack_id"])


def count_registered_packs(*, manifest_path: Path | None = None) -> int:
    """路线总站数权威 = manifest 注册包数（含未签发）；manifest 缺失/损坏 → 0，
    客户端按 0 隐藏总数与占位 slot（不造数），禁前端硬编码第二套总量。"""
    return len(_load_manifest(manifest_path).get("packs") or [])


def build_lesson_viewmodel(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单站 viewmodel；不过投影门一律 LessonNotAvailable（fail-closed）。"""
    pack_id = str(pack_id or "").strip().upper()
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    if pack_id not in green:
        raise LessonNotAvailable(pack_id)
    pack = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id),
        None,
    )
    if pack is None:  # manifest 自身不一致也 fail-closed
        raise LessonNotAvailable(pack_id)
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    return {
        "pack_id": pack_id,
        "title": str(pack.get("title") or ""),
        "content_sha256": str(pack.get("content_sha256") or ""),
        "card_url": _card_url(pack_id),
        "variant_retest": _variant_summary(pack_id, manifest_dir),
        # 证据写入路径声明（客户端按此接线，防第四 builder）：
        "evidence_channels": {
            "light_practice": "learner_signal",  # 档位①②（非 promoting）
            "full_answer": "case_grading",  # 档位③（判分内核链路）
        },
    }


def build_retest_items(
    pack_id: str,
    *,
    user_id: str,
    day_index: int,
    limit: int = 5,
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """次日变体复测题面投影——runtime 只从编译期预生成池**抽取**（§8 红线）。

    确定性轮换：同一用户同一天取同一切片（多端幂等，§9-D3）；跨天按
    ``day_index``（服务端本地日，§9-D2）前进，池耗尽自动回绕复用旧变体
    （产能报告的降级预案①，绝不 runtime 现编）。只发核心变体
    （extension=false）；judge 所需的期望判定随题下发（判断题二选一，
    本地确定性判分=档位①，D5 离线可用）。
    """
    vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)
    if not vm["variant_retest"]["available"]:
        return []
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank_path = manifest_dir / _VARIANT_BANK_TEMPLATE.format(pack_id=vm["pack_id"])
    try:
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    core = [v for v in bank.get("variants") or [] if not v.get("extension")]
    if not core:
        return []
    limit = max(1, min(int(limit), 10))
    seed = sum(ord(c) for c in str(user_id)) + int(day_index)
    start = seed % len(core)
    picked = [core[(start + i) % len(core)] for i in range(min(limit, len(core)))]
    return [
        {
            "variant_id": v["variant_id"],
            "rule_group": v["rule_group"],
            "surface": v["surface"],
            "expected_ok": bool(v["expected_ok"]),
            "correct_statement": v["correct_statement"],
            "anchor": v["anchor"],
        }
        for v in picked
    ]
