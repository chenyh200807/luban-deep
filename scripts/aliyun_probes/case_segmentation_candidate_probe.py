# -*- coding: utf-8 -*-
"""Read-only Aliyun harness: DeepSeek segments 5 priority qids by sub-question.
Produces proposed_sub_no CANDIDATES only (教研 verdict is truth; LLM never越权).
Reads the container's deployed compiled rubric; no DB write, no /app mutation."""
import os, json, asyncio, functools
from deeptutor.services.llm.factory import complete

RUBRIC="/app/deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"
QIDS=["EXAM_1A434000_P0011_01::E0","EXAM_1A434000_P0010_02::E0","EXAM_1A434000_P0014_02::E0",
      "EXAM_1A434000_P0013_01::E0","EXAM_1A434000_P0017_01::E1"]

def load():
    d=json.load(open(RUBRIC,encoding="utf-8")); g={}
    for r in d["records"]: g.setdefault(r["qid"],[]).append(r)
    return g

def prompt(qid,pts):
    lines="\n".join("  %s: %s"%(p["point_id"].split("::")[-1],p["text"]) for p in pts)
    return ("下面是一道一建建筑实务**大题**的全部采分点,它把**多个小问**的采分点揉在了一个 qid 下。\n"
        "请只按**小问归属**给每个采分点分组,输出每个采分点的 proposed_sub_no(小问序号,从1开始;\n"
        "同一小问同号)。不要改写采分点、不要判分、不要新增采分点——你只做分段归组。\n"
        "如果某个采分点本身还能再拆成更细的原子点,split_suggestion 填简短建议,否则填 \"\"。\n\n"
        "【采分点(短id: 文本)】\n%s\n\n"
        '严格 JSON 输出:{"groups":[{"pid":"<短id>","proposed_sub_no":<int>,"split_suggestion":"<...>"}]}。只输出 JSON。'%lines)

def parse(raw):
    s=raw.strip()
    if s.startswith("```"): s=s.split("```",2)[1].lstrip("json").strip().strip("`").strip()
    a,b=s.find("{"),s.rfind("}"); return json.loads(s[a:b+1]).get("groups") or []

async def one(cf,key,p):
    return await cf(prompt=p,system_prompt="You output only strict JSON.",model="deepseek-chat",api_key=key,max_retries=1,temperature=0)

def main():
    key=os.environ.get("DEEPSEEK_API_KEY")
    cf=functools.partial(complete,base_url="https://api.deepseek.com",binding="deepseek")
    g=load(); out={}
    for qid in QIDS:
        pts=g.get(qid) or []
        try:
            groups=parse(asyncio.run(one(cf,key,prompt(qid,pts))))
        except Exception as e:
            print("SEG %s ERROR %r"%(qid,e)); out[qid]={"error":str(e)}; continue
        subs=sorted({x.get("proposed_sub_no") for x in groups if x.get("proposed_sub_no") is not None})
        out[qid]={"n_points":len(pts),"n_subs":len(subs),"groups":groups}
        print("%s: %d点 → %d 小问候选 %s"%(qid,len(pts),len(subs),subs))
    print("=== SEG RESULT JSON ==="); print(json.dumps(out,ensure_ascii=False))

main()
