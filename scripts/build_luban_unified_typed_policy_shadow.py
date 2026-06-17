#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_AGENTIC_PACKET = Path(
    "artifacts/luban_human_validation_v1/po_slice_20260603_heldout/agentic_grading_packet.json"
)
DEFAULT_TYPED_POLICY = Path(
    "artifacts/luban_typed_policy/po_slice_20260601_typed_policy_20260603/typed_policy_candidates.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260603_heldout_unified_typed_policy"
)

ARMS = [
    "qwen37_plus_thinking_primary",
    "deepseek_v4_flash_typed_policy_primary",
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _policy_index(typed_policy: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(policy.get("case_id")), str(policy.get("point_id"))): policy
        for policy in typed_policy.get("policies") or []
    }


def _compact_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_type": policy.get("policy_type"),
        "base_policy": policy.get("base_policy"),
        "policy_readiness": policy.get("policy_readiness"),
        "required_terms": policy.get("required_terms") or [],
        "list_spec": policy.get("list_spec"),
        "numeric_spec": policy.get("numeric_spec"),
        "figure_spec": policy.get("figure_spec"),
        "penalty_spec": policy.get("penalty_spec"),
        "evidence_policy": policy.get("evidence_policy"),
        "residual_signals": policy.get("residual_signals") or [],
        "safety_notes": policy.get("safety_notes") or [],
    }


