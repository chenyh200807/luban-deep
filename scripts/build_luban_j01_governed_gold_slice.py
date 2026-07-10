#!/usr/bin/env python3
"""J01 governed-gold annotation harness — deterministic sampler + blind-packet generator.

阶段0 of the 判分收入闸 plan (docs/plan/评分引擎与金标工件/
2026-07-05-luban-grading-revenue-gate-reconciled-milestone-plan.md §阶段0):
build the *harness* educators use to hand-label ~150 per-scoring-point hit/miss
cells for the J01-anchored case-grading slice. This script produces BLIND review
packets + per-annotator templates + a frozen definitions/threshold file. It does
NOT produce gold (gold = human), does NOT touch production / grading authority /
writeback, and signs NOTHING as gold.

Data sources (honest):
  * Channel ① `v_case_rubric_scored` (runtime_supply) — authoritative scoring
    points + textbook provenance, but has NO student answers. Used here only to
    tag node-level coverage + (when real J01 qids are supplied) enrich a point's
    ``textbook_source_refs``.
  * Golden fixture `luban_case_grading_golden_v1.json` — the ONLY offline corpus
    that pairs (question, official_answer, gold_scoring_points, STUDENT ANSWERS,
    ledger). It is the cell corpus for the offline dry-run. Its scoring points are
    marked ``provenance_class = fixture_authored_candidate`` (NOT textbook-signed).

Blind rule: the packet a human sees carries question / official_answer /
ONE scoring point / student answer ONLY. The ledger and any model prediction stay
in the internal manifest, never in the blind packet.

Cell = (student_answer × scoring_point). Sampler is deterministic (fixed seed):
priority = penalty(+3) + boundary(+2) + list_rule(+2) + open_world(+1); ties broken
by sha256(seed|cell_key). Re-running with the same seed yields the same slice.

Offline, re-runnable, no network. `production_write_count == 0`.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_FIXTURE = PROJECT_ROOT / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_CHANNEL1_BANK = (
    PROJECT_ROOT
    / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "artifacts/luban_governed_gold"
DEFAULT_SEED = "20260705"
DEFAULT_TARGET = 150

# Frozen BEFORE any labeling (eval-design: definitions/thresholds first, no retrofit).
FROZEN_DEFINITIONS: dict[str, Any] = {
    "hit_taxonomy": {
        "hit": "学生答案写出该采分点的教材/官方术语原文(踩字口径);近义、口号、大白话不算。",
        "partial": "写出该采分点要点的一部分,或术语近似但不完全踩字;按 list_rule 折算得分。",
        "miss": "未覆盖该采分点,或写错/写反。",
    },
    "score_rule": "human_score ∈ [0, max_score];hit 通常给满,partial 按 list_rule 折算,miss 给 0。",
    "evidence_span_rule": "每个 hit/partial 必须附 evidence_span:逐字来自 student_answer 的子串(命中依据)。miss 可空。",
    "irr_thresholds": {
        "point_kappa_gold_gate": 0.6,
        "point_kappa_warn": 0.4,
        "note": "点级 Cohen/Fleiss κ ≥ 0.6 方可入 gold;0.4–0.6 进仲裁;<0.4 该采分点重新定义。阈值参照 Landis-Koch,冻结在先,不 retrofit。",
    },
    "gold_authority_redline": (
        "gold = 人工逐采分点裁决。AI 面板只作候选/预标,不得单独入 gold。"
        "历史反例:run_luban_arbitration_gold_panel.py 产物 fleiss_kappa=-0.05(比随机差)—— "
        "AI 面板在此任务上不可当金标。单标注人 = directional,不得称 gold。"
    ),
    "blind_rule": "标注人只看 blind_packets.json;不得查阅 ledger / 任何模型预测 / 既有标签。",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _stable_tiebreak(seed: str, key: str) -> str:
    return hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()


def _channel1_coverage(bank_path: Path) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    """Return (covered node codes, {node_code: [textbook_source_refs]}) from channel ①.

    Node-level only — golden-fixture qids are NOT channel-① qids, so per-question
    rubric coverage is absent (every fixture cell is open-world at qid granularity).
    """
    if not bank_path.exists():
        return set(), {}
    bank = _read_json(bank_path)
    nodes: set[str] = set()
    refs_by_node: dict[str, list[dict[str, Any]]] = {}
    for rec in bank.get("records") or []:
        qid = str(rec.get("qid") or "")
        m = re.search(r"(1A\d{6})", qid)
        if m:
            nodes.add(m.group(1))
        for ref in rec.get("textbook_source_refs") or []:
            nc = ref.get("node_code")
            if nc:
                nodes.add(str(nc))
                refs_by_node.setdefault(str(nc), []).append(ref)
    return nodes, refs_by_node


@dataclass(frozen=True)
class Cell:
    cell_id: str
    case_id: str
    student_id: str
    point_id: str
    question_node: str
    max_score: float
    priority: int
    tags: tuple[str, ...]
    tiebreak: str


def _case_is_penalty(case: dict[str, Any]) -> bool:
    if "罚则" in str(case.get("case_id") or ""):
        return True
    pr = case.get("penalty_rule")
    return bool(pr) and str(pr).strip() != ""


def _point_tags(point: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if point.get("boundary") is True:
        tags.append("boundary_point")
    if str(point.get("list_rule") or "").strip():
        tags.append("list_rule_point")
    return tags


def _priority(tags: list[str]) -> int:
    weight = {"penalty_case": 3, "boundary_point": 2, "list_rule_point": 2, "open_world": 1}
    return sum(weight.get(t, 0) for t in tags)


def build_cell_universe(
    *,
    fixture: dict[str, Any],
    covered_nodes: set[str],
    case_ids: set[str] | None,
    seed: str,
) -> list[tuple[Cell, dict[str, Any]]]:
    """Return [(Cell, internal_payload)] for every (case × sample × scoring_point)."""
    universe: list[tuple[Cell, dict[str, Any]]] = []
    for case in fixture.get("cases") or []:
        case_id = str(case.get("case_id"))
        if case_ids is not None and case_id not in case_ids:
            continue
        node = str(case.get("question_node") or "")
        node_covered = node in covered_nodes
        penalty = _case_is_penalty(case)
        points = case.get("gold_scoring_points") or []
        samples = case.get("eval_samples") or []
        ledger_by_sample = {
            str(s.get("student_id")): {
                str(h.get("point_id")): str(h.get("hit") or "")
                for h in ((s.get("ground_truth_ledger") or {}).get("point_hits") or [])
            }
            for s in samples
        }
        for sample in samples:
            student_id = str(sample.get("student_id"))
            for point in points:
                point_id = str(point.get("point_id"))
                tags = _point_tags(point)
                # qid-granularity open-world: fixture questions have no channel-① compiled rubric.
                tags.append("open_world")
                if penalty:
                    tags.append("penalty_case")
                if node_covered:
                    tags.append("node_channel1_covered")
                cell_key = f"{case_id}|{student_id}|{point_id}"
                cell = Cell(
                    cell_id=hashlib.sha256(cell_key.encode("utf-8")).hexdigest()[:16],
                    case_id=case_id,
                    student_id=student_id,
                    point_id=point_id,
                    question_node=node,
                    max_score=float(point.get("max_score") or 0),
                    priority=_priority(tags),
                    tags=tuple(sorted(set(tags))),
                    tiebreak=_stable_tiebreak(seed, cell_key),
                )
                internal = {
                    "cell_key": cell_key,
                    "question_stem": case.get("stem"),
                    "official_answer": case.get("official_answer"),
                    "official_analysis": case.get("official_analysis"),
                    "penalty_rule": case.get("penalty_rule"),
                    "scoring_point": point,
                    "student_answer_text": sample.get("answer_text"),
                    "archetype": sample.get("archetype"),
                    # kept internal ONLY — annotators are blind to this:
                    "ledger_reference_hit": ledger_by_sample.get(student_id, {}).get(point_id, ""),
                }
                universe.append((cell, internal))
    return universe


def sample_cells(
    universe: list[tuple[Cell, dict[str, Any]]], *, target: int, max_per_case: int | None
) -> list[tuple[Cell, dict[str, Any]]]:
    ordered = sorted(universe, key=lambda ci: (-ci[0].priority, ci[0].tiebreak))
    if max_per_case is None:
        return ordered[:target]
    picked: list[tuple[Cell, dict[str, Any]]] = []
    per_case: dict[str, int] = {}
    overflow: list[tuple[Cell, dict[str, Any]]] = []
    for cell, internal in ordered:
        if per_case.get(cell.case_id, 0) < max_per_case:
            picked.append((cell, internal))
            per_case[cell.case_id] = per_case.get(cell.case_id, 0) + 1
        else:
            overflow.append((cell, internal))
        if len(picked) >= target:
            return picked
    for item in overflow:  # backfill deterministically if per-case caps starved the target
        if len(picked) >= target:
            break
        picked.append(item)
    return picked


def _blind_scoring_point(point: dict[str, Any], node: str, refs_by_node: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Scoring-point view the human judges against — official basis is the source_ref.

    Channel-① textbook refs for the point's node are attached as SUPPLEMENTARY context
    (clearly labeled), never fabricated as the fixture point's own provenance.
    """
    return {
        "point_id": point.get("point_id"),
        "label": point.get("label"),
        "max_score": point.get("max_score"),
        "official_basis": point.get("official_basis"),
        "boundary": point.get("boundary"),
        "list_rule": point.get("list_rule"),
        "source_authority": "golden_fixture.gold_scoring_points",
        "provenance_class": "fixture_authored_candidate",
        "source_ref": point.get("official_basis"),
        "supplementary_channel1_textbook_refs_by_node": refs_by_node.get(node, [])[:3],
    }


