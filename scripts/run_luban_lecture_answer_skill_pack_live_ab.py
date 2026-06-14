#!/usr/bin/env python3
"""Build and run a live-ready A/B eval for Luban lecture answer skill packs.

This harness compares two context strategies on the same lecture-derived exam
questions:

* raw_json_baseline: lecture source excerpt + citation only.
* answer_skill_pack: same source excerpt plus compiled exam answer method fields.

Default mode is a deterministic stub to verify prompt packaging and judge wiring.
Real provider calls only happen with ``--run-live`` and an available provider key.
No DB, registry, production runtime, or canonical learner truth is written.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PACK_ROOT = REPO / "artifacts" / "luban_grading_artifacts" / "lecture_answer_skill_pack_v1_20260614"
DEFAULT_OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / (
    "lecture_answer_skill_pack_live_ab_" + date.today().strftime("%Y%m%d")
)

AB_SPEC = importlib.util.spec_from_file_location(
    "lecture_ab",
    Path(__file__).with_name("run_luban_lecture_answer_skill_pack_ab_eval.py"),
)
lecture_ab = importlib.util.module_from_spec(AB_SPEC)
AB_SPEC.loader.exec_module(lecture_ab)

AD_TERMS = lecture_ab.AD_TERMS
ARMS = ("raw_json_baseline", "answer_skill_pack")
ENV_FILES = [
    REPO / ".env",
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env"),
]
PROVIDER_SPECS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "env_key": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


def _stable_id(*parts: Any, length: int = 16) -> str:
    raw = "::".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _as_list(value: Any) -> list[str]:
    return lecture_ab._as_list(value)


def _load_env_from_files() -> dict[str, str]:
    env = dict(os.environ)
    for path in ENV_FILES:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key in {"DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"} and value:
                    env.setdefault(key, value)
        except OSError:
            pass
    return env


def _question_for_unit(unit: dict[str, Any]) -> str:
    label = (unit.get("question_patterns") or [unit.get("topic") or unit["unit_id"]])[0]
    return f"{label}怎么按一建建筑实务考试答？"


def _material_method_lines(method: dict[str, Any]) -> list[str]:
    lines = [f"答题方式：{method.get('answer_style') or '先给结论，再列采分点。'}"]
    field_map = [
        ("采分关键词", "must_mentions"),
        ("公式/阈值/适用条件", "formula_or_thresholds"),
        ("陷阱提醒", "trap_alerts"),
        ("红线", "red_lines"),
        ("口诀", "mnemonics"),
    ]
    for label, key in field_map:
        values = _as_list(method.get(key))
        if values:
            lines.append(f"{label}：" + "；".join(values))
    return lines


def render_prompt(unit: dict[str, Any], arm: str) -> str:
    method = unit.get("answer_method") or {}
    source_ref = unit.get("source_ref") or {}
    question = _question_for_unit(unit)
    lines = [
        "你是鲁班智考的一建建筑实务答题助手。",
        "只根据本轮给出的讲义材料回答；材料没有的内容写“材料未提供”，不要补讲义外知识。",
        "回答必须引用 json_page_num 和 chunk_id；广告、二维码、课程销售信息一律忽略。",
        "",
        f"【题目】{question}",
        f"【讲义】{unit.get('lecture') or ''} / {unit.get('topic') or ''}",
        f"【出处】json_page_num={source_ref.get('json_page_num')}；chunk_id={source_ref.get('source_chunk_id')}",
        "",
        "【讲义原文】",
        str(unit.get("source_excerpt") or "").strip()[:900],
        "",
    ]
    if arm == "answer_skill_pack":
        lines.extend(["【编译答题方法】", *_material_method_lines(method), ""])
    lines.extend(
        [
            "【输出格式】",
            "结论：",
            "采分点：",
            "公式/适用条件：",
            "陷阱/红线：",
            "口诀：",
            "出处：",
        ]
    )
    return "\n".join(lines)


def _eligible_units(pack_root: Path, max_cases: int) -> list[dict[str, Any]]:
    units = lecture_ab.load_answer_units(pack_root)
    eligible = lecture_ab._eligible_units(units, max_cases=len(units))
    groups: dict[str, list[dict[str, Any]]] = {}
    for unit in eligible:
        key = str(unit.get("lecture_slug") or unit.get("lecture") or "unknown")
        groups.setdefault(key, []).append(unit)
    selected: list[dict[str, Any]] = []
    while len(selected) < max_cases and any(groups.values()):
        for key in list(groups.keys()):
            if groups[key]:
                selected.append(groups[key].pop(0))
                if len(selected) >= max_cases:
                    break
    return selected


def build_prompt_package(
    *,
    pack_root: Path,
    max_cases: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    prompt_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    for index, unit in enumerate(_eligible_units(pack_root, max_cases=max_cases), start=1):
        case_id = f"case_{index:04d}_{_stable_id(unit['unit_id'], length=8)}"
        arm_rows = []
        for arm in ARMS:
            blind_id = f"blind_{_stable_id(case_id, arm, seed, length=12)}"
            prompt = render_prompt(unit, arm)
            arm_rows.append(
                {
                    "blind_id": blind_id,
                    "case_id": case_id,
                    "question": _question_for_unit(unit),
                    "prompt": prompt,
                }
            )
            private_rows.append(
                {
                    "blind_id": blind_id,
                    "case_id": case_id,
                    "arm": arm,
                    "unit": unit,
                    "unit_id": unit["unit_id"],
                    "lecture": unit.get("lecture"),
                    "topic": unit.get("topic"),
                    "source_ref": unit.get("source_ref"),
                }
            )
        rng.shuffle(arm_rows)
        prompt_rows.extend(arm_rows)
    return prompt_rows, private_rows


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _extract_line(prompt: str, label: str) -> str:
    if label.startswith("【") and label.endswith("】"):
        match = re.search(rf"^{re.escape(label)}\s*(.*)$", prompt, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""
    match = re.search(rf"^{re.escape(label)}[:：](.*)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def deterministic_stub_answer(prompt: str) -> str:
    citation = _extract_line(prompt, "【出处】") or _extract_line(prompt, "出处")
    if "【编译答题方法】" in prompt:
        method_part = prompt.split("【编译答题方法】", 1)[1].split("【输出格式】", 1)[0]
        lines = [line.strip() for line in method_part.splitlines() if line.strip()]
        return "\n".join(
            [
                "结论：按讲义编译答题方法作答。",
                "采分点：" + "；".join(line for line in lines if line.startswith("采分关键词")),
                "公式/适用条件：" + "；".join(line for line in lines if line.startswith("公式")),
                "陷阱/红线：" + "；".join(line for line in lines if line.startswith(("陷阱提醒", "红线"))),
                "口诀：" + "；".join(line for line in lines if line.startswith("口诀")),
                f"出处：{citation}",
            ]
        )
    source = prompt.split("【讲义原文】", 1)[1].split("【输出格式】", 1)[0].strip()
    source = re.sub(r"\s+", " ", source)[:260]
    return "\n".join(
        [
            "结论：根据讲义原文作答。",
            f"采分点：{source}",
            "公式/适用条件：材料未提供更细分的适用条件时不补充。",
            "陷阱/红线：材料未提供。",
            "口诀：材料未提供。",
            f"出处：{citation}",
        ]
    )


def _openai_compatible_call(
    *,
    provider_name: str,
    prompt: str,
    env: dict[str, str],
    model: str | None,
    timeout: int,
) -> str:
    spec = PROVIDER_SPECS[provider_name]
    api_key = env.get(spec["env_key"])
    if not api_key:
        raise RuntimeError(f"missing {spec['env_key']}")
    payload = {
        "model": model or spec["model"],
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": "你是严谨的一建建筑实务考试答题助手，只依据用户给出的讲义材料回答。",
            },
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        spec["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"])


def _run_answers(
    *,
    prompt_rows: list[dict[str, Any]],
    run_live: bool,
    provider_name: str,
    env: dict[str, str],
    model: str | None,
    timeout: int,
    sleep_seconds: float,
    provider_callable: Callable[[str], str] | None = None,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    answers: list[dict[str, Any]] = []
    provider_errors: list[dict[str, Any]] = []
    provider_call_count = 0
    for row in prompt_rows:
        started = time.time()
        try:
            if provider_callable is not None:
                answer = provider_callable(row["prompt"])
            elif run_live:
                answer = _openai_compatible_call(
                    provider_name=provider_name,
                    prompt=row["prompt"],
                    env=env,
                    model=model,
                    timeout=timeout,
                )
                provider_call_count += 1
                if sleep_seconds:
                    time.sleep(sleep_seconds)
            else:
                answer = deterministic_stub_answer(row["prompt"])
            answers.append(
                {
                    "blind_id": row["blind_id"],
                    "case_id": row["case_id"],
                    "answer": answer,
                    "latency_seconds": round(time.time() - started, 4),
                }
            )
        except (RuntimeError, urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
            provider_errors.append(
                {
                    "blind_id": row["blind_id"],
                    "case_id": row["case_id"],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                }
            )
            answers.append(
                {
                    "blind_id": row["blind_id"],
                    "case_id": row["case_id"],
                    "answer": "",
                    "latency_seconds": round(time.time() - started, 4),
                    "provider_error": type(exc).__name__,
                }
            )
    return answers, provider_call_count, provider_errors


def _field_recall(rows: list[dict[str, Any]], arm: str, hit_key: str, total_key: str) -> float:
    total = sum(row[arm][total_key] for row in rows)
    if total == 0:
        return 1.0
    return round(sum(row[arm][hit_key] for row in rows) / total, 4)


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    scores = [row[arm]["score"] for row in rows]
    return {
        "avg_score": round(mean(scores), 4) if scores else 0.0,
        "min_score": round(min(scores), 4) if scores else 0.0,
        "max_score": round(max(scores), 4) if scores else 0.0,
        "citation_rate": round(mean([row[arm]["citation_hits"] / 2 for row in rows]), 4) if rows else 0.0,
        "trap_recall": _field_recall(rows, arm, "trap_hits", "trap_total"),
        "red_line_recall": _field_recall(rows, arm, "red_line_hits", "red_line_total"),
        "mnemonic_recall": _field_recall(rows, arm, "mnemonic_hits", "mnemonic_total"),
        "threshold_recall": _field_recall(rows, arm, "threshold_hits", "threshold_total"),
        "ad_pollution_count": sum(row[arm]["ad_pollution"] for row in rows),
    }


def judge_answers(
    *,
    private_rows: list[dict[str, Any]],
    answers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    private_by_blind = {row["blind_id"]: row for row in private_rows}
    answer_by_blind = {row["blind_id"]: row for row in answers}
    case_rows: dict[str, dict[str, Any]] = {}
    judge_rows: list[dict[str, Any]] = []
    for blind_id, private in private_by_blind.items():
        answer_text = str((answer_by_blind.get(blind_id) or {}).get("answer") or "")
        score = lecture_ab.score_answer(private["unit"], answer_text)
        case = case_rows.setdefault(
            private["case_id"],
            {
                "case_id": private["case_id"],
                "unit_id": private["unit_id"],
                "lecture": private.get("lecture"),
                "topic": private.get("topic"),
                "question": _question_for_unit(private["unit"]),
            },
        )
        arm = private["arm"]
        case[arm] = score
        case[f"{arm}_blind_id"] = blind_id
        case[f"{arm}_answer"] = answer_text
        judge_rows.append(
            {
                "blind_id": blind_id,
                "case_id": private["case_id"],
                "arm": arm,
                "score": score,
            }
        )
    rows = [row for row in case_rows.values() if all(arm in row for arm in ARMS)]
    wins: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        raw_score = row["raw_json_baseline"]["score"]
        skill_score = row["answer_skill_pack"]["score"]
        if skill_score > raw_score:
            wins["answer_skill_pack"] += 1
        elif raw_score > skill_score:
            wins["raw_json_baseline"] += 1
        else:
            wins["tie"] += 1
    return rows, judge_rows, dict(wins)


def _delta(skill_summary: dict[str, Any], raw_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "avg_score": round(skill_summary["avg_score"] - raw_summary["avg_score"], 4),
        "trap_recall": round(skill_summary["trap_recall"] - raw_summary["trap_recall"], 4),
        "red_line_recall": round(skill_summary["red_line_recall"] - raw_summary["red_line_recall"], 4),
        "mnemonic_recall": round(skill_summary["mnemonic_recall"] - raw_summary["mnemonic_recall"], 4),
        "threshold_recall": round(skill_summary["threshold_recall"] - raw_summary["threshold_recall"], 4),
    }


def _quality_verdict(
    *,
    run_live: bool,
    case_count: int,
    wins: dict[str, int],
    arms: dict[str, Any],
    delta: dict[str, Any],
    provider_unavailable: bool,
    provider_errors: list[dict[str, Any]],
) -> tuple[str, bool]:
    if provider_unavailable:
        return "PROVIDER_UNAVAILABLE_NO_GO", False
    if provider_errors:
        return "PROVIDER_ERROR_NO_GO", False
    if not run_live:
        if wins.get("answer_skill_pack", 0) > wins.get("raw_json_baseline", 0) and delta["avg_score"] > 0:
            return "PROMPT_PACKAGE_READY_STUB_PASS", False
        return "PROMPT_PACKAGE_READY_STUB_FAIL", False
    if case_count < 10:
        return "LIVE_AB_INSUFFICIENT_CASES_NO_GO", False
    skill = arms["answer_skill_pack"]
    win_rate = wins.get("answer_skill_pack", 0) / case_count if case_count else 0.0
    pass_gate = (
        win_rate >= 0.60
        and delta["avg_score"] >= 0.08
        and skill["citation_rate"] >= 0.95
        and skill["ad_pollution_count"] == 0
        and (delta["trap_recall"] >= 0.20 or skill["trap_recall"] >= 0.95)
        and (delta["red_line_recall"] >= 0.20 or skill["red_line_recall"] >= 0.95)
    )
    return ("LIVE_AB_GO" if pass_gate else "LIVE_AB_NO_GO"), pass_gate


def _write_finding(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Lecture Answer Skill Pack Live A/B Finding",
        "",
        f"- verdict: {result['verdict']}",
        f"- mode: {result['mode']}",
        f"- provider: {result['provider']}",
        f"- model: {result.get('model') or 'default'}",
        f"- case_count: {result['case_count']}",
        f"- prompt_count: {result['prompt_count']}",
        f"- provider_call_count: {result['provider_call_count']}",
        f"- winner: {result['winner']}",
        f"- avg_score_delta: {result['delta']['avg_score']}",
        f"- live_claim_allowed: {str(result['live_claim_allowed']).lower()}",
        "",
        "| arm | avg | citation | trap | red line | mnemonic | threshold | ad pollution |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, summary in result["arms"].items():
        lines.append(
            f"| {arm} | {summary['avg_score']} | {summary['citation_rate']} | "
            f"{summary['trap_recall']} | {summary['red_line_recall']} | "
            f"{summary['mnemonic_recall']} | {summary['threshold_recall']} | "
            f"{summary['ad_pollution_count']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Stub mode only verifies prompt packaging and deterministic judge wiring; it is not live model evidence.",
            "- Live mode is fail-closed when provider keys are unavailable or provider calls fail.",
            "- Passing this eval only authorizes producing the remaining lecture runtime-supply candidates; it does not publish registry/default runtime or official scoring authority.",
        ]
    )
    if result.get("provider_unavailable"):
        lines.extend(["", "## Blocker", "", f"- Missing provider key: {result.get('missing_provider_key')}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_live_ab(
    *,
    pack_root: Path,
    out_dir: Path,
    max_cases: int = 20,
    run_live: bool = False,
    provider_name: str = "stub",
    model: str | None = None,
    env: dict[str, str] | None = None,
    seed: int = 17,
    timeout: int = 60,
    sleep_seconds: float = 0.0,
    provider_callable: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    effective_env = _load_env_from_files() if env is None else dict(env)
    prompt_rows, private_rows = build_prompt_package(pack_root=pack_root, max_cases=max_cases, seed=seed)
    _write_jsonl(out_dir / "prompt_package.jsonl", prompt_rows)
    _write_jsonl(out_dir / "arm_map_private.jsonl", private_rows)

    provider_unavailable = False
    missing_provider_key = None
    provider_errors: list[dict[str, Any]] = []
    answers: list[dict[str, Any]] = []
    provider_call_count = 0

    if run_live and provider_name == "stub":
        provider_errors.append({"error_type": "config_error", "error": "stub provider cannot be used with --run-live"})
    elif run_live and provider_name in PROVIDER_SPECS:
        env_key = PROVIDER_SPECS[provider_name]["env_key"]
        if not effective_env.get(env_key):
            provider_unavailable = True
            missing_provider_key = env_key
        else:
            answers, provider_call_count, provider_errors = _run_answers(
                prompt_rows=prompt_rows,
                run_live=True,
                provider_name=provider_name,
                env=effective_env,
                model=model,
                timeout=timeout,
                sleep_seconds=sleep_seconds,
                provider_callable=provider_callable,
            )
    elif run_live:
        provider_errors.append({"error_type": "config_error", "error": f"unknown provider {provider_name}"})
    else:
        answers, provider_call_count, provider_errors = _run_answers(
            prompt_rows=prompt_rows,
            run_live=False,
            provider_name=provider_name,
            env=effective_env,
            model=model,
            timeout=timeout,
            sleep_seconds=sleep_seconds,
            provider_callable=provider_callable,
        )

    _write_jsonl(out_dir / "model_answers.jsonl", answers)
    rows, judge_rows, wins = judge_answers(private_rows=private_rows, answers=answers)
    _write_jsonl(out_dir / "judge_scores.jsonl", judge_rows)
    if provider_errors:
        _write_jsonl(out_dir / "provider_errors.jsonl", provider_errors)

    raw_summary = _arm_summary(rows, "raw_json_baseline")
    skill_summary = _arm_summary(rows, "answer_skill_pack")
    arms = {"raw_json_baseline": raw_summary, "answer_skill_pack": skill_summary}
    delta = _delta(skill_summary, raw_summary)
    winner = "answer_skill_pack" if delta["avg_score"] > 0 else "tie" if delta["avg_score"] == 0 else "raw_json_baseline"
    verdict, live_claim_allowed = _quality_verdict(
        run_live=run_live,
        case_count=len(rows),
        wins=wins,
        arms=arms,
        delta=delta,
        provider_unavailable=provider_unavailable,
        provider_errors=provider_errors,
    )
    result = {
        "schema_version": "luban_lecture_answer_skill_pack_live_ab.v1",
        "pack_root": str(pack_root),
        "mode": "live_provider" if run_live else "deterministic_stub",
        "provider": provider_name,
        "model": model or (PROVIDER_SPECS.get(provider_name) or {}).get("model"),
        "seed": seed,
        "case_count": len(rows),
        "prompt_count": len(prompt_rows),
        "provider_call_count": provider_call_count,
        "provider_unavailable": provider_unavailable,
        "missing_provider_key": missing_provider_key,
        "provider_error_count": len(provider_errors),
        "winner": winner,
        "wins": wins,
        "arms": arms,
        "delta": delta,
        "verdict": verdict,
        "live_claim_allowed": live_claim_allowed,
        "outputs": {
            "prompt_package": str(out_dir / "prompt_package.jsonl"),
            "arm_map_private": str(out_dir / "arm_map_private.jsonl"),
            "model_answers": str(out_dir / "model_answers.jsonl"),
            "judge_scores": str(out_dir / "judge_scores.jsonl"),
            "finding": str(out_dir / "LIVE_AB_FINDING.md"),
        },
        "limitations": [
            "stub mode is not live model evidence",
            "judge is deterministic and should be complemented with blind human/model review before broad production claims",
            "lecture pack remains teaching answer-method context, not official score authority",
        ],
    }
    _write_json(out_dir / "live_ab_result.json", result)
    _write_jsonl(out_dir / "live_ab_case_rows.jsonl", rows)
    _write_finding(out_dir / "LIVE_AB_FINDING.md", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-cases", type=int, default=20)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--provider", choices=["stub", *PROVIDER_SPECS.keys()], default="stub")
    parser.add_argument("--model", default=None)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_live_ab(
        pack_root=args.pack_root,
        out_dir=args.out_dir,
        max_cases=args.max_cases,
        run_live=args.run_live,
        provider_name=args.provider,
        model=args.model,
        seed=args.seed,
        timeout=args.timeout,
        sleep_seconds=args.sleep_seconds,
    )
    printable = {
        key: value
        for key, value in result.items()
        if key not in {"outputs", "limitations"}
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