def _inject_typed_policy(agentic_packet: dict[str, Any], typed_policy: dict[str, Any]) -> dict[str, Any]:
    indexed = _policy_index(typed_policy)
    packet = json.loads(json.dumps(agentic_packet, ensure_ascii=False))
    missing: list[dict[str, str]] = []
    for task in packet.get("tasks") or []:
        case_id = str(task.get("case_id") or "")
        for point in task.get("scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            policy = indexed.get((case_id, point_id))
            if policy:
                point["typed_policy"] = _compact_policy(policy)
            else:
                point["typed_policy"] = {
                    "policy_type": "high_risk_review",
                    "policy_readiness": "missing_policy",
                    "required_terms": [],
                    "safety_notes": ["typed_policy_missing_do_not_auto_certify"],
                }
                missing.append({"case_id": case_id, "point_id": point_id})
    packet["status"] = "awaiting_unified_typed_policy_predictions"
    packet["typed_policy_version_id"] = (typed_policy.get("summary") or {}).get("version_id", "")
    packet["typed_policy_schema_version"] = (typed_policy.get("summary") or {}).get("schema_version", "")
    packet["typed_policy_missing_points"] = missing
    packet["agentic_rule"] = (
        "Models grade with typed_policy as an explicit scoring protocol. Typed policy is not a production hard gate; "
        "required_terms are only strict for policy types that require exact terminology."
    )
    return packet


def _prompt(role: str, packet_name: str) -> str:
    model_hint = {
        "qwen37_plus_thinking_primary": "你是 Qwen3.7-plus thinking primary grader。",
        "deepseek_v4_flash_typed_policy_primary": "你是 DeepSeek-v4-flash typed-policy primary grader。",
    }[role]
    return f"""# 鲁班 Unified Typed-Policy Shadow - {role}

读取 `{packet_name}`。只根据题干、标准答案、采分点、typed_policy 和学生答案逐点阅卷。

{model_hint}

硬规则：
- 不使用外部资料，不接 RAG。
- 不读取 human label、ledger、artifact_first 预测或任何答案对照。
- hit/partial 必须引用学生答案原文 `evidence_span`；span 缺失或不在学生答案中必须退 miss 或 `unsupported=true`。
- `policy_type=exact_required`：必须遵守教材/规范术语边界；近义、大白话、口号不能自动给满。
- `policy_type=list_rule`：按标准术语命中 k/n 给分，分母以 typed_policy/list_rule 为准；不能用泛化语义替代列举项。
- `policy_type=calculation`：不能凭感觉给数值分；无法重算或过程分不明时标 high_risk。
- `policy_type=penalty_rule`：先判断罚则触发，再判断基础采分点。
- `policy_type=figure_label`：题图/官方答案是 authority；没有图证据时保守。
- `policy_type=high_risk_review`：不自动认证，保守输出并标 `high_risk=true`。
- 不要把 required_terms 当作全局 substring 硬门；只有 exact/list/penalty 等明确要求时才作为纪律边界。

输出 JSON：
```json
{{
  "slice_id": "...",
  "prediction_sets": [
    {{
      "arm": "{role}",
      "predictions": [
        {{
          "case_id": "Q...",
          "student_id": "S...",
          "point_id": "P...",
          "hit": "hit|partial|miss",
          "score": 0,
          "confidence": 0.0,
          "evidence_span": "学生答案原文片段；miss 可为空",
          "rationale": "简短说明",
          "policy_type": "exact_required|semantic_allowed|list_rule|calculation|figure_label|penalty_rule|high_risk_review",
          "disposition": "initial|high_risk",
          "high_risk": false,
          "unsupported": false
        }}
      ]
    }}
  ]
}}
```
"""


def _finding(packet: dict[str, Any], output_dir: Path) -> str:
    policy_counts: dict[str, int] = {}
    point_rows = 0
    for task in packet.get("tasks") or []:
        for point in task.get("scoring_points") or []:
            point_rows += 1
            policy_type = str((point.get("typed_policy") or {}).get("policy_type") or "missing")
            policy_counts[policy_type] = policy_counts.get(policy_type, 0) + 1
    lines = [
        "# FINDING: Unified Typed-Policy Shadow Packet",
        "",
        "> Directional/shadow. This packet unifies model prompts around typed_policy; it does not approve runtime use.",
        "",
        "## Scope",
        "",
        f"- slice_id: `{packet.get('slice_id')}`",
        f"- tasks: `{len(packet.get('tasks') or [])}`",
        f"- point_rows: `{point_rows}`",
        f"- typed_policy_version_id: `{packet.get('typed_policy_version_id')}`",
        f"- missing_policy_points: `{len(packet.get('typed_policy_missing_points') or [])}`",
        "",
        "## Policy Distribution",
        "",
    ]
    for key in sorted(policy_counts):
        lines.append(f"- {key}: `{policy_counts[key]}`")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `unified_typed_policy_packet.json`",
            "- `unified_predictions_template.json`",
            "- `qwen37_plus_thinking_primary_prompt.md`",
            "- `deepseek_v4_flash_typed_policy_primary_prompt.md`",
            "",
            "## Next Gate",
            "",
            "Fill predictions, apply span guard if needed, then score only after human labels are filled.",
            f"Output directory: `{output_dir}`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_unified_typed_policy_shadow(
    *,
    agentic_packet_path: Path,
    typed_policy_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    agentic_packet = _read_json(agentic_packet_path)
    typed_policy = _read_json(typed_policy_path)
    packet = _inject_typed_policy(agentic_packet, typed_policy)
    output_dir.mkdir(parents=True, exist_ok=True)

    packet_path = output_dir / "unified_typed_policy_packet.json"
    template_path = output_dir / "unified_predictions_template.json"
    qwen_prompt_path = output_dir / "qwen37_plus_thinking_primary_prompt.md"
    deepseek_prompt_path = output_dir / "deepseek_v4_flash_typed_policy_primary_prompt.md"
    finding_path = output_dir / "FINDING_unified_typed_policy_shadow.md"

    _write_json(packet_path, packet)
    _write_json(
        template_path,
        {
            "slice_id": packet.get("slice_id"),
            "prediction_sets": [{"arm": arm, "predictions": []} for arm in ARMS],
        },
    )
    qwen_prompt_path.write_text(_prompt("qwen37_plus_thinking_primary", packet_path.name), encoding="utf-8")
    deepseek_prompt_path.write_text(
        _prompt("deepseek_v4_flash_typed_policy_primary", packet_path.name),
        encoding="utf-8",
    )
    finding_path.write_text(_finding(packet, output_dir), encoding="utf-8")
    return {
        "packet": packet_path,
        "template": template_path,
        "qwen_prompt": qwen_prompt_path,
        "deepseek_prompt": deepseek_prompt_path,
        "finding": finding_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a unified typed-policy shadow packet.")
    parser.add_argument("--agentic-packet", default=str(DEFAULT_AGENTIC_PACKET))
    parser.add_argument("--typed-policy", default=str(DEFAULT_TYPED_POLICY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    paths = build_unified_typed_policy_shadow(
        agentic_packet_path=Path(args.agentic_packet),
        typed_policy_path=Path(args.typed_policy),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
