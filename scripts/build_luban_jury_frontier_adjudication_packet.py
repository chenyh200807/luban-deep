#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_FRONTIER = Path(
    "artifacts/luban_agentic_grading_harness/multimodel_jury_gold_20260603/jury_frontier_points.json"
)
DEFAULT_PACKET = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_grading_packet.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/luban_agentic_grading_harness/multimodel_jury_gold_20260603/frontier_adjudication_packet"
)

FORBIDDEN_KEYS = {
    "ground_truth_ledger",
    "ledger",
    "ledger_point_rows",
    "human_hit",
    "human_score",
    "human_note",
    "blind_grade",
    "artifact_first",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id"))


def _task_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("case_id")), str(row.get("student_id"))


def _point_by_id(task: dict[str, Any], point_id: str) -> dict[str, Any]:
    for point in task.get("scoring_points") or []:
        if str(point.get("point_id")) == point_id:
            return {
                "point_id": str(point.get("point_id")),
                "label": point.get("label") or "",
                "max_score": point.get("max_score") or 0,
                "official_basis": point.get("official_basis") or "",
                "list_rule": point.get("list_rule") or "",
                "penalty_rule": point.get("penalty_rule"),
            }
    raise ValueError(f"point_id {point_id!r} not found in task {task.get('case_id')} {task.get('student_id')}")


def _safe_task_context(task: dict[str, Any], point_id: str) -> dict[str, Any]:
    return {
        "case_id": str(task.get("case_id")),
        "student_id": str(task.get("student_id")),
        "point_id": point_id,
        "question_node": task.get("question_node") or "",
        "stem": task.get("stem") or "",
        "official_answer": task.get("official_answer") or "",
        "student_answer": task.get("student_answer") or "",
        "scoring_point": _point_by_id(task, point_id),
    }


def _safe_model_judgments(frontier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    safe: dict[str, dict[str, Any]] = {}
    for arm, value in sorted((frontier.get("arms") or {}).items()):
        safe[str(arm)] = {
            "hit": value.get("hit") or "miss",
            "score": value.get("score") or 0,
            "supported": bool(value.get("supported")),
            "evidence_span": value.get("evidence_span") or "",
            "rationale": _blind_rationale(value.get("rationale") or ""),
        }
    return safe


def _blind_rationale(value: str) -> str:
    lowered = value.lower()
    if any(key.lower() in lowered for key in FORBIDDEN_KEYS):
        return "[redacted: non-blind rationale metadata]"
    return value


def _conflict_summary(frontier: dict[str, Any]) -> dict[str, Any]:
    signatures = sorted(
        {
            f"{value.get('hit') or 'miss'}/{value.get('score') or 0}"
            for value in (frontier.get("arms") or {}).values()
        }
    )
    return {
        "top_hit": frontier.get("top_hit") or "",
        "top_score": frontier.get("top_score") or 0,
        "top_vote_count": frontier.get("top_vote_count") or 0,
        "distinct_judgments": signatures,
        "unsupported_arms": list(frontier.get("unsupported_arms") or []),
    }


def _template_predictions(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "luban-frontier-adjudication-predictions.v0.1",
        "prediction_sets": [
            {
                "arm": "frontier_adjudicator",
                "predictions": [
                    {
                        "case_id": task["case_id"],
                        "student_id": task["student_id"],
                        "point_id": task["point_id"],
                        "hit": "",
                        "score": "",
                        "confidence": "",
                        "evidence_span": "",
                        "rationale": "",
                        "unsupported": False,
                        "adjudication_note": "",
                    }
                    for task in tasks
                ],
            }
        ],
    }


def _prompt(task_count: int) -> str:
    return f"""# 鲁班一建建筑实务 frontier 仲裁任务

这是离线 directional/shadow 仲裁，不是生产门。

你只处理 `{task_count}` 个多模型分歧采分点。每个任务都包含题干、官方答案、学生答案、采分点、以及 GPT/Opus/DeepSeek/Qwen 的分歧判定。

## 判分纪律

- 只根据题干、官方答案、采分点、学生答案和给出的证据判断。
- `hit` 只能填 `hit` / `partial` / `miss`。
- 给 `hit` 或 `partial` 时，必须填写学生答案中的 `evidence_span`；不得抄官方答案作为证据。
- 近义、大白话、口号是否给分，必须服从该采分点的 `label`、`official_basis`、`list_rule`、`penalty_rule`。
- 分歧模型的 rationale 只是参考，不是 authority。
- 吃不准时可填 `unsupported=true`，不要硬凑自动认证。

## 输出

按 `frontier_adjudication_template.json` 的 schema 填回，不要新增字段。
"""


def _finding(*, task_count: int, output_dir: Path, forbidden_hits: list[str]) -> str:
    lines = [
        "# FINDING: Luban Jury Frontier Adjudication Packet",
        "",
        "> Directional/shadow. This package calibrates only multi-model disagreement points; it is not production approval.",
        "",
        "## Summary",
        "",
        f"- frontier adjudication points: `{task_count}`",
        f"- output directory: `{output_dir}`",
        f"- forbidden leakage hits: `{len(forbidden_hits)}`",
        "",
        "## Interpretation",
        "",
        "- Full multi-model consensus is treated as high-confidence synthetic gold candidate evidence.",
        "- Frontier rows are the only rows that should receive expensive adversarial adjudication.",
        "- The packet intentionally excludes human labels, ledger labels, and artifact-first baseline outputs.",
        "",
    ]
    if forbidden_hits:
        lines.extend(["## Leakage Findings", ""])
        lines.extend(f"- `{hit}`" for hit in forbidden_hits)
        lines.append("")
    return "\n".join(lines)


def _leakage_hits(payload: Any) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False)
    return sorted(key for key in FORBIDDEN_KEYS if key in text)


