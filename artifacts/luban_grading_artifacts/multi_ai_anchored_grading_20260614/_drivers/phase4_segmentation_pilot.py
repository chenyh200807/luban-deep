"""Phase 4 PILOT — can the multi-AI team segment prose answers the deterministic
splitter fail-closes on, WITHOUT minting?

Role ② of the team (distinct from Role ①, rule authoring, which Phase 3 validated):
51% of the full-bank compile collapsed to ≤1 point because the deterministic splitter
correctly refuses to cut 顿号/分号 prose lists ('内容包括 A、B、C、D 等') — cutting on 顿号
risks shredding terms. An LLM CAN segment these. But an LLM can also paraphrase/mint, which
would violate the per_question_grading_object's must-not-mint invariant. This pilot tests, on
a 12-case sample, whether multi-AI prose segmentation holds two STRUCTURAL guards (no human
gold needed, non-circular):

  * must-not-mint: every returned segment's 汉字 sequence is a CONTIGUOUS substring of the
    official answer's 汉字 sequence (the segment content is really there, not invented).
  * must-not-drop: the union of segments covers ≥90% of the answer's 汉字 (nothing silently lost).

Plus cross-family agreement on segment count (DeepSeek vs Qwen within ±1) as a stability signal.
If both guards hold across the sample with cross-family agreement, Role ② is safe to scale to
the full 91 collapsed cases (then Codex/Opus adversarial spot-check before any production wire).
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
OUT = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614"

SEGMENTERS = [("deepseek", "切分员A"), ("dashscope", "切分员B")]

SEG_SYS = (
    "你是一级建造师建筑实务案例题评分专家。给你一道题的【官方参考答案】(散文/顿号列表形式),"
    "把它切成若干个【原子采分点】——即官方答案里每一个独立的并列要点/做法/检查项各成一个采分点。"
    "铁律(违反则判分库 must-not-mint 失效):每个采分点必须是官方答案里的【逐字连续片段】,"
    "不得改写、不得近义替换、不得增删任何字、不得跨顿号合并两个并列项。一个并列项=一个采分点。"
    "引导语(如'还应检查'、'内容包括'、'基本条件:')可保留在其所属第一个采分点里或单独成点,但本体文字必须逐字。"
    "只输出 JSON,不要多余文字: {\"segments\":[\"逐字片段1\",\"逐字片段2\", ...]}"
)


def _hanzi(text: str) -> str:
    return "".join(re.findall(r"[一-鿿]", text or ""))


def _segment(call, official_answer: str) -> dict:
    messages = [
        {"role": "system", "content": SEG_SYS},
        {"role": "user", "content": json.dumps({"官方参考答案": official_answer}, ensure_ascii=False)},
    ]
    try:
        result = call("segment", messages)
        obj = json.loads(result["content"])
        segs = [str(s) for s in (obj.get("segments") or []) if str(s).strip()]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160], "segments": []}
    return {"segments": segs}


def _check_guards(segments: list[str], official_answer: str) -> dict:
    """Deterministic must-not-mint + must-not-drop guards (non-circular, no gold)."""
    oa_h = _hanzi(official_answer)
    minted = []  # segments whose 汉字 are NOT a contiguous substring of the answer
    for s in segments:
        sh = _hanzi(s)
        if sh and sh not in oa_h:
            minted.append(s[:40])
    # coverage: fraction of answer 汉字 covered by the union of segment 汉字 spans
    covered = bytearray(len(oa_h))
    for s in segments:
        sh = _hanzi(s)
        if not sh:
            continue
        start = oa_h.find(sh)
        while start != -1:
            for i in range(start, start + len(sh)):
                covered[i] = 1
            start = oa_h.find(sh, start + 1)
    cov = sum(covered) / len(oa_h) if oa_h else 0.0
    return {
        "n_segments": len(segments),
        "minted_segments": minted,
        "must_not_mint_ok": not minted,
        "coverage": round(cov, 4),
        "must_not_drop_ok": cov >= 0.90,
    }


def _pick_cases(n: int = 12) -> list[dict]:
    enum_re = re.compile(r"(包括|包含|应有|有[:：]|主要有|分别为)")
    calc_re = re.compile(r"(=|总工期|网络图|关键线路|T=|万元|工期为|\d+\s*个月|\d+\s*天)")
    cands = []
    for f in sorted(glob.glob(str(OBJDIR / "*.json"))):
        d = json.loads(Path(f).read_text("utf-8"))
        sqs = d.get("sub_questions") or []
        pts = [p for sq in sqs for p in (sq.get("scoring_points") or [])]
        if len(pts) != 1:
            continue
        oa = pts[0].get("atomic_official_slice") or ""
        hz = len(_hanzi(oa))
        if enum_re.search(oa) and oa.count("、") >= 2 and not calc_re.search(oa) and hz >= 30:
            cands.append({"case": Path(f).name, "qid": d.get("question_id"), "official_answer": oa,
                          "dunhao": oa.count("、"), "hanzi": hz})
    # spread the sample across 顿号-density buckets for diversity
    cands.sort(key=lambda c: c["dunhao"])
    if len(cands) <= n:
        return cands
    step = len(cands) / n
    return [cands[int(i * step)] for i in range(n)]


def main() -> int:
    cases = _pick_cases(12)
    calls = {}
    for prov, _ in SEGMENTERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=120, max_tokens=1200)
        if c is None:
            raise SystemExit(f"{prov} API key missing")
        calls[prov] = c

    def work(case):
        oa = case["official_answer"]
        out = {"case": case["case"], "qid": case["qid"], "dunhao": case["dunhao"], "hanzi": case["hanzi"],
               "official_answer": oa, "by_model": {}}
        for prov, _ in SEGMENTERS:
            seg = _segment(calls[prov], oa)
            guard = _check_guards(seg.get("segments") or [], oa)
            out["by_model"][prov] = {**seg, **guard}
        ds = out["by_model"]["deepseek"]
        qw = out["by_model"]["dashscope"]
        out["cross_family_count_delta"] = abs(ds.get("n_segments", 0) - qw.get("n_segments", 0))
        return out

    results = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(work, cases):
            results.append(r)

    # aggregate metrics
    n = len(results)
    mint_clean = sum(1 for r in results if all(r["by_model"][p]["must_not_mint_ok"] for p, _ in SEGMENTERS))
    drop_clean = sum(1 for r in results if all(r["by_model"][p]["must_not_drop_ok"] for p, _ in SEGMENTERS))
    agree = sum(1 for r in results if r["cross_family_count_delta"] <= 1)
    avg_segs = round(sum(r["by_model"]["deepseek"].get("n_segments", 0) for r in results) / n, 2) if n else 0
    metrics = {
        "n_cases": n,
        "both_models_must_not_mint_clean": f"{mint_clean}/{n}",
        "both_models_must_not_drop_clean": f"{drop_clean}/{n}",
        "cross_family_count_agree_within_1": f"{agree}/{n}",
        "avg_segments_deepseek": avg_segs,
        "pilot_pass_rule": "must-not-mint 必须 n/n(零mint),must-not-drop ≥0.9 多数,跨家族±1 多数 → 角色②可放全量",
        "pilot_passes": (mint_clean == n and drop_clean >= n - 2 and agree >= n - 2),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase4_segmentation_pilot.json").write_text(json.dumps({
        "schema": "luban_multi_ai_segmentation_pilot.v1", "generated_at_date": "2026-06-14",
        "classification": {"pilot_only": True, "task": "prose answer segmentation (Role ②)",
                           "guards": "deterministic must-not-mint + must-not-drop (non-circular, no gold)"},
        "metrics": metrics, "results": results,
    }, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
