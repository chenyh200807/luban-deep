"""Phase 7 STAGE A — multi-AI team closes the 51-segment human-review queue.

The Phase-6 顿号-heuristic flagged 51 is_list_item segments that still hold ≥2 顿号 — an UPPER
BOUND. The real question per segment is binary and semantic, with a real anchor (the official
answer structure + 踩字 grading): is each 顿号-item an INDEPENDENTLY-scorable 规范术语/做法
(→ atomize) or are they JOINT sub-conditions of ONE scoring point (→ keep, e.g. a load
combination G1、G2、G3 of one 验算)? Some are mis-flagged prose (→ not_a_list).

Division of labour (capability-matched, the user's mandate — no human expert, top AIs instead):
  Stage A (this file): DeepSeek + Qwen — cross-family proposers, each classifies + (if atomize)
                       splits into verbatim items, anchored to the FULL official answer.
  Stage B (Codex):     adversarial refuter — challenges the A/B consensus in one batched pass.
  Stage C (Opus 4.8):  anchor-verify + final ruling on the contested set.

Every proposed split is must-not-mint guarded (汉字 contiguous substring) deterministically.
Non-circular note: no human gold exists for this judgment; the team CONVERGES it under
cross-family + adversarial pressure and NAMES the residual contested set honestly (not "closed").
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

FAC = REPO / "artifacts/luban_grading_artifacts/multi_ai_anchored_grading_20260614/phase5_factory"
OUT = FAC / "stage3_atomization"
PROPOSERS = [("deepseek", "原子化提议员A"), ("dashscope", "原子化提议员B")]

ATOM_SYS = (
    "你是一级建造师建筑实务案例题评分专家。给你官方答案里的一个【采分点片段】(它含多个顿号),"
    "以及该题完整官方答案做上下文。判断这个片段里顿号分隔的各项,是【A 各自独立的踩字采分项】"
    "(每项是一个独立的规范术语/做法,学生命中一项就该独立得分,如'五牌一图'各块牌、各检测方法、各道工序),"
    "还是【B 同一个采分点的联合子条件】(各项合起来才构成一个判断,拆开无意义,如某验算项的荷载组合"
    "'G1、G2、G3'、某检查的'班前/班中/班后'三阶段、一句话里的并列定语),"
    "还是【C 误标:这根本不是并列清单而是一句散文】。\n"
    "判据锚定踩字语义:能不能想象判分时'命中这项+0.x分,漏这项-0.x分'独立成立?能=A;各项是一个东西的"
    "组成部分/修饰=B;整体是论述句=C。\n"
    "若判 A,给出逐字拆分 items(每项必须是片段里的【逐字连续子串】,不得改写/增删字)。\n"
    "只输出 JSON: {\"verdict\":\"A_atomize|B_keep|C_not_a_list\",\"items\":[\"逐字项1\",...],"
    "\"reason\":\"<一句:为何独立/联合/散文>\"}"
)


def _hanzi(t: str) -> str:
    return "".join(re.findall(r"[一-鿿]", t or ""))


def _classify(call, segment: str, official: str) -> dict:
    payload = {"待判采分点片段": segment, "该题完整官方答案(上下文)": official[:1200]}
    messages = [{"role": "system", "content": ATOM_SYS},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    try:
        obj = json.loads(call("atom", messages)["content"])
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "error", "items": [], "reason": str(exc)[:120]}
    items = [str(x) for x in (obj.get("items") or []) if str(x).strip()]
    seg_h = _hanzi(segment)
    minted = [x[:24] for x in items if _hanzi(x) and _hanzi(x) not in seg_h]
    return {"verdict": str(obj.get("verdict") or "error"), "items": items,
            "reason": str(obj.get("reason") or ""), "minted": minted, "mnm_ok": not minted}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    queue = json.loads((FAC / "spotcheck_and_review_queue.json").read_text("utf-8")
                       )["HUMAN_REVIEW_QUEUE_under_atomized_list_segments"]["items"]
    # need the FULL segment text (queue truncates to 80) + official answer per case
    official = {}
    full_segs = {}  # case_file -> list of full is_list_item segments
    for f in glob.glob(str(FAC / "propose_by_case" / "*.json")):
        d = json.loads(Path(f).read_text("utf-8"))
        official[d["case_file"]] = d.get("official_answer", "")
    candidate = json.loads((FAC / "full_factory_candidate.json").read_text("utf-8"))["cases"]
    seg_by_case = {}
    for rec in candidate:
        seg_by_case.setdefault(rec["case_file"], []).extend(
            s["text"] for s in (rec.get("segments") or []) if s.get("is_list_item"))

    # rebuild the 51 with FULL text by matching the truncated prefix
    items = []
    for q in queue:
        cfile = q["case_file"]
        pref = q["segment"]
        full = next((s for s in seg_by_case.get(cfile, []) if s.startswith(pref[:20])), pref)
        items.append({"case_file": cfile, "segment": full, "official": official.get(cfile, "")})

    calls = {}
    for prov, _ in PROPOSERS:
        c = RUN._openai_compat_provider(provider=prov, model=None, timeout_s=90, max_tokens=700)
        if c is None:
            raise SystemExit(f"{prov} key missing")
        calls[prov] = c

    def work(it):
        out = {"case_file": it["case_file"], "segment": it["segment"], "by_model": {}}
        for prov, _ in PROPOSERS:
            out["by_model"][prov] = _classify(calls[prov], it["segment"], it["official"])
        ds, qw = out["by_model"]["deepseek"], out["by_model"]["dashscope"]
        out["consensus_verdict"] = ds["verdict"] if ds["verdict"] == qw["verdict"] else None
        out["contested"] = out["consensus_verdict"] is None
        return out

    results = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(work, items):
            results.append(r)

    n = len(results)
    consensus = sum(1 for r in results if not r["contested"])
    vd = {}
    for r in results:
        v = r["consensus_verdict"] or "CONTESTED"
        vd[v] = vd.get(v, 0) + 1
    summary = {"n_segments": n, "cross_family_consensus": f"{consensus}/{n}",
               "consensus_verdict_distribution": vd,
               "contested_to_opus": [r["segment"][:50] for r in results if r["contested"]]}
    (OUT / "stageA_propose.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
