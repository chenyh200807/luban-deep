"""M5B live LLM jury — 3 real jurors (GPT via Codex CLI, DeepSeek, Qwen).

Runs the actual rubric-review jury over the top-priority M5B manifest questions.
GPT5.5 is routed through the local Codex CLI (no OPENAI_API_KEY available); DeepSeek
and Qwen run through the project's llm factory with keys loaded from the user's .env
(values never printed). The jury is REVIEW evidence, never a textbook source: it cannot
upgrade a weak source to verified and cannot mint a textbook_quote.

Cost note: Codex is heavy (~30k+ tokens/call), so this defaults to a small --limit
pilot. Scale up only after reviewing the pilot.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
M5B = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5b_20260604"
OUT_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_live_m5b_20260604"
ENV_FILE = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _load_env() -> dict[str, str]:
    env = {}
    for line in ENV_FILE.read_text("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"):
        if env.get(k):
            os.environ[k] = env[k]
    return env


def _extract_json(text: str) -> dict[str, Any] | None:
    # last balanced {...} block in the output (codex prints hook noise then the JSON)
    depth = 0
    start = -1
    best = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                best = text[start:i + 1]
    if not best:
        return None
    try:
        return json.loads(best)
    except Exception:
        return None


def _jury_prompt(q: dict[str, Any]) -> str:
    pts = [{"point_id": p["point_id"], "policy_type": p["policy_type"], "max_score": p["max_score"],
            "label": p.get("label"), "auto_certifiable": p["auto_certifiable"], "source_status": p["source_status"],
            "verified_anchor": (p["verified_anchors"][0]["textbook_quote"] if p["verified_anchors"] else None)}
           for p in q["scoring_points"]]
    return (
        "你是独立阅卷复核模型（model jury，不是真人，不是 PO）。复核下面一建建筑实务案例题的采分点结构。"
        "规则：exact_required 从严，近义不放宽；不得编造 textbook_quote；不得把 weak source 升 verified；"
        "calculation 缺 spec 不能 publish；list_rule 缺 denominator 不能 publish。"
        "只输出一行 JSON：{\"question_id\":\"" + q["question_id"] + "\",\"point_reviews\":"
        "[{\"point_id\":\"\",\"valid_scoring_point\":true,\"policy_type_ok\":true,"
        "\"textbook_anchor_supports_point\":true,\"over_credit_risk\":\"low|medium|high\","
        "\"decision\":\"accept|revise|reject|needs_po_review\",\"rationale\":\"\"}],"
        "\"question_decision\":\"publish_candidate|draft_candidate|reject|needs_po_review\",\"question_rationale\":\"\"}\n"
        f"题干：{q['stem'][:600]}\n官方答案：{q['official_answer'][:400]}\n采分点：{json.dumps(pts, ensure_ascii=False)}"
    )


async def _vote_factory(model: str, prompt: str, *, api_key=None, base_url=None, binding=None) -> dict[str, Any]:
    from deeptutor.services.llm.factory import complete
    t = time.monotonic()
    try:
        out = await asyncio.wait_for(complete(prompt, model=model, api_key=api_key, base_url=base_url,
                                              binding=binding, max_retries=1, max_tokens=1200, temperature=0), timeout=90)
        v = _extract_json(out)
        return {"ok": bool(v), "vote": v, "latency_ms": round((time.monotonic() - t) * 1000),
                "error_class": None if v else "unparseable"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "vote": None, "latency_ms": round((time.monotonic() - t) * 1000), "error_class": type(exc).__name__}


def _vote_codex(prompt: str) -> dict[str, Any]:
    t = time.monotonic()
    try:
        proc = subprocess.run(["codex", "exec", "--skip-git-repo-check", prompt],
                              capture_output=True, text=True, timeout=240)
        v = _extract_json(proc.stdout)
        return {"ok": bool(v), "vote": v, "latency_ms": round((time.monotonic() - t) * 1000),
                "error_class": None if v else "unparseable"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "vote": None, "latency_ms": round((time.monotonic() - t) * 1000), "error_class": type(exc).__name__}


def _adjudicate(q: dict[str, Any], votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    live = {m: v["vote"] for m, v in votes.items() if v.get("ok") and v.get("vote")}
    n = len(live)
    point_rows = []
    any_unsupported = False
    for p in q["scoring_points"]:
        pid = p["point_id"]
        decs = []
        for m, vote in live.items():
            pr = next((x for x in (vote.get("point_reviews") or []) if x.get("point_id") == pid), None)
            if pr:
                decs.append(pr.get("decision"))
                if p["auto_certifiable"] and pr.get("textbook_anchor_supports_point") is False:
                    any_unsupported = True
        accepts = sum(1 for d in decs if d == "accept")
        final = "accept" if accepts >= 2 else ("needs_po_review" if decs else "needs_po_review")
        point_rows.append({"point_id": pid, "policy_type": p["policy_type"], "votes": decs,
                           "accepts": accepts, "final": final})
    pub_votes = sum(1 for v in live.values() if v.get("question_decision") == "publish_candidate")
    if n < 3:
        qd = "needs_po_review"  # quorum lost mid-run
    elif any_unsupported:
        qd = "needs_po_review"
    elif q["m5a_status"] == "published_candidate" and pub_votes >= 2:
        qd = "publish_candidate"
    else:
        qd = "draft_candidate" if q["m5a_status"] != "needs_po_review" else "needs_po_review"
    return {"question_id": q["question_id"], "m5a_status": q["m5a_status"], "live_jurors": n,
            "question_decision": qd, "publish_votes": pub_votes, "any_source_unsupported": any_unsupported,
            "point_decisions": point_rows}


def main(limit: int = 3, only_status: str | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "model_votes").mkdir(exist_ok=True)
    env = _load_env()
    manifest = json.loads((M5B / "jury_input_manifest.json").read_text("utf-8"))
    if only_status:
        manifest = [m for m in manifest if m["m5a_status"] == only_status]
    questions = manifest[:limit]

    # resume: reuse adjudications already computed (saves Codex calls/tokens)
    adj_path = OUT_DIR / "jury_adjudication_live.json"
    meta_path = OUT_DIR / "provider_votes_meta.json"
    adjudications = json.loads(adj_path.read_text("utf-8")) if adj_path.exists() else []
    all_votes_meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else []
    done = {a["question_id"] for a in adjudications}
    questions = [q for q in questions if q["question_id"] not in done]

    for q in questions:
        prompt = _jury_prompt(q)
        votes = {}
        votes["deepseek_v4"] = asyncio.run(_vote_factory("deepseek-chat", prompt))
        votes["qwen37"] = asyncio.run(_vote_factory("qwen-plus", prompt, api_key=env.get("DASHSCOPE_API_KEY"),
                                                    base_url=DASHSCOPE_BASE, binding="openai_compat"))
        votes["gpt55"] = _vote_codex(prompt)
        for m, v in votes.items():
            if v.get("vote"):
                (OUT_DIR / "model_votes" / f"{q['question_id']}__{m}.json").write_text(
                    json.dumps({"model": m, "reviewer_type": "llm_jury", "votes_fabricated": False, **v["vote"]},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            all_votes_meta.append({"question_id": q["question_id"], "model": m, "ok": v["ok"],
                                   "latency_ms": v["latency_ms"], "error_class": v["error_class"]})
        adjudications.append(_adjudicate(q, votes))

    summary = {
        "limit": limit, "only_status": only_status, "questions_reviewed": len(adjudications),
        "newly_reviewed_this_run": len(questions),
        "jurors": ["gpt55(codex)", "deepseek_v4", "qwen37"], "votes_fabricated": False,
        "sanctioned_cache_used": False, "formal_registry_emitted": False,
        "publish_candidate": sum(1 for a in adjudications if a["question_decision"] == "publish_candidate"),
        "draft_candidate": sum(1 for a in adjudications if a["question_decision"] == "draft_candidate"),
        "needs_po_review": sum(1 for a in adjudications if a["question_decision"] == "needs_po_review"),
        "quorum_per_question": [a["live_jurors"] for a in adjudications],
    }
    _dump("provider_votes_meta.json", all_votes_meta)
    _dump("jury_adjudication_live.json", adjudications)
    _dump("jury_live_summary.json", summary)
    print(f"live jury: reviewed={len(questions)} quorum={summary['quorum_per_question']} "
          f"pub={summary['publish_candidate']} draft={summary['draft_candidate']} needs_po={summary['needs_po_review']}")
    print(f"-> {OUT_DIR}")


def _dump(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--only-status", default=None)
    args = ap.parse_args()
    main(limit=args.limit, only_status=args.only_status)
