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
_CARD_BASE_ENV = "LUBAN_LESSON_CARD_BASE"


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
    ``concept_cards.py`` 传自己的 ``filename_template`` 复用同一闸，禁分叉第二 loader）。

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
    """绿灯站点列表投影（地图/路线消费）；只含绿灯包，锁定站的露脸文案归上层。

    ``retest_available`` = signed 变体池真值（复用 ``_variant_summary`` 同一闸，
    不建第二判定）——供学习页头牌轻练按供给路由/降级：承诺宽度收窄到有货的
    站，不对空池站渲染练不了的按钮。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    rows = []
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        rows.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "content_sha256": str(pack.get("content_sha256") or ""),
                "retest_available": _variant_summary(
                    str(pack["pack_id"]),
                    manifest_dir,
                    str(pack.get("content_sha256") or ""),
                )["available"],
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
        # 证据写入路径声明（客户端按此接线，防第四 builder）：
        "evidence_channels": {
            "light_practice": "learner_signal",  # 档位①②（非 promoting）
            "full_answer": "case_grading",  # 档位③（判分内核链路）
        },
    }


def _forward_rule_group_spread(
    core: list[dict[str, Any]], seed: int, limit: int
) -> list[dict[str, Any]]:
    """正向轻练选序：确定性广度优先 round-robin 覆盖不同 ``rule_group``——
    对刚学完的 pack 先各考法采样一题、再回填（学习轮"先广后深"）。

    与复测的扁平轮换的唯一差别是**选序**：纯签发池内确定性重排，零生成、
    零新供给（不派生任何题面字段，§8 红线）。组内起点按同一 ``seed`` 轮换
    （多端幂等）；组间按轮次交错；题数 ≤ 核心变体数（耗尽即止）。
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for variant in core:
        groups.setdefault(str(variant.get("rule_group") or ""), []).append(variant)
    keys = list(groups.keys())  # 保持首次出现序，确定性
    interleaved: list[dict[str, Any]] = []
    round_idx = 0
    while any(round_idx < len(groups[k]) for k in keys):
        for k in keys:
            members = groups[k]
            if round_idx < len(members):
                interleaved.append(members[(seed + round_idx) % len(members)])
        round_idx += 1
    return interleaved[: min(limit, len(core))]


def build_retest_items(
    pack_id: str,
    *,
    user_id: str,
    day_index: int,
    limit: int = 5,
    mode: str = "review",
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """变体题面投影——runtime 只从编译期预生成池**抽取**（§8 红线）。

    两种取题模式共用**同一签发池、同一 builder**（不分叉第二 builder）：
    - ``mode="review"``（默认，复习轮换皮复测）：跨天扁平确定性轮换，同一用户
      同一天取同一切片（多端幂等，§9-D3）；跨天按 ``day_index``（服务端本地日，
      §9-D2）前进，池耗尽自动回绕复用旧变体（产能降级预案①，绝不 runtime 现编）。
    - ``mode="forward"``（学习轮 2 分钟轻练，对刚学完的 pack 立即练一遍）：广度
      优先 round-robin 覆盖不同 ``rule_group``（见 ``_forward_rule_group_spread``）。
      仅**选序**不同，证据仍走 learner_signal 非 promoting（轻练不关闭弱点，PRD 红线）。

    两模式都只发核心变体（extension=false）；judge 所需期望判定随题下发（判断题
    二选一，本地确定性判分，D5 离线可用）。对外只投影签发字段
    {variant_id, rule_group, surface, expected_ok, correct_statement, anchor}——
    绝不派生 scoring_point 文本 / exam_refs / chapter（变体池无此供给=不臆造）。

    ``textbook``（可选字段）= **同 pack** 签发考点卡 bank 按 ``anchor == point_id``
    精确 join 出的教材原文并排卡 {quote, label, page_num}。这不是派生/生成——
    quote 逐字来自已签发考点卡（同一 ``_load_signed_bank`` 双闸），坐标系同为
    kc: 锚。join 不中 / 卡池未签发 → 字段缺省（fail-closed，前端有原文才亮）。
    跨包借 quote 红线不适用：只 join 自己 pack 的卡池。

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
    if str(mode or "").strip().lower() == "forward":
        picked = _forward_rule_group_spread(core, seed, limit)
    else:
        start = seed % len(core)
        picked = [core[(start + i) % len(core)] for i in range(min(limit, len(core)))]
    textbook_by_point = _textbook_quote_index(
        vm["pack_id"], manifest_dir, vm["content_sha256"]
    )
    rows: list[dict[str, Any]] = []
    for v in picked:
        row: dict[str, Any] = {
            "variant_id": v["variant_id"],
            "rule_group": v["rule_group"],
            "surface": v["surface"],
            "expected_ok": bool(v["expected_ok"]),
            "correct_statement": v["correct_statement"],
            "anchor": v["anchor"],
        }
        textbook = textbook_by_point.get(str(v.get("anchor") or ""))
        if textbook:
            row["textbook"] = textbook
        rows.append(row)
    return rows


_CONCEPT_CARD_BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"


def _textbook_quote_index(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, dict[str, Any]]:
    """同 pack 签发考点卡 → {point_id: 教材原文并排卡}（retest join 用）。

    quote/label 逐字透传签发卡字段（zero 生成）；卡池未签发/缺失 → 空 index
    （fail-closed，retest 不带 textbook 字段照常工作）。
    """
    bank = _load_signed_bank(
        pack_id,
        manifest_dir,
        expected_sha,
        filename_template=_CONCEPT_CARD_BANK_TEMPLATE,
    )
    if bank is None:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for card in bank.get("cards") or []:
        point_id = str(card.get("point_id") or "").strip()
        quote = str(card.get("quote") or "").strip()
        if not point_id or not quote:
            continue
        source_ref = card.get("source_ref") or {}
        page_num = source_ref.get("page_num") if isinstance(source_ref, dict) else None
        index[point_id] = {
            "quote": quote,
            "label": str(card.get("front") or ""),
            "page_num": page_num if isinstance(page_num, int) else None,
        }
    return index
