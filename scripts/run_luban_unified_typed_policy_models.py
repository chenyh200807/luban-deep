#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PACKET = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_typed_policy_packet.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy/unified_predictions_template.json"
)

ARMS = {
    "qwen": {
        "arm": "qwen37_plus_thinking_primary",
        "provider": "dashscope",
        "model": "qwen3.7-plus",
    },
    "deepseek": {
        "arm": "deepseek_v4_flash_typed_policy_primary",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
    },
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _env_value(name: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'").split(",")[0].strip()
    return ""


def _client(provider: str):
    from openai import OpenAI

    if provider == "dashscope":
        return OpenAI(
            api_key=_env_value("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    if provider == "deepseek":
        return OpenAI(
            api_key=_env_value("DEEPSEEK_API_KEY"),
            base_url=_env_value("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1",
        )
    raise ValueError(f"unsupported provider: {provider}")


def _task_context(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": task.get("case_id"),
        "student_id": task.get("student_id"),
        "official_answer": task.get("official_answer") or "",
        "official_analysis": task.get("official_analysis") or "",
        "penalty_rule": task.get("penalty_rule") or "",
        "scoring_points": task.get("scoring_points") or [],
        "student_answer": task.get("student_answer") or "",
    }


def build_prompt(task: dict[str, Any], *, arm: str) -> str:
    role = {
        "qwen37_plus_thinking_primary": "你是 Qwen3.7-plus thinking primary grader。",
        "deepseek_v4_flash_typed_policy_primary": "你是 DeepSeek-v4-flash typed-policy primary grader。",
    }.get(arm, "你是鲁班一级建造师《建筑实务》案例阅卷主阅卷员。")
    return (
        "# 鲁班 Unified Typed-Policy Shadow Grading\n\n"
        f"{role}\n\n"
        "只根据题干、标准答案、采分点、typed_policy 和学生答案逐点阅卷。\n"
        "硬规则：\n"
        "- 不使用外部资料，不接 RAG。\n"
        "- 不读取 human label、ledger、artifact_first 预测或任何答案对照。\n"
        "- hit/partial 必须引用学生答案原文 evidence_span；span 缺失或不在学生答案中必须退 miss 或 unsupported=true。\n"
        "- policy_type=exact_required 时，近义、大白话、口号不能自动给满。\n"
        "- policy_type=list_rule 时，按标准术语命中 k/n 给分，不能用泛化语义替代列举项。\n"
        "- policy_type=calculation 时，不能凭感觉给数值分；无法重算或过程分不明时标 high_risk。\n"
        "- policy_type=penalty_rule 时，先判断罚则触发，再判断基础采分点。\n"
        "- 不要把 required_terms 当作全局 substring 硬门；只有 exact/list/penalty 等明确要求时才作为纪律边界。\n\n"
        "只输出一个 JSON 数组，无解释、无代码围栏。每点一个对象，字段："
        '{"point_id","hit"(hit|partial|miss),"score","confidence","evidence_span","rationale",'
        '"policy_type","disposition","high_risk","unsupported"}\n\n'
        "任务(JSON):\n"
        + json.dumps(_task_context(task), ensure_ascii=False)
    )


def parse_prediction_array(text: str) -> list[dict[str, Any]]:
    body = text.strip()
    body = re.sub(r"^```(?:json)?", "", body).strip()
    body = re.sub(r"```$", "", body).strip()
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end < 0:
        return []
    snippet = body[start : end + 1]
    for candidate in (snippet, re.sub(r",(\s*[}\]])", r"\1", snippet)):
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            continue
    return []


def _call_model(client: Any, *, provider: str, model: str, prompt: str, retries: int = 2) -> str:
    extra_body = None
    # DashScope qwen3.7-plus thinking is the default when enable_thinking is not disabled.
    if provider == "dashscope":
        extra_body = None
    for attempt in range(retries + 1):
        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 4000,
            }
            if extra_body is not None:
                kwargs["extra_body"] = extra_body
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                print(f"call error: {str(exc)[:160]}", flush=True)
                return ""
            time.sleep(2)
    return ""


def _normalize_predictions(task: dict[str, Any], predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in predictions:
        item = dict(row)
        item["case_id"] = str(task.get("case_id"))
        item["student_id"] = str(task.get("student_id"))
        item.setdefault("unsupported", False)
        item.setdefault("high_risk", False)
        item.setdefault("disposition", "initial")
        normalized.append(item)
    return normalized


def _load_prediction_payload(output_path: Path, *, slice_id: str) -> dict[str, Any]:
    if output_path.exists():
        return _read_json(output_path)
    return {
        "slice_id": slice_id,
        "prediction_sets": [{"arm": spec["arm"], "predictions": []} for spec in ARMS.values()],
    }


def merge_predictions(*, output_path: Path, slice_id: str, arm: str, predictions: list[dict[str, Any]]) -> None:
    payload = _load_prediction_payload(output_path, slice_id=slice_id)
    sets = payload.setdefault("prediction_sets", [])
    for row in sets:
        if row.get("arm") == arm:
            row["predictions"] = predictions
            break
    else:
        sets.append({"arm": arm, "predictions": predictions})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _prediction_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("case_id")), str(row.get("student_id")))


def run_arm(
    *,
    packet_path: Path,
    output_path: Path,
    arm_alias: str,
    offset: int = 0,
    limit: int = 0,
) -> dict[str, Any]:
    packet = _read_json(packet_path)
    spec = ARMS[arm_alias]
    arm = spec["arm"]
    client = _client(spec["provider"])
    payload = _load_prediction_payload(output_path, slice_id=str(packet.get("slice_id")))
    existing = []
    for row in payload.get("prediction_sets") or []:
        if row.get("arm") == arm:
            existing = list(row.get("predictions") or [])
            break
    completed_tasks = {_prediction_key(row) for row in existing}
    tasks = list(packet.get("tasks") or [])[offset:]
    if limit:
        tasks = tasks[:limit]

    predictions = existing
    mismatches = []
    for task in tasks:
        task_key = (str(task.get("case_id")), str(task.get("student_id")))
        if task_key in completed_tasks:
            continue
        expected = len(task.get("scoring_points") or [])
        prompt = build_prompt(task, arm=arm)
        parsed = parse_prediction_array(
            _call_model(client, provider=spec["provider"], model=spec["model"], prompt=prompt)
        )
        if len(parsed) != expected:
            parsed = parse_prediction_array(
                _call_model(client, provider=spec["provider"], model=spec["model"], prompt=prompt)
            )
        normalized = _normalize_predictions(task, parsed)
        if len(normalized) != expected:
            mismatches.append(
                {
                    "task_id": task.get("task_id"),
                    "case_id": task.get("case_id"),
                    "student_id": task.get("student_id"),
                    "expected": expected,
                    "actual": len(normalized),
                }
            )
        predictions.extend(normalized)
        merge_predictions(output_path=output_path, slice_id=str(packet.get("slice_id")), arm=arm, predictions=predictions)
        print(
            f"{task.get('task_id')}: {arm} {len(normalized)}/{expected} "
            f"{'OK' if len(normalized) == expected else 'MISMATCH'}",
            flush=True,
        )

    summary = {
        "arm": arm,
        "prediction_count": len(predictions),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "output": str(output_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified typed-policy model predictions for Luban heldout slices.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--arm", choices=sorted(ARMS), required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    summary = run_arm(
        packet_path=Path(args.packet),
        output_path=Path(args.output),
        arm_alias=args.arm,
        offset=args.offset,
        limit=args.limit,
    )
    return 0 if summary["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