def build_frontier_adjudication_packet(
    *,
    frontier_path: Path = DEFAULT_FRONTIER,
    source_packet_path: Path = DEFAULT_PACKET,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    frontier_rows = list(_read_json(frontier_path))
    source_packet = _read_json(source_packet_path)
    task_index = {_task_key(task): task for task in source_packet.get("tasks") or []}

    tasks: list[dict[str, Any]] = []
    missing_context: list[dict[str, str]] = []
    for frontier in frontier_rows:
        case_id, student_id, point_id = _key(frontier)
        task = task_index.get((case_id, student_id))
        if not task:
            missing_context.append({"case_id": case_id, "student_id": student_id, "point_id": point_id})
            continue
        enriched = _safe_task_context(task, point_id)
        enriched["model_judgments"] = _safe_model_judgments(frontier)
        enriched["conflict_summary"] = _conflict_summary(frontier)
        tasks.append(enriched)

    adjudication_packet = {
        "schema_version": "luban-frontier-adjudication-packet.v0.1",
        "slice_id": source_packet.get("slice_id") or "",
        "purpose": "Adjudicate only multi-model frontier points from the official-standard-anchored jury analysis.",
        "grading_guideline": source_packet.get("grading_guideline") or {},
        "adjudication_rule": "Use official-standard context plus student-answer evidence; model judgments are evidence to audit, not authority.",
        "tasks": tasks,
        "missing_context": missing_context,
    }
    forbidden_hits = _leakage_hits(adjudication_packet)
    if forbidden_hits:
        raise ValueError(f"frontier adjudication packet leaked forbidden keys: {', '.join(forbidden_hits)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "frontier_adjudication_packet.json", adjudication_packet)
    _write_json(output_dir / "frontier_adjudication_template.json", _template_predictions(tasks))
    (output_dir / "frontier_adjudication_prompt.md").write_text(_prompt(len(tasks)), encoding="utf-8")
    (output_dir / "FINDING_jury_frontier_adjudication_packet.md").write_text(
        _finding(task_count=len(tasks), output_dir=output_dir, forbidden_hits=forbidden_hits),
        encoding="utf-8",
    )
    result = {
        "output_dir": str(output_dir),
        "frontier_point_count": len(tasks),
        "missing_context_count": len(missing_context),
        "forbidden_leakage_hits": forbidden_hits,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a blind multi-model frontier adjudication packet for Luban grading.")
    parser.add_argument("--frontier", default=str(DEFAULT_FRONTIER))
    parser.add_argument("--source-packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    build_frontier_adjudication_packet(
        frontier_path=Path(args.frontier),
        source_packet_path=Path(args.source_packet),
        output_dir=Path(args.output_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
