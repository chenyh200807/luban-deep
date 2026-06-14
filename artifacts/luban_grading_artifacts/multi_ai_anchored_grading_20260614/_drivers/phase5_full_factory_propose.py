"""Phase 5 — full case-question compilation factory, STAGE 1 (propose + deterministic guard).

Merges Role ① (rule authoring, Phase-3 validated 1.0/1.0) and Role ② (prose segmentation,
Phase-4 pilot: must-not-mint 12/12 + Opus arbiter resolves granularity) into ONE
type-conditioned pass — the first-principles finding from the pilot was that the scoring-point
TYPE determines BOTH the segmentation granularity AND the grading rule, so they are one job.

Cost-aware (cost-aware-llm-pipeline discipline): the two cheap cross-family proposers
(DeepSeek + Qwen) run on EVERY case here; the expensive Opus arbiter (Stage 2) runs ONLY on
cases where the proposers disagree on type or segment count — the pilot showed ~1/3 disagree,
so we pay the costly model on a third of the bank, not all of it.

Every proposed segment passes a DETERMINISTIC must-not-mint guard (汉字 contiguous substring of
the official answer) — non-circular, no gold needed. Output is per-case (resumable; a timeout
never loses completed work). REVIEW-ONLY / candidate: no production write, no DB.
"""
from __future__ import annotations

import concurrent.futures as cf
import glob
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path("/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor")
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location(
    "deep_runner", REPO / "scripts/run_luban_rich_leaf_llm_deep_compile_runner.py")
RUN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RUN)

OBJDIR = REPO / "artifacts/luban_grading_artifacts/per_question_grading_object_full_compile_20260614/objects"
OUT = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory"
CASES_DIR = OUT / "propose_by_case"

PROPOSERS = [("deepseek", "提议员A"), ("dashscope", "提议员B")]

FACTORY_SYS = (
    "你是一级建造师建筑实务案例题评分知识编译员。给你一道案例题的题干、官方参考答案(可能是散文/顿号列表)、"
    "官方解析。你要一次性产出该题的【类型条件化评分知识】。\n"
    "第一步判类型 point_type:\n"
    " - list: 列举型('列出N项/还包括/还可采用:A、B、C'),按命中项数给分\n"
    " - flaw_correction: 不妥之处+正确做法,成对判分\n"
    " - process: 连续工序/做法论述句,整句为一个点\n"
    " - calculation: 计算题(有=、总工期、万元、网络图)\n"
    " - mixed: 同题内多种类型混合\n"
    " - single: 单一论断\n"
    "第二步按类型切原子采分点 segments(粒度由类型决定,不是越细越好):\n"
    " - list 型→每个并列项各成一个采分点(踩字判分需独立命中)\n"
    " - flaw_correction→'不妥之处'与对应'正确做法'各一个点,正确做法是完整论述时不得碎成子句\n"
    " - process→保留完整工序句,不按逗号碎切\n"
    "铁律 must-not-mint:每个 segment.text 必须是官方答案里的【逐字连续片段】,不得改写/增删字/近义替换。\n"
    "第三步授权判分规则:\n"
    " - list_rule.applies(是否列举型)+ total_items(官方并列总项数,直接数)\n"
    " - penalty_rule:题干是否含元规则('本问题X项,多答不得分'),含则给 exists/scope/text\n"
    " - 每个 segment 标 exact_term_required(踩字:近义/错位算不算)\n"
    "只输出 JSON,不要多余文字:\n"
    "{\"point_type\":\"<...>\",\"segments\":[{\"text\":\"逐字片段\",\"is_list_item\":true|false,\"exact_term_required\":true|false}],"
    "\"list_rule\":{\"applies\":true|false,\"total_items\":<int或null>},"
    "\"penalty_rule\":{\"exists\":true|false,\"scope\":\"<...>\",\"text\":\"<...>\"}}"
)


def _hanzi(text: str) -> str:
    return "".join(re.findall(r"[一-鿿]", text or ""))


def _full_official_answer(obj: dict) -> str:
    parts = []
    for sq in obj.get("sub_questions") or []:
        v = sq.get("official_sub_answer_verbatim")
        if v:
            parts.append(v)
    return "\n".join(parts)