def _annotation_row(cell: Cell) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "case_id": cell.case_id,
        "student_id": cell.student_id,
        "point_id": cell.point_id,
        "max_score": cell.max_score,
        "human_hit": "",
        "human_score": "",
        "evidence_span": "",
        "human_error_codes": "",
        "human_note": "",
    }


def build_slice(
    *,
    fixture_path: Path,
    bank_path: Path,
    output_root: Path,
    seed: str,
    target: int,
    max_per_case: int | None,
    annotators: list[str],
    case_ids: set[str] | None,
) -> dict[str, Any]:
    fixture = _read_json(fixture_path)
    covered_nodes, refs_by_node = _channel1_coverage(bank_path)
    universe = build_cell_universe(
        fixture=fixture, covered_nodes=covered_nodes, case_ids=case_ids, seed=seed
    )
    selected = sample_cells(universe, target=target, max_per_case=max_per_case)

    cell_keys = [c.cell_id for c, _ in selected]
    slice_content_hash = _hash_payload(sorted(cell_keys))
    slice_id = f"j01-gg-{seed}-{slice_content_hash[:12]}"
    output_dir = output_root / f"j01_{seed}_{slice_content_hash[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)

    blind_packets: list[dict[str, Any]] = []
    manifest_cells: list[dict[str, Any]] = []
    for cell, internal in selected:
        blind_packets.append(
            {
                "cell_id": cell.cell_id,
                "case_id": cell.case_id,
                "student_id": cell.student_id,
                "point_id": cell.point_id,
                "question_node": cell.question_node,
                "question_stem": internal["question_stem"],
                "official_answer": internal["official_answer"],
                "scoring_point": _blind_scoring_point(
                    internal["scoring_point"], cell.question_node, refs_by_node
                ),
                "student_answer_text": internal["student_answer_text"],
                "blind_instruction": (
                    "只看本 cell 的题目/官方答案/采分点/学生答案。判定 human_hit ∈ "
                    "{hit,partial,miss},给 human_score,附 evidence_span(逐字来自学生答案)。"
                    "不得查阅 ledger 或任何模型预测。"
                ),
            }
        )
        manifest_cells.append(
            {
                "cell_id": cell.cell_id,
                "case_id": cell.case_id,
                "student_id": cell.student_id,
                "point_id": cell.point_id,
                "max_score": cell.max_score,
                "priority": cell.priority,
                "tags": list(cell.tags),
                "student_answer_text": internal["student_answer_text"],
                "scoring_point_label": internal["scoring_point"].get("label"),
                "source_ref": internal["scoring_point"].get("official_basis"),
                # internal only, for post-hoc analysis — NOT shown to annotators:
                "_ledger_reference_hit": internal["ledger_reference_hit"],
            }
        )

    source_hashes = {
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "channel1_bank_sha256": (
            hashlib.sha256(bank_path.read_bytes()).hexdigest() if bank_path.exists() else None
        ),
    }
    manifest = {
        "slice_id": slice_id,
        "schema_version": "luban_j01_governed_gold_slice.v1",
        "status": "awaiting_human_labels",
        "gold_authority": "human_per_scoring_point_adjudication",
        "sampler": {
            "seed": seed,
            "target": target,
            "max_per_case": max_per_case,
            "selected_count": len(selected),
            "universe_count": len(universe),
            "priority_weights": {"penalty_case": 3, "boundary_point": 2, "list_rule_point": 2, "open_world": 1},
            "case_ids_filter": sorted(case_ids) if case_ids else None,
        },
        "data_sources": {
            "cell_corpus": "golden_fixture.luban_case_grading_golden_v1 (offline; ONLY paired student-answer corpus)",
            "scoring_point_authority": "golden_fixture.gold_scoring_points (fixture_authored_candidate)",
            "channel1_bank": str(bank_path.relative_to(PROJECT_ROOT)) if bank_path.exists() else "MISSING",
            "channel1_role": "node-level coverage tag + supplementary textbook refs only; NO student answers here",
            "honest_gap": (
                "真 J01 governed gold 需真实 J01 学生答案 × 官方 J01 采分点。离线无该配对语料;"
                "本 slice 用 golden fixture 作 harness 载体与 dry-run 证据。真语料需教研/生产侧提供(本 agent 未做,禁碰生产)。"
            ),
        },
        "source_hashes": source_hashes,
        "annotators_expected": annotators,
        "frozen_definitions": FROZEN_DEFINITIONS,
        "slice_content_hash": slice_content_hash,
        "cells": manifest_cells,
    }

    (output_dir / "blind_packets.json").write_text(
        json.dumps(blind_packets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "slice_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "frozen_definitions.json").write_text(
        json.dumps(FROZEN_DEFINITIONS, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    template_paths: dict[str, str] = {}
    rows = [_annotation_row(cell) for cell, _ in selected]
    fieldnames = list(rows[0].keys()) if rows else []
    for annotator in annotators:
        csv_path = output_dir / f"annotation_template_{annotator}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        template_paths[annotator] = str(csv_path)

    (output_dir / "annotation_runbook.md").write_text(
        _runbook_markdown(slice_id=slice_id, output_dir=output_dir, annotators=annotators, manifest=manifest),
        encoding="utf-8",
    )

    return {
        "slice_id": slice_id,
        "output_dir": str(output_dir),
        "selected_count": len(selected),
        "universe_count": len(universe),
        "slice_content_hash": slice_content_hash,
        "annotation_templates": template_paths,
        "blind_packets": str(output_dir / "blind_packets.json"),
        "slice_manifest": str(output_dir / "slice_manifest.json"),
        "runbook": str(output_dir / "annotation_runbook.md"),
    }


def _runbook_markdown(*, slice_id: str, output_dir: Path, annotators: list[str], manifest: dict[str, Any]) -> str:
    thr = FROZEN_DEFINITIONS["irr_thresholds"]
    try:
        rel = output_dir.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = output_dir
    return f"""# 鲁班 J01 governed-gold 标注 runbook

Slice: `{slice_id}`  ·  cells: {manifest['sampler']['selected_count']}  ·  seed: `{manifest['sampler']['seed']}`

> 这是**教研人工逐采分点金标**的标注包。gold = 人。AI 面板只能当候选/预标,**不得单独入 gold**
> (历史反例 `fleiss_kappa=-0.05`,见 frozen_definitions.json)。单标注人 = directional,不得称 gold。

## 1. 领包

每位标注人各自领一份模板(互不可见对方结果),盲于 ledger 与任何模型预测:

{chr(10).join(f'- `{a}` → `{rel}/annotation_template_{a}.csv`' for a in annotators)}

只看 `{rel}/blind_packets.json`(题目/官方答案/采分点/学生答案)。

## 2. 标注协议(踩字口径)

每个 cell = 某学生答案 × 某采分点。逐 cell 填:

- `human_hit`: `hit` / `partial` / `miss`
  - hit = 写出采分点的教材/官方术语**原文**(踩字);近义、口号、大白话不算。
  - partial = 写出部分要点,或术语近似不完全踩字;按 `list_rule` 折算。
  - miss = 未覆盖 / 写错 / 写反。
- `human_score`: `0..max_score`;hit 通常满分,partial 按 `list_rule` 折算。
- `evidence_span`: **hit/partial 必填** —— 逐字来自学生答案的命中子串(判据)。miss 可空。
- `human_error_codes` / `human_note`: 可空;分歧或边界情况写原因。

## 3. 独立 + 交叉

至少 **2 名**标注人**独立**标同一批 cell,不得互相商量、不得看对方模板。这是真 IRR 的前提。

## 4. 回收 → IRR → 仲裁

```bash
python scripts/score_luban_j01_governed_gold.py \\
  --manifest {rel}/slice_manifest.json \\
  --labels {' '.join(f'{a}={rel}/annotation_template_{a}_filled.csv' for a in annotators)} \\
  --output {rel}/governed_gold_result.json
```

- 报 **Cohen κ(2 人)/ Fleiss κ(≥3 人)**,整体 + 每采分点(point_id)。
- 阈值(冻结在先,不 retrofit):点级 κ ≥ **{thr['point_kappa_gold_gate']}** 方可入 gold;
  **{thr['point_kappa_warn']}–{thr['point_kappa_gold_gate']}** 进仲裁;< **{thr['point_kappa_warn']}** 该采分点重新定义。
- 分歧 cell → `arbitration_queue.json`,由第三人/官方口径裁决后才入 gold,**不自动入**。
- `evidence_span` 非逐字子串 → `span_invalid`,该 cell 不入 gold。

## 5. 冻结

入 gold 的 cell → `governed_gold_frozen.json`,带 `content_hash` + `version_id`。
定义/阈值见 `frozen_definitions.json`,**标注前已冻结**。

## 6. 红线(eval-design)

- 标注人盲于 ledger / 预测(泄漏)。
- gold = 人,非 AI 面板(`fleiss_kappa=-0.05` 反例)。
- κ 报告可被第三方用同一 manifest + labels 复算(可证伪)。
- 单标注人 directional,不得称 gold。
- 抽样确定性:同 seed 复算同一 slice。
"""


def _parse_case_ids(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {c.strip() for c in raw.split(",") if c.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build J01 governed-gold blind annotation slice.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--channel1-bank", default=str(DEFAULT_CHANNEL1_BANK))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--max-per-case", type=int, default=None)
    parser.add_argument("--annotators", default="annotatorA,annotatorB")
    parser.add_argument("--case-ids", default=None, help="Comma-separated case_id filter (default: all cases).")
    args = parser.parse_args()

    result = build_slice(
        fixture_path=Path(args.fixture),
        bank_path=Path(args.channel1_bank),
        output_root=Path(args.output_root),
        seed=args.seed,
        target=args.target,
        max_per_case=args.max_per_case,
        annotators=[a.strip() for a in args.annotators.split(",") if a.strip()],
        case_ids=_parse_case_ids(args.case_ids),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
