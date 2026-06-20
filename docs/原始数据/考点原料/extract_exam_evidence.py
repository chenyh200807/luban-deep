#!/usr/bin/env python3
"""真题证据确定性抽取器 — 给生产镜头喂真 ground truth(答案/解析/分值),不靠LLM.

用法: python extract_exam_evidence.py <考点ID> "<关键词|管道分隔>"
扫真考卷 FINAL_CLEANED_EXAM_V20XX.json, 按关键词命中题, 抽 {年份,题号,题型,题干,correct_answer,analysis,score}.
存 _<ID>_exam_evidence.json (=唯一允许真题锚源, 供 produce_lens.py / R7 构造).
"""
import sys, re, json, glob, os
ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"

def main():
    cid, kw = sys.argv[1], re.compile(sys.argv[2])
    out = []
    for f in sorted(glob.glob(ROOT + "/docs/原始数据/2026_副本/题库/**/FINAL_CLEANED_EXAM_V*.json", recursive=True)):
        yr = re.search(r"V(\d{4})", f).group(1)
        d = json.load(open(f, encoding="utf-8"))
        for c in d.get("chunks", []):
            anchor = c.get("source_meta", {}).get("original_anchor", "")
            for e in c.get("exercises", []):
                qd = e.get("question_data", {})
                blob = " ".join([str(qd.get("stem","")), str(qd.get("analysis","")), str(c.get("content_markdown",""))])
                if not kw.search(blob): continue
                out.append({
                    "year": yr, "题号": anchor, "type": e.get("type",""),
                    "stem": str(qd.get("stem",""))[:400],
                    "correct_answer": str(qd.get("correct_answer",""))[:600],
                    "analysis": str(qd.get("analysis",""))[:800],
                    "score": qd.get("score"),
                    "logic_chain": str(qd.get("logic_chain",""))[:300] if qd.get("logic_chain") else None,
                })
    res = {"考点": cid, "真题命中": len(out), "evidence": out}
    p = ROOT + f"/docs/原始数据/考点原料/_{cid}_exam_evidence.json"
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    yrs = sorted(set(x["year"] for x in out))
    cases = sum(1 for x in out if x["type"]=="case_study")
    print(f"{cid}: 真题命中 {len(out)} (案例 {cases}), 覆盖年份 {yrs} → {os.path.basename(p)}")
    print("案例题样本(带官方答案/解析/分值):")
    for x in [e for e in out if e["type"]=="case_study"][:2]:
        print(f"  {x['year']}{x['题号']} score={x['score']} | 答案:{x['correct_answer'][:50]} | 解析:{x['analysis'][:50]}")

if __name__ == "__main__":
    main()
