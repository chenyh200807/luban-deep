#!/usr/bin/env python3
"""Run M35 DeepSeek adversarial probe as shadow candidate evidence only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is present in normal repo env
    load_dotenv = None

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.m35_ai_governed_gold import (  # noqa: E402
    build_deepseek_adversarial_prompt,
    normalize_deepseek_adversarial_report,
)

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_env() -> None:
    if load_dotenv is None:
        return
    load_dotenv(REPO / ".env", override=False)
    load_dotenv(REPO / ".env.local", override=False)


def _samples(fixture_dir: Path, max_samples: int) -> list[dict[str, Any]]:
    manifest = _read_json(fixture_dir / "manifest.json")
    questions = {
        str(question.get("question_id") or ""): question
        for question in manifest.get("questions") or []
    }
    rows = _read_jsonl(fixture_dir / "student_answers.jsonl")
    samples: list[dict[str, Any]] = []
    for row in rows:
        question = questions.get(str(row.get("question_id") or ""))
        if not question:
            continue
        artifact = {
            "artifact_version": "m35_deepseek_adversarial_probe.v1",
            "question_authority_ref": question.get("question_authority_ref"),
            "source_refs": question.get("source_refs") or [],
            "gold_point_matches": row.get("gold_point_matches") or [],
        }
        samples.append(
            {
                "answer_id": str(row.get("answer_id") or ""),
                "question_id": str(row.get("question_id") or ""),
                "question": question,
                "artifact": artifact,
                "student_answer": str(row.get("student_answer") or ""),
            }
        )
        if len(samples) >= max_samples:
            break
    return samples


def _fixture_payload(sample: dict[str, Any]) -> dict[str, Any]:
    refs = sample["artifact"].get("source_refs") or []
    matches = sample["artifact"].get("gold_point_matches") or []
    point_id = str((matches[0] if matches else {}).get("point_id") or "P1")
    return {
        "source_challenges": [
            {
                "point_id": point_id,
                "reason": "fixture_adversary_requires_field_level_source_support",
                "source_ref_count": len(refs),
            }
        ],
        "rubric_attacks": [
            {
                "point_id": point_id,
                "risk": "overaccepts_generated_self_label_until_ai_governed_protocol_passes",
            }
        ],
        "suggested_demotions": [],
        "unresolved_objection_count": 0,
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
        raise ValueError("provider reply did not contain a JSON object")
    depth = 0
    for index in range(start, len(raw)):
        char = raw[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : index + 1])
    raise ValueError("provider reply contained an incomplete JSON object")


def _call_deepseek(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an adversarial prosecutor. Return strict JSON only. "
                    "You are not release truth."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    return _extract_json_object(content)


def build_probe_payload(
    *,
    fixture: Path,
    output: Path,
    mode: str,
    model: str,
    max_samples: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    _load_env()
    api_key = os.environ.get("DEEPSEEK_API_KEY") or ""
    base_url = os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL

    reports = []
    provider_call_count = 0
    status = "OK"
    error_type = ""

    if mode == "live" and not api_key:
        status = "BLOCKED_MISSING_DEEPSEEK_API_KEY"
    else:
        for sample in _samples(fixture, max_samples):
            prompt = build_deepseek_adversarial_prompt(
                question=sample["question"],
                artifact=sample["artifact"],
                student_answer=sample["student_answer"],
            )
            try:
                if mode == "fixture":
                    raw = _fixture_payload(sample)
                else:
                    provider_call_count += 1
                    raw = _call_deepseek(
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                        prompt=prompt,
                        timeout_seconds=timeout_seconds,
                    )
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                status = "BLOCKED_PROVIDER_ERROR"
                error_type = type(exc).__name__
                break
            report = normalize_deepseek_adversarial_report(raw, model_id=model)
            report["question_id"] = sample["question_id"]
            report["answer_id"] = sample["answer_id"]
            reports.append(report)

    payload = {
        "schema_version": "luban_m35_deepseek_adversarial_probe.v1",
        "mode": mode,
        "status": status,
        "model": model,
        "adversarial_role": "prosecutor",
        "provider_call_count": provider_call_count,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "promote_to_release": False,
        "runtime_usable_as_truth": False,
        "fixture": str(fixture),
        "output": str(output),
        "error_type": error_type,
        "reports": reports,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices={"fixture", "live"}, default="fixture")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_M35_ADVERSARIAL_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--max-samples", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    output = Path(args.output)
    payload = build_probe_payload(
        fixture=Path(args.fixture),
        output=output,
        mode=args.mode,
        model=args.model,
        max_samples=max(0, args.max_samples),
        timeout_seconds=args.timeout_seconds,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
