#!/usr/bin/env python3
"""Run real deepseek-v4-flash point-level grading for the typed-policy shadow slice.

Fills ``deepseek_predictions_template.json`` with genuine model output for the
three arms (primary -> strict_reviewer -> dual_adjudicated), one task per call.

Design notes
------------
- Per-task calls keep each JSON response small and parseable; the 320KB packet is
  never fed whole.
- ``case_id``/``student_id``/``point_id`` are injected by this script from the
  packet, never trusted from model echo, so keys always align with the scorer.
- Nothing is fabricated: if the model omits a point after retries, it is recorded
  as ``missing`` and surfaced, not silently filled.

Usage
  python scripts/run_luban_deepseek_typed_policy_predictions.py \
    --artifact-dir artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env", override=False)

from deeptutor.services.llm import factory  # noqa: E402

ARMS = (
    ("deepseek_v4_flash_primary", "deepseek_primary_prompt.md"),
    ("deepseek_v4_flash_strict_reviewer", "deepseek_strict_reviewer_prompt.md"),
    ("deepseek_v4_flash_dual_adjudicated", "deepseek_dual_adjudicator_prompt.md"),
)

PER_POINT_FIELDS = (
    "hit",
    "score",
    "confidence",
    "evidence_span",
    "rationale",
    "policy_type",
    "disposition",
    "high_risk",
    "unsupported",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _task_packet(task: dict[str, Any]) -> dict[str, Any]:
    """Single-task view fed to the model (the per-task 'packet')."""
    return {
        "case_id": task.get("case_id"),
        "student_id": task.get("student_id"),
        "student_archetype": task.get("student_archetype"),
        "stem": task.get("stem"),
        "official_answer": task.get("official_answer"),
        "official_analysis": task.get("official_analysis"),
        "penalty_rule": task.get("penalty_rule"),
        "student_answer": task.get("student_answer"),
        "scoring_points": task.get("scoring_points") or [],
    }


def _output_contract(point_ids: list[str]) -> str:
    return (
        "本次只处理一个 task。仅输出一个 JSON 对象："
        '{"predictions": [ ... ]}，不要任何额外文字、不要 markdown 围栏。\n'
        f"必须为且仅为以下 point_id 各输出一条，顺序不限：{point_ids}\n"
        "每条字段：point_id, hit(hit|partial|miss), score(数值, 0..该点 max_score), "
        "confidence(0..1), evidence_span(学生答案原文片段; miss 可空), rationale, "
        "policy_type, disposition(agree|fixed_over_credit|fixed_under_credit|high_risk|initial), "
        "high_risk(bool), unsupported(bool)。\n"
        "不要输出 case_id / student_id（由程序补全）。"
    )


def _extract_json_obj(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a possibly fenced / prose-wrapped reply."""
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model reply")
    depth = 0
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : idx + 1])
    raise ValueError("unbalanced JSON object in model reply")


def _build_user_prompt(
    *,
    task: dict[str, Any],
    point_ids: list[str],
    prior: dict[str, list[dict[str, Any]]] | None,
) -> str:
    parts = [
        "## 单题 packet",
        "```json",
        json.dumps(_task_packet(task), ensure_ascii=False, indent=2),
        "```",
    ]
    for label, preds in (prior or {}).items():
        parts += [
            f"## 已有 {label} 对本题的逐点判断（供你复核/裁决，不是答案对照）",
            "```json",
            json.dumps(preds, ensure_ascii=False, indent=2),
            "```",
        ]
    parts += ["## 输出要求", _output_contract(point_ids)]
    return "\n".join(parts)


