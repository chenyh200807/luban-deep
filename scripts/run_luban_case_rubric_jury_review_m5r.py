"""M5R — sanctioned real LLM-jury rerun of the M4 packets with >=3 heterogeneous models.

Live providers loaded from the project .env files (DeepSeek / DashScope-Qwen / BigModel-GLM).
gpt55 / opus48 stay provider_unavailable (no OpenAI/Anthropic key). Reuses the M5 adjudication
protocol + build_m5 (models= injected). NEVER prints secrets, NEVER fabricates a vote, NEVER
uses the 485 cache, NEVER emits a formal registry. A model call/parse failure -> provider_unavailable.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from scripts.run_luban_case_rubric_jury_review_m5 import build_m5

REPO = Path(__file__).resolve().parents[1]
M5R_DIR = REPO / "artifacts/luban_grading_artifacts/case_rubric_jury_review_m5r_20260604"
ENV_FILES = [REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")]

JURY_MODELS = ["gpt55", "opus48", "deepseek_v4", "qwen37", "glm45"]
# jury_model -> (key_env, base_url, model_id). gpt55/opus48 intentionally absent -> unavailable.
LIVE = {
    "deepseek_v4": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat"),
    "qwen37": ("DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "glm45": ("BIGMODEL_API_KEY", "https://open.bigmodel.cn/api/paas/v4", "glm-4-plus"),
}


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in ENV_FILES:
        try:
            for line in Path(p).read_text("utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            continue
    return env


_ENV = _load_env()


def _prompt(packet: dict[str, Any]) -> str:
    pts = [{"point_id": p.get("point_id"), "label": p.get("label"), "policy_type": p.get("policy_type"),
            "max_score": p.get("max_score"), "source_status": p.get("source_status"),
            "auto_certifiable": p.get("auto_certifiable")} for p in packet.get("scoring_point_candidates") or []]
    return (
        "你是一建《建筑实务》案例题阅卷采分点复核陪审员（LLM jury，非真人）。复核以下采分点候选的质量，"
        "只判断采分点/政策/锚点是否可执行，不得新造教材来源，不得把 weak 来源升级为 verified。\n"
        "规则：exact_required 取严（近义不放宽 required_terms）；calculation 缺 spec 不能 published；"
        "list_rule 缺 denominator/item_set 不能 published；source_status=weak 的点 textbook_anchor_ok 必须 false。\n\n"
        f"question_id: {packet.get('question_id')}\n题干: {(packet.get('question_text') or '')[:800]}\n"
        f"official_answer: {(packet.get('official_answer') or '')[:1200]}\n"
        f"scoring_point_candidates: {json.dumps(pts, ensure_ascii=False)}\n"
        f"policy_gaps: {json.dumps(packet.get('policy_gaps') or [], ensure_ascii=False)}\n\n"
        "只输出 JSON（不要解释、不要 markdown 代码块），schema：\n"
        '{"point_reviews":[{"point_id":"","valid_scoring_point":true,"textbook_anchor_ok":true,'
        '"required_terms_ok":true,"missing_point_risk":"low|medium|high","over_credit_risk":"low|medium|high",'
        '"decision":"accept|revise|reject|needs_po_review","rationale":"..."}],'
        '"question_level_decision":"publish_candidate|draft_candidate|reject|needs_po_review",'
        '"question_level_rationale":"..."}'
    )


def _parse_json(txt: str) -> dict[str, Any] | None:
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def real_vote_fn(model: str, packet: dict[str, Any]) -> dict[str, Any]:
    if model not in LIVE:
        return {"model": model, "status": "provider_unavailable",
                "reason": f"no live provider key for {model} (OpenAI/Anthropic not configured)",
                "votes_fabricated": False}
    # Resume: reuse a real vote already produced by THIS M5R run (not the 485 cache) so an
    # interrupted run only re-calls the missing (question, model) pairs.
    cached = M5R_DIR / "model_votes" / f"{packet.get('question_id')}__{model}.json"
    if cached.exists():
        try:
            v = json.loads(cached.read_text("utf-8"))
            if isinstance(v.get("point_reviews"), list) and v.get("votes_fabricated") is False:
                return v
        except Exception:
            pass
    key_env, base, model_id = LIVE[model]
    key = _ENV.get(key_env)
    if not key:
        return {"model": model, "status": "provider_unavailable",
                "reason": f"{key_env} missing in .env", "votes_fabricated": False}
    try:
        cli = OpenAI(api_key=key, base_url=base, timeout=60.0)
        t0 = time.time()
        r = cli.chat.completions.create(model=model_id, temperature=0, max_tokens=1400,
                                        messages=[{"role": "user", "content": _prompt(packet)}])
        parsed = _parse_json(r.choices[0].message.content or "")
        if not parsed or not isinstance(parsed.get("point_reviews"), list):
            return {"model": model, "status": "provider_unavailable",
                    "reason": "vote_parse_failed", "votes_fabricated": False}
        return {"model": model, "model_id": model_id, "reviewer_type": "llm_jury",
                "votes_fabricated": False, "latency_s": round(time.time() - t0, 2),
                "point_reviews": parsed.get("point_reviews") or [],
                "question_level_decision": parsed.get("question_level_decision"),
                "question_level_rationale": parsed.get("question_level_rationale")}
    except Exception as e:  # noqa: BLE001 — fail-closed, never fabricate
        return {"model": model, "status": "provider_unavailable",
                "reason": f"live_call_error:{type(e).__name__}", "votes_fabricated": False}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(M5R_DIR))
    args = ap.parse_args()
    r = build_m5(Path(args.out_dir), vote_fn=real_vote_fn, models=JURY_MODELS)
    s = r["sim"]
    print(f"M5R -> {args.out_dir}")
    print(f"  input={s['input_questions']} publish_ready={s['publish_ready_after_jury']} "
          f"draft={s['draft_after_jury']} needs_po_review={s['needs_po_review']} rejected={s['rejected']} "
          f"quorum_blocked={s['quorum_blocked']}")
    print(f"  provider_unavailable={s['provider_unavailable_counts']}")


if __name__ == "__main__":
    main()
