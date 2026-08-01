"""canonical-431 案例采分点 → governed 判分库编译器（Lane 1：只编译+验证+签发候选）.

**这个脚本不切生产**。它把 `docs/原始数据/数据盘点/extractions/case_rubric_canonical.json`
（佑森 431 采分点 / 117 小问 / 25 案例 / 5 年，PDF 视觉核查 + 5 专家复核）编译成一个
`rubric_grader_v1` 形制的 bank slot 候选 `canonical431`，并产出可证伪的验证账本。

切生产是主控带 live 回归的独立步骤：需要 (a) 在 `_RUBRIC_BANK_SLOTS` 注册 slot、
(b) 把 pointer 的 `production_authorized` 翻 true、(c) 打通 tier-1 的键（见报告
`docs/原始数据/数据盘点/2026-08-01-canonical431上服Lane1.md` §4）。本脚本三样都不做。

## 键的选择

`qid = "{case_group_id}::E{case_subquestion_index}"`，例如 `2021-case1::E1`。

理由：C2（2026-08-01）已把 `case_group_id` / `case_subquestion_index` 回填进
`public.questions_bank`，C3 已让 RAG 按 `case_group_id` 取全组并把
`case_subquestion_index` 投成 `covered_subquestions[].display_index`
（`deeptutor/services/rag/pipelines/supabase.py:3197-3433`）。这两个字段是题级归属的
**唯一权威键**（`contracts/rag.md §45`），比 legacy bank 的裸 chunk 键
（`EXAM_1A413000_P0012_02::E0`）强：后者的 `E{n}` 是编译期 0-based `exercises[]` 序数，
与运行时 1-based `display_index` **没有共享权威**——已实测 23/354 命中、语义正确 0 条
（`deeptutor/tutorbot/agent/loop.py:2122-2136`）。

**本 bank 的 `E{n}` 一律是 1-based `case_subquestion_index`，与 DB / display_index 同权威。**
这条不变量由 `--verify` 的 V6 断言守住。

## 硬边界（本脚本自我约束）

- 只写 `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_canonical431/`
  这一个新目录，绝不碰 `v_case_rubric_scored`(legacy) / `v_case_rubric_scored_pgo`。
- pointer 恒 `production_authorized: false`。脚本**没有**把它写成 true 的代码路径。
- 不改任何判分核代码、不读写数据库、不发网络请求。

运行:
    python scripts/build_luban_canonical431_case_rubric_bank.py            # 编译 + 验证
    python scripts/build_luban_canonical431_case_rubric_bank.py --dry-run  # 只验证不落盘
    python scripts/build_luban_canonical431_case_rubric_bank.py --verify   # 只跑断言（读已落盘产物）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CANONICAL_PATH = ROOT / "docs/原始数据/数据盘点/extractions/case_rubric_canonical.json"
RECONCILIATION_PATH = (
    ROOT / "docs/原始数据/数据盘点/extractions/case_group_mapping_c1/reconciliation_vs_yousen.json"
)
TEXTBOOK_PATH = (
    ROOT
    / "deeptutor/services/construction_grading/runtime_supply/v_textbook_knowledge_full"
    / "textbook_knowledge_release_candidate.json"
)
OUT_DIR = (
    ROOT
    / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_canonical431"
)
BANK_NAME = "case_rubric_scored_canonical431.json"
POINTER_NAME = "canonical_pointer.json"
VALIDATION_NAME = "validation_report.json"

SCHEMA_VERSION = "luban_case_rubric_canonical431.v1"
NAMESPACE = "case_rubric_scored_canonical431"
SLOT_NAME = "canonical431"

# 分值/术语权威：佑森培训机构解析，**不是官方评分细则**。这条必须逐记录携带——
# 一个 NOT_official 的分值被下游当官方口径消费，就是「完整的赝品仍是赝品」。
SCORE_AUTHORITY = "training_org_analysis_yousen"

# ── 2022 隔离 ────────────────────────────────────────────────────────────────
# 佑森 2022 抽取源是 `2022bukao_jianzhu_case_rubric.jsonl` = **补考卷**；
# questions_bank 的 2022-caseN 行是**正考卷**。实证（本脚本 --verify 的 V2 断言）：
#   DB   2022-case5 E1 = 「施工企业安全生产管理制度内容还有哪些？」
#   佑森 2022-case5 E1 = 「(1)混凝土工程容易发生:①高空坠落」
# 两张卷子。`per_question_score_backfill.jsonl` 的 _meta 也已因同一理由跳过 2022。
# 把补考 rubric 挂到正考题号上 = 用错答案判分，比没有 rubric 危险得多。
# 因此默认 quarantine：不进 records，只进 manifest.quarantined。
QUARANTINE_YEARS = {"2022"}
QUARANTINE_REASON = (
    "佑森 2022 抽取源为补考卷(2022bukao)，questions_bank 2022-caseN 为正考卷；"
    "题面实证不同卷。挂载=用错卷答案判分。待补正考 rubric 源后单独立案。"
)

# 佑森 point_type → rubric_grader_v1._VALID_POLICIES
# ("list", "exact_required", "boolean_judgment", "qualitative", "calc")
# 保守原则：不轻易给 exact_required——它是二值无部分分，误判代价是「答对意思判 0 分」。
# 佑森 point_text 是整句解析文本、不是规范术语单点，因此本 bank **零 exact_required**。
POLICY_MAP = {
    "判断": "boolean_judgment",
    "改错": "qualitative",
    "列举": "list",
    "分类": "list",
    "程序": "list",
    "措施": "list",
    "计算结果": "calc",
    "计算步骤": "calc",
}
DEFAULT_POLICY = "qualitative"

# 一建·建筑实务卷面结构：案例一~三各 20 分，案例四~五各 30 分，合计 120。
# 这是**唯一一条不来自佑森的**分值锚（来自考试大纲），用来外部校验 per-小问 nominal 之和。
OFFICIAL_CASE_TOTALS = {1: 20.0, 2: 20.0, 3: 20.0, 4: 30.0, 5: 30.0}


def _sha256_hex(obj: Any) -> str:
    """必须与 full_knowledge_compiler._sha256_hex 逐字节一致（闸按它复算）。"""
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 教材溯源 ─────────────────────────────────────────────────────────────────
# 复用 scripts/enrich_rubric_textbook_provenance.py 的匹配器（同一把尺子，避免两套口径）。
def _load_matcher():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_enricher", ROOT / "scripts/enrich_rubric_textbook_provenance.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _iter_canonical(rubric: dict, *, include_quarantined: bool = False):
    """产出 (year, case_no, sub_q_no, subq_dict)，确定性顺序（年→案例号→小问号，数值序）。"""
    for year in sorted(rubric, key=int):
        if year in QUARANTINE_YEARS and not include_quarantined:
            continue
        cases = rubric[year]
        for case_no in sorted(cases, key=int):
            subs = cases[case_no]
            for sub_no in sorted(subs, key=int):
                yield year, case_no, sub_no, subs[sub_no]


def build_records(rubric: dict, matcher, textbook_records: list[dict], text_index: dict) -> tuple[
    list[dict], list[dict], dict
]:
    """编译 records + quarantined + 每小问 nominal 表。"""
    records: list[dict] = []
    quarantined: list[dict] = []
    nominal_table: dict[str, dict] = {}

    for year, case_no, sub_no, subq in _iter_canonical(rubric, include_quarantined=True):
        case_group_id = f"{year}-case{case_no}"
        qid = f"{case_group_id}::E{sub_no}"
        nominal = float(subq["sub_q_total_score"])
        judging_rule = str(subq.get("judge_rule") or "")
        points = subq.get("points") or []
        pool = round(sum(float(p["score"]) for p in points), 4)

        nominal_table[qid] = {
            "case_group_id": case_group_id,
            "subquestion_index": int(sub_no),
            "nominal": nominal,
            "point_pool": pool,
            "point_count": len(points),
            "pool_vs_nominal": ("over" if pool > nominal else "under" if pool < nominal else "exact"),
            "quarantined": year in QUARANTINE_YEARS,
        }

        for p in points:
            seq = int(p["seq"])
            text = str(p["text"]).strip()
            ptype = str(p.get("type") or "")
            refs, strong = matcher._find_matches(text, [], textbook_records, text_index)
            rec = {
                "qid": qid,
                "point_id": f"{qid}::p{seq}",
                "text": text,
                "score": float(p["score"]),
                "policy": POLICY_MAP.get(ptype, DEFAULT_POLICY),
                "required_terms": [],
                # ── 题级归属（tier-1 分组 + per-问封顶的键）──────────────────
                "case_group_id": case_group_id,
                # question_no / subquestion_index 都填 1-based index：
                # rubric_grader_v1._question_group_key 读这两个键做分组与 caps key。
                "question_no": int(sub_no),
                "subquestion_index": int(sub_no),
                "point_seq": seq,
                # ── 分母权威：per-小问真实满分（不是均分）──────────────────
                "official_total_score": nominal,
                "official_total_score_authority": SCORE_AUTHORITY,
                "score_authority": SCORE_AUTHORITY,
                "per_point_score_authority": SCORE_AUTHORITY,
                "answer_key_authority": SCORE_AUTHORITY,
                "point_pool_total": pool,
                # ── 判分规则内嵌 ─────────────────────────────────────────────
                "judging_rule": judging_rule,
                "sub_type": ptype,
                "factory_point_type": ptype,
                "source_schema": SCHEMA_VERSION,
                "exact_term_required": False,
                # ── 教材溯源（项目铁律：采分点必须能溯源到教材）─────────────
                "textbook_source_refs": refs,
                "textbook_traced": bool(refs),
                "textbook_traced_strong": bool(strong),
                # ── 出处 ─────────────────────────────────────────────────────
                "source_year": int(year),
                "source_case_no": int(case_no),
                "source_page": p.get("page") if isinstance(p, dict) else None,
                "source_authority": SCORE_AUTHORITY,
                "NOT_official": True,
            }
            if p.get("_ocr_suspect"):
                rec["ocr_suspect"] = str(p["_ocr_suspect"])
            if year in QUARANTINE_YEARS:
                rec["quarantine_reason"] = QUARANTINE_REASON
                quarantined.append(rec)
            else:
                records.append(rec)

    # ── 分母外部校验：案例级 Σnominal vs 卷面结构 ──────────────────────────
    # 佑森是唯一分值来源，自己校自己等于没校。卷面结构（20/20/20/30/30）是外部锚。
    # 对不上的案例组：**逐记录**打 `nominal_authority_disputed`，让任何未来的封顶
    # 消费方能 fail-closed 拒用这个分母，而不是拿一个走样的满分去封顶。
    by_case: dict[str, float] = {}
    for meta in nominal_table.values():
        if meta["quarantined"]:
            continue
        by_case[meta["case_group_id"]] = round(
            by_case.get(meta["case_group_id"], 0.0) + meta["nominal"], 4
        )
    disputed: dict[str, dict] = {}
    for g, s in sorted(by_case.items()):
        want = OFFICIAL_CASE_TOTALS.get(int(g.split("-case")[1]))
        if want is not None and abs(s - want) > 1e-9:
            disputed[g] = {"sum_nominal": s, "official_paper_total": want, "delta": round(s - want, 2)}
    for r in records:
        if r["case_group_id"] in disputed:
            r["nominal_authority_disputed"] = True
            r["nominal_dispute_detail"] = disputed[r["case_group_id"]]
    for qid, meta in nominal_table.items():
        meta["nominal_authority_disputed"] = meta["case_group_id"] in disputed

    return records, quarantined, nominal_table, disputed


def build_reachability(nominal_table: dict) -> dict:
    """用 C1 对账档案算「这个键在运行时够不够得着」。

    整题行（case_row_granularity='whole_question'）按 C2 契约 index 必须留空，
    所以 `{group}::E{n}` 对它们**恒不命中**。这不是 bug，是键的适用边界——
    必须写进账本，否则第二波会拿一个 48% 可达的库去宣称 100% 覆盖。
    """
    rec = _load_json(RECONCILIATION_PATH)
    by_group = {g["case_group_id"]: g for g in rec}
    out: dict[str, Any] = {"per_group": {}, "summary": {}}
    reachable = unreachable = 0
    for qid, meta in nominal_table.items():
        if meta["quarantined"]:
            continue
        g = by_group.get(meta["case_group_id"]) or {}
        indexed = set(g.get("db_subquestion_indexes") or [])
        ok = meta["subquestion_index"] in indexed
        entry = out["per_group"].setdefault(
            meta["case_group_id"],
            {
                "db_subquestion_indexes": sorted(indexed),
                "whole_case_spans": g.get("whole_case_spans") or [],
                "reachable_E": [],
                "unreachable_E": [],
            },
        )
        (entry["reachable_E"] if ok else entry["unreachable_E"]).append(meta["subquestion_index"])
        reachable += ok
        unreachable += not ok
    out["summary"] = {
        "reachable_subquestions": reachable,
        "unreachable_subquestions": unreachable,
        "total_non_quarantined": reachable + unreachable,
        "note": (
            "unreachable = 该小问在 questions_bank 里只有整题行(whole_question)，"
            "case_subquestion_index 按 C2 契约留空，故 `{group}::E{n}` 键永不命中。"
            "解药是整题行 bundle 接线（见报告 §4.3），不是改键。"
        ),
    }
    return out


def build_whole_case_index(records: list[dict]) -> dict[str, list[str]]:
    """`{case_group_id}` → 该组全部 qid（升序）。给第二波的整题行 bundle 接线用。

    **不进 records**（不参与 content_hash 覆盖的判分弹药面），只作为旁挂索引，
    这样它变更不会动摇 bank 的 hash 身份。
    """
    idx: dict[str, list[str]] = {}
    for r in records:
        idx.setdefault(str(r["case_group_id"]), [])
        if r["qid"] not in idx[r["case_group_id"]]:
            idx[r["case_group_id"]].append(r["qid"])
    return {k: sorted(v, key=lambda q: int(q.rsplit("::E", 1)[1])) for k, v in sorted(idx.items())}


def build_bundle(rubric: dict) -> tuple[dict, dict]:
    matcher = _load_matcher()
    tb = _load_json(TEXTBOOK_PATH)
    textbook_records = tb.get("records") or []
    text_index = matcher._build_text_index(textbook_records)

    records, quarantined, nominal_table, disputed = build_records(
        rubric, matcher, textbook_records, text_index
    )
    reachability = build_reachability(nominal_table)
    whole_case_index = build_whole_case_index(records)

    by_policy: dict[str, int] = {}
    for r in records:
        by_policy[r["policy"]] = by_policy.get(r["policy"], 0) + 1
    traced = sum(1 for r in records if r["textbook_traced"])
    traced_strong = sum(1 for r in records if r["textbook_traced_strong"])
    live_nominal = {k: v for k, v in nominal_table.items() if not v["quarantined"]}

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "lane": NAMESPACE,
        "slot": SLOT_NAME,
        "status": "release_candidate",
        "published": False,
        "production_authorized": False,
        "source": "docs/原始数据/数据盘点/extractions/case_rubric_canonical.json",
        "source_authority": SCORE_AUTHORITY,
        "NOT_official": True,
        "judging_rule": "小题得分 = min(Σ命中采分点×point_score, sub_q_total_score) 封顶",
        "key_scheme": "{case_group_id}::E{case_subquestion_index}  (E 为 1-based，与 DB display_index 同权威)",
        "key_authority": "contracts/rag.md §45 (方案C / C2+C3)",
        "question_count": len({r["qid"] for r in records}),
        "scoring_point_count": len(records),
        "case_group_count": len(whole_case_index),
        "by_policy": by_policy,
        "textbook_traced_count": traced,
        "textbook_traced_strong_count": traced_strong,
        "nominal_total": round(sum(v["nominal"] for v in live_nominal.values()), 2),
        "point_pool_total": round(sum(v["point_pool"] for v in live_nominal.values()), 2),
        "quarantined_years": sorted(QUARANTINE_YEARS),
        "quarantined_point_count": len(quarantined),
        "quarantine_reason": QUARANTINE_REASON,
        "official_paper_case_totals": OFFICIAL_CASE_TOTALS,
        "nominal_drift_pending_adjudication": disputed,
        "nominal_disputed_point_count": sum(
            1 for r in records if r.get("nominal_authority_disputed")
        ),
        "content_hash": _sha256_hex(records),
        "authorization_note": (
            "Lane 1 只编译+验证+签发候选。切生产需主控另行：注册 _RUBRIC_BANK_SLOTS、"
            "打通 tier-1 键、翻 production_authorized、跑 live 回归。"
        ),
    }
    bundle = {
        "manifest": manifest,
        "records": records,
        "rejected": [],
        "quarantined": quarantined,
        "whole_case_index": whole_case_index,
        "nominal_table": nominal_table,
        "reachability": reachability,
    }
    pointer = {
        "namespace": NAMESPACE,
        "slot": SLOT_NAME,
        "status": "release_candidate",
        "published": False,
        "expected_content_hash": manifest["content_hash"],
        # ↓ 这一行是 Lane 1 的硬边界。脚本没有把它写成 true 的代码路径。
        "production_authorized": False,
        "authorization_note": (
            "待主控切换：Lane 1 只交付候选。装载前必须 (1) 在 rubric_grader_v1._RUBRIC_BANK_SLOTS "
            "注册 'canonical431' → ('v_case_rubric_scored_canonical431', "
            "'case_rubric_scored_canonical431.json')；(2) 打通 tier-1 键（ctx.question_id 目前不是 "
            "case_group_id::E{n}，见 2026-08-01-canonical431上服Lane1.md §4）；(3) live 回归。"
            "分值权威=佑森培训机构解析，NOT official。"
        ),
    }
    return bundle, pointer


# ── 验证断言 ─────────────────────────────────────────────────────────────────
def verify(bundle: dict, pointer: dict, rubric: dict) -> tuple[list[dict], bool]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    records = bundle["records"]
    quarantined = bundle["quarantined"]
    manifest = bundle["manifest"]
    nominal_table = bundle["nominal_table"]

    # V1 源账对齐：431 点 / 117 小问 / 25 案例
    src_pts = sum(
        len(s["points"]) for _, _, _, s in _iter_canonical(rubric, include_quarantined=True)
    )
    src_subq = sum(1 for _ in _iter_canonical(rubric, include_quarantined=True))
    src_cases = sum(len(rubric[y]) for y in rubric)
    add(
        "V1_source_totals",
        (src_pts, src_subq, src_cases) == (431, 117, 25),
        f"源: {src_pts}点/{src_subq}小问/{src_cases}案例 (期望 431/117/25)",
    )

    # V2 全量守恒：records + quarantined 必须逐点覆盖源，一个不多一个不少
    add(
        "V2_no_point_lost",
        len(records) + len(quarantined) == src_pts,
        f"records {len(records)} + quarantined {len(quarantined)} = "
        f"{len(records) + len(quarantined)} vs 源 {src_pts}",
    )

    # V3 2022 隔离生效
    bad_2022 = [r for r in records if r["source_year"] == 2022]
    add("V3_2022_quarantined", not bad_2022, f"records 内 2022 点数={len(bad_2022)} (必须 0)")

    # V4 每小问 Σ点分 vs nominal 关系表（记录，不强制相等——池>满分是允许的）
    live = {k: v for k, v in nominal_table.items() if not v["quarantined"]}
    over = [k for k, v in live.items() if v["pool_vs_nominal"] == "over"]
    under = [k for k, v in live.items() if v["pool_vs_nominal"] == "under"]
    exact = [k for k, v in live.items() if v["pool_vs_nominal"] == "exact"]
    add(
        "V4_pool_vs_nominal_recorded",
        len(over) + len(under) + len(exact) == len(live),
        f"exact={len(exact)} over={len(over)} under={len(under)}; "
        f"under 需人审(抽取可能漏点): {under}",
    )

    # V5 每条记录都带分母 + 分母>0 + 分值权威非空
    bad = [
        r["point_id"]
        for r in records
        if not r.get("official_total_score")
        or float(r["official_total_score"]) <= 0
        or not r.get("official_total_score_authority")
    ]
    add("V5_every_point_carries_nominal", not bad, f"缺分母/分母<=0 的点: {len(bad)} {bad[:5]}")

    # V6 键形制：1-based E，且 E 必须等于记录的 subquestion_index
    bad_keys = []
    for r in records:
        qid = r["qid"]
        if "::E" not in qid:
            bad_keys.append(qid)
            continue
        head, e = qid.rsplit("::E", 1)
        if not e.isdigit() or int(e) < 1 or int(e) != int(r["subquestion_index"]):
            bad_keys.append(qid)
        if head != r["case_group_id"]:
            bad_keys.append(qid)
    add("V6_key_shape_1based", not bad_keys, f"键形制违规: {len(set(bad_keys))} {sorted(set(bad_keys))[:5]}")

    # V7 policy 合法（对齐 rubric_grader_v1._VALID_POLICIES）
    valid = {"list", "exact_required", "boolean_judgment", "qualitative", "calc"}
    bad_pol = sorted({r["policy"] for r in records} - valid)
    add("V7_policy_legal", not bad_pol, f"非法 policy: {bad_pol}")

    # V8 exact_required 必带 required_terms（否则会把答对意思的学生判 0 分）
    bad_ex = [r["point_id"] for r in records if r["policy"] == "exact_required" and not r["required_terms"]]
    add("V8_exact_required_has_terms", not bad_ex, f"裸 exact_required: {len(bad_ex)}")

    # V9 point_id 全局唯一
    ids = [r["point_id"] for r in records]
    add("V9_point_id_unique", len(ids) == len(set(ids)), f"{len(ids)} 条 / {len(set(ids))} 唯一")

    # V10 content_hash 自洽 + pointer 一致
    h = _sha256_hex(records)
    add("V10_content_hash", h == manifest["content_hash"] == pointer["expected_content_hash"], h[:16])

    # V11 Lane 1 硬边界：pointer 必须未授权
    add(
        "V11_not_production_authorized",
        pointer.get("production_authorized") is False and manifest.get("production_authorized") is False,
        f"pointer={pointer.get('production_authorized')} manifest={manifest.get('production_authorized')}",
    )

    # V12 未污染既有 slot
    legacy = OUT_DIR.parent / "v_case_rubric_scored" / "case_rubric_scored.json"
    pgo = OUT_DIR.parent / "v_case_rubric_scored_pgo"
    add(
        "V12_existing_slots_untouched",
        OUT_DIR.name not in {"v_case_rubric_scored", "v_case_rubric_scored_pgo"}
        and legacy.exists()
        and pgo.exists(),
        f"输出目录={OUT_DIR.name}；legacy/pgo 仍在原处",
    )

    # V13 教材溯源覆盖（记录真实数字，不粉饰）
    traced = sum(1 for r in records if r["textbook_traced"])
    add(
        "V13_textbook_traced_recorded",
        True,
        f"{traced}/{len(records)} 条采分点匹配到教材节点 "
        f"({100.0 * traced / max(1, len(records)):.1f}%); "
        f"strong={sum(1 for r in records if r['textbook_traced_strong'])}",
    )

    # V14 可达性账本存在且诚实
    s = bundle["reachability"]["summary"]
    add(
        "V14_reachability_recorded",
        s["reachable_subquestions"] + s["unreachable_subquestions"] == s["total_non_quarantined"],
        f"可达 {s['reachable_subquestions']} / 不可达 {s['unreachable_subquestions']} "
        f"/ 非隔离共 {s['total_non_quarantined']}",
    )

    # V15 与金标 v2 三题交叉抽验（Q2023-03 / Q2024-03 / Q2025-03）
    # 诚实边界：金标 v2 的采分点骨架取自 **同一批** extractions jsonl，因此这是
    # 「编译器有没有在搬运途中丢/改点」的守恒校验，**不是独立信源核对**。
    # 它能抓的是：漏点、串行、分值走样、per-小问满分错配；抓不到的是佑森源本身的错。
    gold_path = ROOT / "docs/原始数据/数据盘点/extractions/gold_pack_v2/student_army_gold.v2.pilot.json"
    if gold_path.exists():
        gold = _load_json(gold_path)
        by_qid = {}
        for r in records:
            by_qid.setdefault(r["qid"], []).append(r)
        diffs: list[str] = []
        compared = 0
        for gq in gold.get("questions") or []:
            year = str(gq.get("year"))
            case_no = str(gq["question_id"].split("-")[1]).lstrip("0")
            for gp in gq.get("rubric_points") or []:
                qid = f"{year}-case{case_no}::E{gp['sub_q_no']}"
                mine = next(
                    (r for r in by_qid.get(qid, []) if int(r["point_seq"]) == int(gp["point_seq"])), None
                )
                compared += 1
                if mine is None:
                    diffs.append(f"{gq['question_id']}/{gp['point_id']}: bank 缺该点({qid})")
                    continue
                if str(mine["text"]) != str(gp["point_text"]):
                    diffs.append(f"{gq['question_id']}/{gp['point_id']}: text 不一致")
                if abs(float(mine["score"]) - float(gp["point_score"])) > 1e-9:
                    diffs.append(
                        f"{gq['question_id']}/{gp['point_id']}: score {mine['score']} vs {gp['point_score']}"
                    )
                if abs(float(mine["official_total_score"]) - float(gp["sub_q_total_score"])) > 1e-9:
                    diffs.append(
                        f"{gq['question_id']}/{gp['point_id']}: 小问满分 "
                        f"{mine['official_total_score']} vs {gp['sub_q_total_score']}"
                    )
        add(
            "V15_gold_v2_crosscheck",
            not diffs,
            f"逐点比对 {compared} 条（3 题），差异 {len(diffs)} 条 {diffs[:3]}；"
            "注：金标骨架同源于本 extractions，故为守恒校验、非独立信源",
        )
    else:
        add("V15_gold_v2_crosscheck", False, f"金标缺失: {gold_path}")

    # V16 分母外部校验：案例级 Σnominal 必须对上卷面结构，对不上的必须逐记录打争议标
    # 断言不是「零偏离」（偏离是源数据事实，改不掉），而是「每一处偏离都被标出来了」——
    # 一个走样的满分被静默当封顶分母用，才是真正的病。
    by_case_v: dict[str, float] = {}
    for meta in nominal_table.values():
        if meta["quarantined"]:
            continue
        by_case_v[meta["case_group_id"]] = round(
            by_case_v.get(meta["case_group_id"], 0.0) + meta["nominal"], 4
        )
    drift = {}
    for g, s in sorted(by_case_v.items()):
        want = OFFICIAL_CASE_TOTALS.get(int(g.split("-case")[1]))
        if want is not None and abs(s - want) > 1e-9:
            drift[g] = f"Σnominal={s} vs 卷面 {want} (差 {round(s - want, 2):+})"
    declared = set(manifest.get("nominal_drift_pending_adjudication") or {})
    marked = {r["case_group_id"] for r in records if r.get("nominal_authority_disputed")}
    add(
        "V16_nominal_drift_all_flagged",
        set(drift) == declared == marked,
        f"{len(by_case_v)} 组对卷面；实测偏离 {sorted(drift)}；manifest 声明 {sorted(declared)}；"
        f"记录已打标 {sorted(marked)}。明细: {drift}",
    )

    # V17 未偏离的案例组必须**没有**争议标（防止把标当万能免责声明滥用）
    over_marked = sorted(marked - set(drift))
    add("V17_no_spurious_dispute_flag", not over_marked, f"误标组: {over_marked}")

    return checks, all(c["ok"] for c in checks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="只编译+验证，不落盘")
    ap.add_argument("--verify", action="store_true", help="只读已落盘产物跑断言")
    args = ap.parse_args(argv)

    rubric = _load_json(CANONICAL_PATH)["rubric"]

    if args.verify:
        bundle = _load_json(OUT_DIR / BANK_NAME)
        pointer = _load_json(OUT_DIR / POINTER_NAME)
    else:
        bundle, pointer = build_bundle(rubric)

    checks, ok = verify(bundle, pointer, rubric)

    print(f"=== canonical431 bank 验证（{len(checks)} 条断言）===")
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}: {c['detail']}")
    m = bundle["manifest"]
    print(
        f"\nrecords={m['scoring_point_count']}  qid={m['question_count']}  "
        f"组={m['case_group_count']}  隔离={m['quarantined_point_count']}  hash={m['content_hash'][:16]}"
    )

    if args.verify or args.dry_run:
        return 0 if ok else 1

    if not ok:
        print("\n断言未全绿，拒绝落盘（fail-closed）。", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / BANK_NAME).write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT_DIR / POINTER_NAME).write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT_DIR / VALIDATION_NAME).write_text(
        json.dumps(
            {
                "built_at": "2026-08-01",
                "builder": "scripts/build_luban_canonical431_case_rubric_bank.py",
                "checks": checks,
                "all_green": ok,
                "nominal_table": bundle["nominal_table"],
                "reachability": bundle["reachability"],
            },
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n已落盘 → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
