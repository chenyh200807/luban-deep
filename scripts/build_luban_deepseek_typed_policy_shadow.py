#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_AGENTIC_PACKET = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_agentic_20260602/agentic_grading_packet.json"
)
DEFAULT_TYPED_POLICY = Path(
    "artifacts/luban_typed_policy/po_slice_20260601_typed_policy_20260603/typed_policy_candidates.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "artifacts/luban_agentic_grading_harness/po_slice_20260601_deepseek_typed_policy_20260603"
)

DEEPSEEK_ARMS = [
    "deepseek_v4_flash_primary",
    "deepseek_v4_flash_strict_reviewer",
    "deepseek_v4_flash_dual_adjudicated",
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
        case_id = str(task.get("case_id"))
        for point in task.get("scoring_points") or []:
            point_id = str(point.get("point_id"))
            policy = indexed.get((case_id, point_id))
            if not policy:
                missing.append({"case_id": case_id, "point_id": point_id})
                point["typed_policy"] = {
                    "policy_type": "high_risk_review",
                    "policy_readiness": "missing_policy",
                    "safety_notes": ["typed_policy_missing_do_not_auto_certify"],
                }
                continue
            point["typed_policy"] = _compact_policy(policy)
    packet["status"] = "awaiting_deepseek_v4_flash_predictions"
    packet["typed_policy_version_id"] = (typed_policy.get("summary") or {}).get("version_id", "")
    packet["typed_policy_schema_version"] = (typed_policy.get("summary") or {}).get("schema_version", "")
    packet["typed_policy_missing_points"] = missing
    packet["agentic_rule"] = (
        "DeepSeek-v4-flash is evaluated in three isolated roles: primary understanding, "
        "strict reviewer, and final adjudicator. Typed policy guides judgment; it is not a "
        "runtime hard gate and required_terms are not a global substring rule."
    )
    return packet


def _prompt(role: str, packet_name: str) -> str:
    role_instruction = {
        "deepseek_v4_flash_primary": (
            "你是 primary grader。你的任务是理解学生答案是否满足每个采分点，输出点级判断。"
            "你可以利用 typed_policy，但不要机械 substring。"
        ),
        "deepseek_v4_flash_strict_reviewer": (
            "你是 strict reviewer。你的任务不是重新写解析，而是专门审查 primary 的误给分、漏给分、"
            "unsupported span、计算错误、方向错误、近义/大白话放水。"
        ),
        "deepseek_v4_flash_dual_adjudicated": (
            "你是 final adjudicator。你要结合 primary 与 strict reviewer 的分歧，给出最终点级裁决。"
            "不要把 required_terms 当作全局 substring 硬门；只有 policy_type 明确要求严格术语时，"
            "才把 required_terms 作为纪律边界。"
        ),
    }[role]
    return f"""# 鲁班 DeepSeek-v4-flash Typed Policy Shadow - {role}

读取 `{packet_name}`。只根据题干、标准答案、采分点、typed_policy 和学生答案阅卷。

{role_instruction}

硬规则：
- 不使用外部资料，不接 RAG。
- 不读取 human label、ledger、artifact_first 预测或任何答案对照。
- hit/partial 必须提供学生答案中的 `evidence_span`；没有 span 或 span 不在学生答案中，必须标 `unsupported=true` 或退 miss。
- `policy_type=calculation` 时，不要凭感觉给数值分；无法核算时标 high_risk。
- `policy_type=list_rule` 时，按 typed_policy 的 denominator/terms 理解 k/n，但 denominator 仍是 candidate，不得伪装成生产硬门。
- `policy_type=penalty_rule` 时，必须先判断罚则是否触发，再判断 base_policy。
- `policy_type=high_risk_review` 时，不自动认证，给出保守判断和 high_risk=true。
- 不要把 required_terms 当作全局 substring 硬门；上一轮已证明这种做法会退步。

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
          "disposition": "agree|fixed_over_credit|fixed_under_credit|high_risk|initial",
          "high_risk": false,
          "unsupported": false
        }}
      ]
    }}
  ]
}}
```
"""


def _runbook(output_dir: Path) -> str:
    return f"""# DeepSeek-v4-flash Typed Policy Shadow Runbook

## Scope

- Directional/shadow only.
- Does not touch `CaseGradingSkillKernel`.
- Does not enter production runtime.
- Uses typed policy as prompt protocol, not a global hard gate.

## Fill Predictions

1. Feed `deepseek_typed_policy_packet.json` to DeepSeek-v4-flash with `deepseek_primary_prompt.md`.
2. Put the model output into `deepseek_predictions_template.json` under `deepseek_v4_flash_primary`.
3. Feed primary predictions plus the same packet to `deepseek_strict_reviewer_prompt.md`.
4. Put reviewer output under `deepseek_v4_flash_strict_reviewer`.
5. Feed primary + reviewer + packet to `deepseek_dual_adjudicator_prompt.md`.
6. Put final output under `deepseek_v4_flash_dual_adjudicated`.

## Score

```bash
python scripts/build_luban_agentic_grading_harness.py score \\
  --predictions {output_dir / "deepseek_predictions_template.json"} \\
  --output {output_dir / "deepseek_prediction_metrics.json"}
```

## Gate

- `deepseek_v4_flash_dual_adjudicated.point_hit_agreement >= 0.90`
- `deepseek_v4_flash_dual_adjudicated.mean_abs_score_delta <= 0.70`
- `unsupported_judgment_rate == 0`
- high-risk cases must be explicitly marked, not silently auto-certified.

Passing this gate means DeepSeek-v4-flash qualifies for larger shadow eval. It does not mean production launch.
"""


def _finding(packet: dict[str, Any], output_dir: Path) -> str:
    policy_counts: dict[str, int] = {}
    point_count = 0
    for task in packet.get("tasks") or []:
        for point in task.get("scoring_points") or []:
            point_count += 1
            policy_type = str((point.get("typed_policy") or {}).get("policy_type") or "missing")
            policy_counts[policy_type] = policy_counts.get(policy_type, 0) + 1

    lines = [
        "# DeepSeek-v4-flash Typed Policy Shadow Finding 2026-06-03",
        "",
        "## Status",
        "",
        "- Shadow packet: ready.",
        "- Model predictions: not filled in this environment.",
        "- Production status: not eligible; requires real DeepSeek predictions and scoring.",
        "- Runtime changes: none.",
        "",
        "## Packet",
        "",
        f"- tasks: `{len(packet.get('tasks') or [])}`",
        f"- point_rows: `{point_count}`",
        f"- typed_policy_version_id: `{packet.get('typed_policy_version_id')}`",
        f"- typed_policy_missing_points: `{len(packet.get('typed_policy_missing_points') or [])}`",
        "",
        "## Policy Distribution In Packet",
        "",
    ]
    for key in sorted(policy_counts):
        lines.append(f"- {key}: `{policy_counts[key]}`")
    lines.extend(
        [
            "",
            "## Gate Command",
            "",
            "```bash",
            "python scripts/build_luban_agentic_grading_harness.py score \\",
            f"  --predictions {output_dir / 'deepseek_predictions_template.json'} \\",
            f"  --output {output_dir / 'deepseek_prediction_metrics.json'}",
            "```",
            "",
            "## Decision Boundary",
            "",
            "- Passing the configured gate qualifies DeepSeek-v4-flash for larger shadow eval only.",
            "- Do not promote required_terms to a global hard gate.",
            "- Do not touch CaseGradingSkillKernel from this artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_deepseek_shadow_packet(
    *,
    agentic_packet_path: Path,
    typed_policy_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    agentic_packet = _read_json(agentic_packet_path)
    typed_policy = _read_json(typed_policy_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    packet = _inject_typed_policy(agentic_packet, typed_policy)
    packet_path = output_dir / "deepseek_typed_policy_packet.json"
    template_path = output_dir / "deepseek_predictions_template.json"
    primary_prompt = output_dir / "deepseek_primary_prompt.md"
    reviewer_prompt = output_dir / "deepseek_strict_reviewer_prompt.md"
    dual_prompt = output_dir / "deepseek_dual_adjudicator_prompt.md"
    runbook_path = output_dir / "RUNBOOK_deepseek_typed_policy_shadow.md"
    gate_path = output_dir / "production_candidate_gate.json"
    finding_path = output_dir / "FINDING_deepseek_typed_policy_shadow_20260603.md"

    _write_json(packet_path, packet)
    _write_json(
        template_path,
        {
            "slice_id": packet.get("slice_id"),
            "model": "deepseek-v4-flash",
            "prediction_sets": [{"arm": arm, "predictions": []} for arm in DEEPSEEK_ARMS],
        },
    )
    primary_prompt.write_text(_prompt("deepseek_v4_flash_primary", packet_path.name), encoding="utf-8")
    reviewer_prompt.write_text(_prompt("deepseek_v4_flash_strict_reviewer", packet_path.name), encoding="utf-8")
    dual_prompt.write_text(_prompt("deepseek_v4_flash_dual_adjudicated", packet_path.name), encoding="utf-8")
    runbook_path.write_text(_runbook(output_dir), encoding="utf-8")
    finding_path.write_text(_finding(packet, output_dir), encoding="utf-8")
    _write_json(
        gate_path,
        {
            "status": "shadow_only_not_production",
            "model": "deepseek-v4-flash",
            "required_arm": "deepseek_v4_flash_dual_adjudicated",
            "thresholds": {
                "point_hit_agreement_min": 0.90,
                "mean_abs_score_delta_max": 0.70,
                "unsupported_judgment_rate_max": 0.0,
            },
            "next_if_pass": "larger_shadow_eval_not_runtime_launch",
            "blocked_actions": [
                "do_not_touch_case_grading_kernel",
                "do_not_promote_required_terms_to_global_hard_gate",
                "do_not_claim_production_accuracy",
            ],
        },
    )
    return {
        "packet": packet_path,
        "template": template_path,
        "primary_prompt": primary_prompt,
        "reviewer_prompt": reviewer_prompt,
        "dual_prompt": dual_prompt,
        "runbook": runbook_path,
        "gate": gate_path,
        "finding": finding_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build DeepSeek typed-policy shadow grading packet.")
    parser.add_argument("--agentic-packet", type=Path, default=DEFAULT_AGENTIC_PACKET)
    parser.add_argument("--typed-policy", type=Path, default=DEFAULT_TYPED_POLICY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    paths = build_deepseek_shadow_packet(
        agentic_packet_path=args.agentic_packet,
        typed_policy_path=args.typed_policy,
        output_dir=args.output_dir,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