async def _grade_task(
    *,
    arm: str,
    system_prompt: str,
    task: dict[str, Any],
    prior: dict[str, list[dict[str, Any]]] | None,
    sem: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    points = task.get("scoring_points") or []
    point_ids = [str(p.get("point_id")) for p in points]
    max_by_id = {str(p.get("point_id")): float(p.get("max_score") or 0) for p in points}
    case_id = str(task.get("case_id"))
    student_id = str(task.get("student_id"))
    user_prompt = _build_user_prompt(task=task, point_ids=point_ids, prior=prior)

    async with sem:
        collected: dict[str, dict[str, Any]] = {}
        last_err = ""
        for attempt in range(3):
            extra = ""
            if attempt and (missing := [pid for pid in point_ids if pid not in collected]):
                extra = f"\n\n上一次缺少这些 point_id，请补齐且只输出这些：{missing}"
            try:
                reply = await factory.complete(
                    prompt=user_prompt + extra,
                    system_prompt=system_prompt,
                    temperature=0.0,
                    max_tokens=4096,
                )
                obj = _extract_json_obj(reply)
                for row in obj.get("predictions") or []:
                    pid = str(row.get("point_id") or "").strip()
                    if pid not in max_by_id or pid in collected:
                        continue
                    rec = {"case_id": case_id, "student_id": student_id, "point_id": pid}
                    for field in PER_POINT_FIELDS:
                        rec[field] = row.get(field)
                    collected[pid] = rec
            except Exception as exc:  # noqa: BLE001 - surfaced as last_err
                last_err = f"{type(exc).__name__}: {exc}"
            if all(pid in collected for pid in point_ids):
                break
        result = [collected[pid] for pid in point_ids if pid in collected]
        missing = [pid for pid in point_ids if pid not in collected]
        flag = f" MISSING={missing} ({last_err})" if missing else ""
        print(f"  [{arm}] {case_id}::{student_id} -> {len(result)}/{len(point_ids)} pts{flag}", flush=True)
        return result


async def run(*, artifact_dir: Path, concurrency: int) -> Path:
    packet_path = artifact_dir / "deepseek_typed_policy_packet.json"
    template_path = artifact_dir / "deepseek_predictions_template.json"
    packet = _read_json(packet_path)
    template = _read_json(template_path)
    tasks: list[dict[str, Any]] = packet.get("tasks") or []
    prompts = {arm: (artifact_dir / fname).read_text(encoding="utf-8") for arm, fname in ARMS}

    sem = asyncio.Semaphore(concurrency)
    by_arm: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for arm, _ in ARMS:
        print(f"== arm: {arm} ==", flush=True)
        results = await asyncio.gather(
            *(
                _grade_task(
                    arm=arm,
                    system_prompt=prompts[arm],
                    task=task,
                    prior=_prior_for(arm, task, by_arm),
                    sem=sem,
                )
                for task in tasks
            )
        )
        by_arm[arm] = {
            f"{t.get('case_id')}::{t.get('student_id')}": preds
            for t, preds in zip(tasks, results)
        }
        flat = [row for preds in by_arm[arm].values() for row in preds]
        for pset in template.get("prediction_sets") or []:
            if pset.get("arm") == arm:
                pset["predictions"] = flat
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   {arm}: {len(flat)} predictions written", flush=True)

    return template_path


def _prior_for(
    arm: str,
    task: dict[str, Any],
    by_arm: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, list[dict[str, Any]]] | None:
    key = f"{task.get('case_id')}::{task.get('student_id')}"
    if arm == "deepseek_v4_flash_strict_reviewer":
        primary = by_arm.get("deepseek_v4_flash_primary", {}).get(key, [])
        return {"deepseek_v4_flash_primary": primary}
    if arm == "deepseek_v4_flash_dual_adjudicated":
        return {
            "deepseek_v4_flash_primary": by_arm.get("deepseek_v4_flash_primary", {}).get(key, []),
            "deepseek_v4_flash_strict_reviewer": by_arm.get("deepseek_v4_flash_strict_reviewer", {}).get(key, []),
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    out = asyncio.run(run(artifact_dir=Path(args.artifact_dir), concurrency=args.concurrency))
    print(f"\nfilled: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
