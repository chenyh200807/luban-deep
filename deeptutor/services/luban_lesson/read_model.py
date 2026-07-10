"""鲁班站点卡 lesson viewmodel——投影门（双轮 v3.2 §7）的第一个 runtime 消费者。

Thin 投影层（§3 所有权表）：本模块**只读投影、零生成**——
- 签发真值唯一来源 = `_pack_manifest.json`（manifest 绿灯 =
  ``published ∧ jury_clean ∧ not explicitly_barred_default_entry``，fail-closed：
  不在绿灯集合的 pack 与不存在的 pack 同样不可见，防未签发内容泄漏）；
- 变体池只报数量与 sha（runtime 抽取归复测链路，本模块不展开题面）；
  且**只认签发池**（双 fail-closed）：bank ``status=="signed"`` 且
  ``source_pack_sha256`` 与 manifest 该 pack 的 ``content_sha256`` 一致——
  candidate 未签发/pack 正文修订后的旧变体，一律与 bank 缺失同形不可见
  （签发动作 = ``docs/原始数据/考点原料/promote_variant_bank.py``，人闸）；
- 讲懂卡 URL = 业务托管基址（env ``LUBAN_LESSON_CARD_BASE``）+ pack slug 约定，
  卡产物按压缩预研 0.39MB 口径产出并开 Content-Encoding（托管侧职责）；
- ``content_sha256`` 透传给客户端作缓存键（§9-D7/D8：pack 升版 → sha 变 → 重取）。

学习证据边界（防第四 builder）：本模块**不写任何学习证据**。档位①②轻练走既有
``learner_signal`` 路由（非 promoting），档位③走判分链路；学-evidence
（lesson_viewed）唯一 writer = ``learner_state/lesson_evidence.py``（经
``lesson_progress`` 路由，融合计划 §2.1）——本投影模块仍零写入。
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
_CONCEPT_CARD_BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"
_R6_CLOZE_BANK_TEMPLATE = "_{pack_id}_r6_cloze_bank.v0.json"
_R8_ANTIDOTE_BANK_TEMPLATE = "_{pack_id}_r8_antidote_bank.v0.json"
_CARD_BASE_ENV = "LUBAN_LESSON_CARD_BASE"

# 复习考点卡逐字投影字段（§6.2：考点 front + 关键词颗粒 key_gist + 教材原文
# quote + 出处 point_id/source_ref/leaf_name_path）——只从签发 bank 已有字段
# 里挑选透传，一个字不新造/不改写；bank 缺某字段则该字段不出现（不补默认值）。
_CONCEPT_CARD_PROJECT_FIELDS = (
    "card_id",
    "front",
    "key_gist",
    "quote",
    "point_id",
    "source_ref",
    "leaf_name_path",
)


class LessonNotAvailable(Exception):
    """pack 不存在或未过投影门——两者对外同形（fail-closed，不泄漏未签发存在性）。"""


# manifest 模块级缓存(照 pack_lifecycle_projection 的 (mtime_ns, size) 模式,
# 病B-3):命中零解析;产物更新(stat 键变)自动失效;失败(缺文件/损坏)
# fail-closed 且**不缓存**——修好文件后同进程下次调用即恢复。
_MANIFEST_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
_MANIFEST_UNAVAILABLE: dict[str, Any] = {"projection_green": [], "packs": []}


def _load_manifest(manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or _MANIFEST_PATH
    try:
        stat = path.stat()
        stat_key = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        # manifest 缺失 = 供给面不可用，整体 fail-closed
        return dict(_MANIFEST_UNAVAILABLE)
    cache_key = str(path)
    cached = _MANIFEST_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat_key:
        return cached[1]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_MANIFEST_UNAVAILABLE)
    _MANIFEST_CACHE[cache_key] = (stat_key, manifest)
    return manifest


def _card_url(pack_id: str) -> str:
    base = str(os.getenv(_CARD_BASE_ENV) or "").strip().rstrip("/")
    if not base:
        return ""  # 托管未配置：viewmodel 仍可用（练档数据不依赖卡），客户端按无卡降级
    return f"{base}/{pack_id.lower()}/lesson.html"


def _load_signed_bank(
    pack_id: str,
    manifest_dir: Path,
    expected_sha: str,
    filename_template: str = _VARIANT_BANK_TEMPLATE,
) -> dict[str, Any] | None:
    """供给池签发闸（双 fail-closed，所有 bank 读取的唯一入口——含考点卡池，
    考点卡 loader 传自己的 ``filename_template`` 复用同一闸，禁分叉第二 loader）。

    只放行 ``status=="signed"`` 且 ``source_pack_sha256`` == manifest 该 pack
    ``content_sha256`` 的 bank；candidate 未签发、pack 正文修订后的 sha 漂移、
    文件缺失/损坏，一律返回 None（对外与 bank 缺失同形，不泄漏未签发存在性）。
    """
    path = manifest_dir / filename_template.format(pack_id=pack_id)
    try:
        bank = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(bank, dict):
        return None
    if str(bank.get("status") or "") != "signed":
        return None  # candidate/未知状态 = 未签发，不可直通真实考生
    expected_sha = str(expected_sha or "").strip()
    if not expected_sha or str(bank.get("source_pack_sha256") or "") != expected_sha:
        return None  # pack 正文已修订（或 manifest 无 sha），旧变体失效
    return bank


def _variant_summary(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, Any]:
    bank = _load_signed_bank(pack_id, manifest_dir, expected_sha)
    if bank is None:
        return {"available": False, "count": 0}
    variants = bank.get("variants") or []
    return {
        "available": bool(variants),
        "count": len(variants),
        "bank_status": "signed",
        "source_pack_sha256": str(bank.get("source_pack_sha256") or ""),
    }


def _concept_summary(pack_id: str, manifest_dir: Path, expected_sha: str) -> str:
    """路线卡副标题真源：签发考点卡池首卡 ``front``（该 pack §1 第一个关键知识点，
    ``build_luban_concept_card_bank.py`` 确定性派生自签发 pack + 教材逐字 quote）。

    走 ``_load_signed_bank`` 单一签发闸（signed + sha 双 fail-closed，与变体池同闸）；
    bank 缺失/未签发/sha 漂移/无卡 → 返回 ""（副标题该站留空，客户端 fail-closed
    不造词）。零生成——只逐字透传首卡 ``front``，不摘要不改写。
    """
    bank = _load_signed_bank(
        pack_id, manifest_dir, expected_sha, filename_template=_CONCEPT_CARD_BANK_TEMPLATE
    )
    if bank is None:
        return ""
    cards = bank.get("cards") or []
    if not cards or not isinstance(cards[0], dict):
        return ""
    return str(cards[0].get("front") or "")


def _review_concept_cards(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> list[dict[str, Any]]:
    """复习模块考点卡投影（§6.2）——签发考点卡池逐字透传为复习列表。

    走 ``_load_signed_bank`` 单一签发闸（signed + sha 双 fail-closed，与变体池
    /副标题同闸，不分叉第二 loader）。bank 缺失/未签发/sha 漂移/无卡 → 返回 ``[]``
    （fail-closed，复习模块该 pack 无考点卡，绝不现编）。零生成——只从每张卡
    ``_CONCEPT_CARD_PROJECT_FIELDS`` 里已有的字段逐字挑选，不摘要不改写不补默认。
    """
    bank = _load_signed_bank(
        pack_id, manifest_dir, expected_sha, filename_template=_CONCEPT_CARD_BANK_TEMPLATE
    )
    if bank is None:
        return []
    out: list[dict[str, Any]] = []
    for card in bank.get("cards") or []:
        if not isinstance(card, dict):
            continue
        out.append(
            {k: card[k] for k in _CONCEPT_CARD_PROJECT_FIELDS if k in card}
        )
    return out


def _cloze_fill(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, Any]:
    """关键词填空投影（§5.2 练档位①）——签发 r6 挖空池逐字透传。

    走同一签发闸（signed + sha 双 fail-closed）。bank 缺失/未签发/sha 漂移 →
    ``{"available": False, "items": []}``（fail-closed）。空池同形。items 逐字
    透传 bank 已有条目（不对条目内部字段做任何生成/改写/schema 强加——挖空题面
    的采分句骨架与关键词是签发期真值，runtime 只投影）。
    """
    bank = _load_signed_bank(
        pack_id, manifest_dir, expected_sha, filename_template=_R6_CLOZE_BANK_TEMPLATE
    )
    if bank is None:
        return {"available": False, "items": []}
    items = [i for i in bank.get("items") or [] if isinstance(i, dict)]
    return {"available": bool(items), "items": items}


def _antidotes(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, list[dict[str, Any]]]:
    """错因银行解药投影（§6.4）——签发 r8 解药池按 ``error_code`` 逐字投影。

    走同一签发闸（signed + sha 双 fail-closed）。bank 缺失/未签发/sha 漂移 →
    ``{}``（fail-closed，无解药层）。解药条目按 ``error_code`` 归组（§6.4 同错因
    聚焦），条目逐字透传 bank 已有字段（error_code + 采分点 + 原题背景 + 解药正文
    均为签发期真值，禁二次 LLM 归因，§ 表 R8 行）。无 ``error_code`` 的条目跳过
    （fail-closed：不虚构错因码）。
    """
    bank = _load_signed_bank(
        pack_id, manifest_dir, expected_sha, filename_template=_R8_ANTIDOTE_BANK_TEMPLATE
    )
    if bank is None:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for entry in bank.get("antidotes") or []:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("error_code") or "").strip()
        if not code:
            continue  # 无错因码不投影(fail-closed,不虚构归因)
        out.setdefault(code, []).append(entry)
    return out


def list_all_pack_ids(*, manifest_path: Path | None = None) -> list[str]:
    """40 pack 全集（pack_id 排序，非 manifest 登记序；消费者当集合用）
    ——生命周期投影「未学」态的枚举范围
    （融合计划 §1.1：考点全集 = 60-slot 注册表的 40 pack，不是 1976 叶）。
    只读 manifest，绿灯与否不影响「未学」枚举（锁定站也如实是未学）。"""
    manifest = _load_manifest(manifest_path)
    return sorted(
        str(pack.get("pack_id") or "").strip()
        for pack in manifest.get("packs") or []
        if str(pack.get("pack_id") or "").strip()
    )


def list_green_lessons(*, manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """绿灯站点列表投影（地图/路线消费）；只含绿灯包，锁定站的露脸文案归上层。"""
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    rows = []
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        content_sha = str(pack.get("content_sha256") or "")
        rows.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "content_sha256": content_sha,
                # 副标题真源：签发考点卡首卡 front（无卡→""，前端 fail-closed 留空）
                "summary": _concept_summary(pack["pack_id"], manifest_dir, content_sha),
            }
        )
    return sorted(rows, key=lambda r: r["pack_id"])


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
        # card_hosted=manifest 确定性扫描(web/public/luban-preview/<id>/lesson.html 实存);
        # 非 hosted 站不发 URL——防 web-view 打开 404(部署探针实证 22/28 站无卡)
        "card_url": _card_url(pack_id) if pack.get("card_hosted") else "",
        "variant_retest": _variant_summary(
            pack_id, manifest_dir, str(pack.get("content_sha256") or "")
        ),
        # 复习模块三层母题集投影（双轮 v3 §6.2/§5.2/§6.4）——全部走 variant_retest
        # 同一签发闸（signed + sha 双 fail-closed），只读已签发逐字内容、零生成；
        # 无签发池的层各自 fail-closed（考点卡/解药空、挖空 available:false）。
        "review_concept_cards": _review_concept_cards(
            pack_id, manifest_dir, str(pack.get("content_sha256") or "")
        ),
        "cloze_fill": _cloze_fill(
            pack_id, manifest_dir, str(pack.get("content_sha256") or "")
        ),
        "antidotes": _antidotes(
            pack_id, manifest_dir, str(pack.get("content_sha256") or "")
        ),
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

    签发闸（双 fail-closed）：只从 ``status=="signed"`` 且 sha 锚定当前 pack
    正文的 bank 抽取——不满足与 bank 缺失同形返回 ``[]``（既有降级）。
    """
    vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)
    if not vm["variant_retest"]["available"]:
        return []
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank = _load_signed_bank(vm["pack_id"], manifest_dir, vm["content_sha256"])
    if bank is None:
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