def _propose(call, obj: dict) -> dict:
    oa = _full_official_answer(obj)
    payload = {
        "题干": (obj.get("stem") or "")[:1000],
        "官方参考答案": oa,
        "官方解析": (obj.get("official_analysis") or "")[:600],
    }
    messages = [
        {"role": "system", "content": FACTORY_SYS},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        result = call("factory", messages)
        obj_out = json.loads(result["content"])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160]}
    segs = obj_out.get("segments") or []
    oa_h = _hanzi(oa)
    minted = [s.get("text", "")[:30] for s in segs
              if _hanzi(s.get("text", "")) and _hanzi(s.get("text", "")) not in oa_h]
    return {
        "point_type": str(obj_out.get("point_type") or ""),
        "n_segments": len(segs),
        "segments": segs,
        "list_rule": obj_out.get("list_rule") or {},
        "penalty_rule": obj_out.get("penalty_rule") or {},
        "must_not_mint_ok": not minted,
        "minted": minted,
    }


def _process_case(obj_path: str, calls: dict) -> dict:
    obj = json.loads(Path(obj_path).read_text("utf-8"))
    qid = obj.get("question_id")
    out = {"case_file": Path(obj_path).name, "question_id": qid,
           "official_total_score": obj.get("official_total_score"),
           "prior_n_points": obj.get("scoring_point_count"),
           "official_answer": _full_official_answer(obj), "by_model": {}}
    for prov, _ in PROPOSERS:
        out["by_model"][prov] = _propose(calls[prov], obj)
    ds, qw = out["by_model"]["deepseek"], out["by_model"]["dashscope"]
    type_disagree = ds.get("point_type") != qw.get("point_type")
    count_disagree = abs(ds.get("n_segments", 0) - qw.get("n_segments", 0)) > 1
    mint_fail = not (ds.get("must_not_mint_ok") and qw.get("must_not_mint_ok"))
    out["needs_arbiter"] = bool(type_disagree or count_disagree or mint_fail)
    out["arbiter_reason"] = {"type_disagree": type_disagree, "count_disagree": count_disagree,
                             "mint_fail": mint_fail}
    return out


def main() -> int:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    calls = {}
    for prov, _ in PROPOSERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=120, max_tokens=2000)
        if c is None:
            raise SystemExit(f"{prov} API key missing")
        calls[prov] = c

    all_objs = sorted(glob.glob(str(OBJDIR / "*.json")))
    # resumable: skip cases already written
    todo = [p for p in all_objs if not (CASES_DIR / (Path(p).stem + ".json")).exists()]
    print(f"total={len(all_objs)} done={len(all_objs)-len(todo)} todo={len(todo)}", flush=True)

    def work(p):
        try:
            r = _process_case(p, calls)
        except Exception as exc:  # noqa: BLE001
            r = {"case_file": Path(p).name, "fatal_error": str(exc)[:200]}
        (CASES_DIR / (Path(p).stem + ".json")).write_text(
            json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
        return r.get("needs_arbiter", None)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for _ in ex.map(work, todo):
            done += 1
            if done % 20 == 0:
                print(f"  progress {done}/{len(todo)}", flush=True)

    # aggregate
    results = [json.loads(p.read_text("utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]
    valid = [r for r in results if "fatal_error" not in r and r.get("by_model")]
    mint_clean = sum(1 for r in valid
                     if r["by_model"]["deepseek"].get("must_not_mint_ok")
                     and r["by_model"]["dashscope"].get("must_not_mint_ok"))
    needs_arb = sum(1 for r in valid if r.get("needs_arbiter"))
    type_dist = {}
    for r in valid:
        t = r["by_model"]["deepseek"].get("point_type", "?")
        type_dist[t] = type_dist.get(t, 0) + 1
    summary = {
        "schema": "luban_full_factory_propose.v1", "generated_at_date": "2026-06-14",
        "n_cases": len(valid), "fatal_errors": len(results) - len(valid),
        "both_models_must_not_mint_clean": f"{mint_clean}/{len(valid)}",
        "needs_opus_arbiter": f"{needs_arb}/{len(valid)}",
        "needs_arbiter_pct": round(needs_arb / len(valid), 3) if valid else None,
        "point_type_distribution_deepseek": dict(sorted(type_dist.items())),
        "note": "Stage 2 = Opus arbiter on the needs_arbiter cohort only (cost-aware).",
    }
    (OUT / "propose_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
