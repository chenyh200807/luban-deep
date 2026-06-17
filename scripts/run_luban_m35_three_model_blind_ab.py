#!/usr/bin/env python3
"""Run M35 three-model blind A/B as local shadow evidence only."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_ORIGINAL_REPO = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor")
DEFAULT_FIXTURE = REPO / "tests/fixtures/luban_m35_case_scoring"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


def _load_env(env_file: Path | None = None) -> None:
    if load_dotenv is None:
        return
    candidates = []
    if env_file is not None:
        candidates.append(env_file)
    candidates.extend(
        [
            REPO / ".env",
            REPO / ".env.local",
            DEFAULT_ORIGINAL_REPO / ".env",
            DEFAULT_ORIGINAL_REPO / ".env.local",
        ]
    )
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _samples(fixture: Path, max_samples: int, start_index: int = 0) -> list[dict[str, Any]]:
    if max_samples <= 0:
        return []
    manifest = _read_json(fixture / "manifest.json")
    questions = {
        str(question.get("question_id") or ""): question
        for question in manifest.get("questions") or []
    }
    rows = _read_jsonl(fixture / "student_answers.jsonl")
    out = []
    for row in rows[max(0, start_index) :]:
        question = questions.get(str(row.get("question_id") or ""))
        if not question:
            continue
        out.append(
            {
                "answer_id": str(row.get("answer_id") or ""),
                "question_id": str(row.get("question_id") or ""),
                "question": _bounded_question(question),
                "student_answer": str(row.get("student_answer") or "")[:1800],
                "generated_label": {
                    "gold_score": row.get("gold_score"),
                    "gold_point_matches": row.get("gold_point_matches") or [],
                    "scoring_points": row.get("scoring_points") or [],
                    "scoring_protocol": row.get("scoring_protocol") or {},
                    "label_authority": row.get("label_authority"),
                },
            }
        )
        if len(out) >= max_samples:
            break
    return out


def _bounded_question(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": question.get("question_id"),
        "stem": str(question.get("stem") or "")[:1800],
        "total_score": question.get("total_score"),
        "source_refs": list(question.get("source_refs") or [])[:12],
        "question_authority_ref": question.get("question_authority_ref"),
    }


def _artifact_for_sample(sample: dict[str, Any]) -> dict[str, Any]:
    label = sample["generated_label"]
    points = label.get("scoring_points") or label["gold_point_matches"]
    return {
        "artifact_version": "m35_three_model_blind_ab.fixture.v1",
        "question_id": sample["question_id"],
        "source_refs": sample["question"].get("source_refs") or [],
        "scoring_points": [
            {
                "point_id": point.get("point_id"),
                "criterion": point.get("criterion") or point.get("label"),
                "max_score": point.get("max_score"),
            }
            for point in points
        ],
        "scoring_protocol": label.get("scoring_protocol") or {},
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    if start < 0:
        raise ValueError("provider reply did not contain JSON")
    depth = 0
    for index in range(start, len(raw)):
        if raw[index] == "{":
            depth += 1
        elif raw[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : index + 1])
    raise ValueError("provider reply contained incomplete JSON")


def _chat_json(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"].get("content") or ""
    return _extract_json_object(content)


def _scorer_prompt(provider: str, sample: dict[str, Any], artifact: dict[str, Any]) -> str:
    packet = {
        "question": sample["question"],
        "student_answer": sample["student_answer"],
        "arms": {
            "arm_a": {
                "description": "baseline-style whole-answer grading candidate",
                "available_context": "question + student_answer only",
            },
            "arm_b": {
                "description": "artifact-first point-level grading candidate",
                "available_context": artifact,
            },
        },
    }
    provider_name = "DeepSeek V4 Flash" if provider == "deepseek" else "Qwen Flash"
    return (
        f"You are {provider_name} acting as a blind scorer for an M35 A/B test. "
        "Do not infer which arm is preferred. Score both arms independently. "
        "Return strict JSON with keys baseline, artifact_first. Each value must contain "
        "score, point_matches, rationale, blind_to_arm_name=true.\n"
        f"PACKET={json.dumps(packet, ensure_ascii=False, sort_keys=True)}"
    )


def _prosecutor_prompt(provider: str, sample: dict[str, Any], primary_scores: dict[str, Any]) -> str:
    packet = {
        "question": sample["question"],
        "student_answer": sample["student_answer"],
        "primary_scores": primary_scores,
    }
    provider_name = "DeepSeek V4 Pro" if provider == "deepseek" else "Qwen Flash"
    return (
        f"You are {provider_name} acting only as adversarial prosecutor. "
        "Attack over-credit, source pollution, slogan answers, near-synonym mistakes, "
        "and unsupported point matches. You are not final judge. Return strict JSON "
        "with keys objections, suggested_demotions, source_challenges, unresolved_objection_count.\n"
        f"PACKET={json.dumps(packet, ensure_ascii=False, sort_keys=True)}"
    )


def _gpt_prompt(
    sample: dict[str, Any],
    qwen_scores: dict[str, Any],
    deepseek_report: dict[str, Any],
) -> str:
    packet = {
        "question": sample["question"],
        "student_answer": sample["student_answer"],
        "qwen_scores": qwen_scores,
        "deepseek_prosecution": deepseek_report,
    }
    return (
        "You are GPT5.5 acting as final adjudicator and protocol gate for M35. "
        "Choose one recommendation: artifact_first_wins, baseline_wins, tie, send_to_review. "
        "You must not grant official score, release truth, production default, or canonical learner truth. "
        "Return strict JSON with keys recommendation, rationale, unresolved_objections, "
        "official_score_allowed=false, quality_claim_allowed=false.\n"
        f"PACKET={json.dumps(packet, ensure_ascii=False, sort_keys=True)}"
    )


def _fixture_case(sample: dict[str, Any], *, scorer: str = "qwen", adversary: str = "deepseek", local_final_adjudicator: bool = False) -> dict[str, Any]:
    points = sample["generated_label"]["gold_point_matches"]
    total = float(sample["generated_label"].get("gold_score") or 0)
    primary = {
        "baseline": {
            "score": total,
            "point_matches": [],
            "rationale": "fixture baseline placeholder; not quality evidence",
            "blind_to_arm_name": True,
        },
        "artifact_first": {
            "score": total,
            "point_matches": points,
            "rationale": "fixture artifact-first shape proof; not quality evidence",
            "blind_to_arm_name": True,
        },
    }
    adversarial = {
        "role": "adversarial_prosecutor",
        "objections": [],
        "suggested_demotions": [],
        "source_challenges": [],
        "unresolved_objection_count": 0,
    }
    gpt = {
        "role": "local_agent_final_adjudicator" if local_final_adjudicator else "final_adjudicator",
        "recommendation": "tie",
        "rationale": "fixture mode cannot decide quality",
        "unresolved_objections": 0,
        "official_score_allowed": False,
        "quality_claim_allowed": False,
    }
    return _case_payload(sample, primary, adversarial, gpt, scorer=scorer, adversary=adversary)


def _local_final_pending(deepseek_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "local_agent_final_adjudicator",
        "recommendation": "send_to_review",
        "rationale": "awaiting Codex GPT5.5 local final adjudication; not provider evidence",
        "unresolved_objections": deepseek_report.get("unresolved_objection_count", 0),
        "official_score_allowed": False,
        "quality_claim_allowed": False,
        "local_final_adjudication_required": True,
    }


def _case_payload(
    sample: dict[str, Any],
    primary_scores: dict[str, Any],
    adversarial_report: dict[str, Any],
    gpt_adjudication: dict[str, Any],
    *,
    scorer: str = "qwen",
    adversary: str = "deepseek",
) -> dict[str, Any]:
    adversarial_report = dict(adversarial_report)
    adversarial_report.setdefault("role", "adversarial_prosecutor")
    gpt_adjudication = dict(gpt_adjudication)
    gpt_adjudication.setdefault("role", "final_adjudicator")
    gpt_adjudication["official_score_allowed"] = False
    gpt_adjudication["quality_claim_allowed"] = False
    recommendation = str(gpt_adjudication.get("recommendation") or "send_to_review")
    if recommendation not in {"artifact_first_wins", "baseline_wins", "tie", "send_to_review"}:
        gpt_adjudication["recommendation"] = "send_to_review"
    payload = {
        "answer_id": sample["answer_id"],
        "question_id": sample["question_id"],
        "primary_scores": primary_scores,
        "adversarial_review": adversarial_report,
        "gpt55_adjudication": gpt_adjudication,
        "final_adjudication": gpt_adjudication,
    }
    payload[f"{scorer}_blind_scores"] = primary_scores
    payload[f"{adversary}_prosecution"] = adversarial_report
    return payload


def _provider_specs(*, local_final_adjudicator: bool = False, scorer: str = "qwen", adversary: str = "deepseek") -> dict[str, dict[str, str]]:
    qwen_role_model = (
        os.getenv("QWEN_M35_BLIND_MODEL") or os.getenv("QWEN_MODEL") or "qwen-max"
        if scorer == "qwen"
        else os.getenv("QWEN_M35_ADVERSARIAL_MODEL") or os.getenv("QWEN_MODEL") or "qwen-flash"
    )
    deepseek_role_model = (
        os.getenv("DEEPSEEK_M35_BLIND_MODEL") or "deepseek-v4-flash"
        if scorer == "deepseek"
        else os.getenv("DEEPSEEK_M35_ADVERSARIAL_MODEL") or "deepseek-v4-pro"
    )
    return {
        "qwen": {
            "key_env": "DASHSCOPE_API_KEY",
            "base_url": os.getenv("DASHSCOPE_BASE_URL") or QWEN_BASE_URL,
            "model": qwen_role_model,
        },
        "deepseek": {
            "key_env": "DEEPSEEK_API_KEY",
            "base_url": os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL,
            "model": deepseek_role_model,
        },
        "gpt55": {
            "key_env": "" if local_final_adjudicator else "OPENAI_API_KEY",
            "base_url": os.getenv("OPENAI_BASE_URL") or OPENAI_BASE_URL,
            "model": "codex-gpt55-local-agent"
            if local_final_adjudicator
            else os.getenv("GPT55_M35_ADJUDICATOR_MODEL") or "gpt-5.5",
        },
    }


def _missing_key_envs(specs: dict[str, dict[str, str]]) -> list[str]:
    return [
        spec["key_env"]
        for spec in specs.values()
        if spec["key_env"] and not os.environ.get(spec["key_env"])
    ]


def _summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "artifact_first_win_count": 0,
        "baseline_win_count": 0,
        "tie_count": 0,
        "send_to_review_count": 0,
    }
    for case in cases:
        rec = str((case.get("final_adjudication") or {}).get("recommendation") or "send_to_review")
        if rec == "artifact_first_wins":
            counts["artifact_first_win_count"] += 1
        elif rec == "baseline_wins":
            counts["baseline_win_count"] += 1
        elif rec == "tie":
            counts["tie_count"] += 1
        else:
            counts["send_to_review_count"] += 1
    counts["quality_claim_allowed"] = False
    counts["effect_claim"] = "directional_ai_governed_shadow_only"
    return counts


def build_payload(
    *,
    fixture: Path,
    output: Path,
    mode: str,
    max_samples: int,
    timeout_seconds: int,
    env_file: Path | None = None,
    local_final_adjudicator: bool = False,
    scorer: str = "qwen",
    adversary: str = "deepseek",
    start_index: int = 0,
) -> dict[str, Any]:
    _load_env(env_file)
    specs = _provider_specs(
        local_final_adjudicator=local_final_adjudicator,
        scorer=scorer,
        adversary=adversary,
    )
    missing = _missing_key_envs(specs) if mode == "live" else []
    cases: list[dict[str, Any]] = []
    provider_call_count = 0
    status = "AWAITING_LOCAL_FINAL_ADJUDICATION" if mode == "live" and local_final_adjudicator else "OK"
    error_type = ""

    if missing:
        status = "BLOCKED_MISSING_PROVIDER_KEYS"
    else:
        for sample in _samples(fixture, max_samples, start_index=start_index):
            try:
                if mode == "fixture":
                    case = _fixture_case(
                        sample,
                        scorer=scorer,
                        adversary=adversary,
                        local_final_adjudicator=local_final_adjudicator,
                    )
                else:
                    artifact = _artifact_for_sample(sample)
                    primary_raw = _chat_json(
                        base_url=specs[scorer]["base_url"],
                        api_key=os.environ[specs[scorer]["key_env"]],
                        model=specs[scorer]["model"],
                        system="Return strict JSON only.",
                        prompt=_scorer_prompt(scorer, sample, artifact),
                        max_tokens=4096,
                        timeout_seconds=timeout_seconds,
                    )
                    provider_call_count += 1
                    adversarial_raw = _chat_json(
                        base_url=specs[adversary]["base_url"],
                        api_key=os.environ[specs[adversary]["key_env"]],
                        model=specs[adversary]["model"],
                        system="Return strict JSON only. You are adversarial prosecutor, not final judge.",
                        prompt=_prosecutor_prompt(adversary, sample, primary_raw),
                        max_tokens=8192,
                        timeout_seconds=timeout_seconds,
                    )
                    provider_call_count += 1
                    if local_final_adjudicator:
                        gpt_raw = _local_final_pending(adversarial_raw)
                    else:
                        gpt_raw = _chat_json(
                            base_url=specs["gpt55"]["base_url"],
                            api_key=os.environ[specs["gpt55"]["key_env"]],
                            model=specs["gpt55"]["model"],
                            system="Return strict JSON only. You are final adjudicator and protocol gate.",
                            prompt=_gpt_prompt(sample, primary_raw, adversarial_raw),
                            max_tokens=4096,
                            timeout_seconds=timeout_seconds,
                        )
                        provider_call_count += 1
                    case = _case_payload(
                        sample,
                        primary_raw,
                        adversarial_raw,
                        gpt_raw,
                        scorer=scorer,
                        adversary=adversary,
                    )
                cases.append(case)
            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
                http.client.RemoteDisconnected,
            ) as exc:
                status = "BLOCKED_PROVIDER_ERROR"
                error_type = type(exc).__name__
                break

    return {
        "schema_version": "luban_m35_three_model_blind_ab.v1",
        "mode": mode,
        "status": status,
        "roles": {
            scorer: "blind_scorer",
            adversary: "adversarial_prosecutor",
            "gpt55": "local_agent_final_adjudicator"
            if local_final_adjudicator
            else "final_adjudicator",
        },
        "models": {name: spec["model"] for name, spec in specs.items()},
        "sample_window": {"start_index": max(0, start_index), "max_samples": max_samples},
        "missing_key_envs": missing,
        "provider_call_count": provider_call_count,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "promote_to_release": False,
        "runtime_usable_as_truth": False,
        "quality_claim_allowed": False,
        "fixture": str(fixture),
        "output": str(output),
        "error_type": error_type,
        "cases": cases,
        "summary": _summary(cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices={"fixture", "live"}, default="fixture")
    parser.add_argument("--max-samples", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--local-final-adjudicator", action="store_true")
    parser.add_argument("--scorer", choices={"qwen", "deepseek"}, default="qwen")
    parser.add_argument("--adversary", choices={"qwen", "deepseek"}, default="deepseek")
    parser.add_argument("--start-index", type=int, default=0)
    args = parser.parse_args()

    output = Path(args.output)
    payload = build_payload(
        fixture=args.fixture,
        output=output,
        mode=args.mode,
        max_samples=max(0, args.max_samples),
        timeout_seconds=args.timeout_seconds,
        env_file=args.env_file,
        local_final_adjudicator=args.local_final_adjudicator,
        scorer=args.scorer,
        adversary=args.adversary,
        start_index=max(0, args.start_index),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
