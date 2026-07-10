# -*- coding: utf-8 -*-
"""Self-contained read-only harness: real DeepSeek → distractor gen → RTG gates.
Runs inside the deployed deeptutor container. Imports ONLY deployed modules
(llm.factory.complete + error_codes.ERROR_CODE_REGISTRY); F16 points + generator
+ RTG gate logic are inlined (mirrors the feat-branch modules verbatim).
Read-only: no DB write, no /app mutation."""
import os, re, json, asyncio, functools, unicodedata

from deeptutor.services.llm.factory import complete
from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

# ── F16 起鼓割补 dev anchor (7 atomized points; live-validated) ──
POINTS = [
    {"id":"a1","st":"用刀将鼓泡卷材割开,放出鼓泡内气体","rt":["割开","放气"],"sc":0.25},
    {"id":"a2","st":"擦干水分","rt":["擦干"],"sc":0.15},
    {"id":"a3","st":"清除旧胶结料","rt":["清除旧胶结料"],"sc":0.20},
    {"id":"a4","st":"喷灯烘烤旧卷材槎口","rt":["喷灯烘烤"],"sc":0.20},
    {"id":"a5","st":"分层剥开旧卷材(关键区分点)","rt":["分层剥开"],"sc":0.30},
    {"id":"a6","st":"重新粘贴新卷材","rt":["重新粘贴","重贴新卷材"],"sc":0.25},
    {"id":"a7","st":"周边压实刮平","rt":["压实","刮平"],"sc":0.15},
]
TARGET = "a5"
CASE_CODES = [c for c,s in ERROR_CODE_REGISTRY.items() if s.get("series")=="E"]

# ── RTG normalize + gates (inlined from case_light_practice_rtg.py) ──
_PUNCT = re.compile(r"[\s　\.,,。;;:：、!!??()()\"'“”‘’\-—_/\\]+")
def norm(t):
    s=unicodedata.normalize("NFKC",str(t or ""))
    for a,b in {"㎡":"m2","m²":"m2","＝":"=","％":"%"}.items(): s=s.replace(a,b)
    return _PUNCT.sub("",s).casefold()
def overlap(a,b):
    ta,tb=set(norm(a)),set(norm(b))
    return len(ta&tb)/len(ta|tb) if ta and tb else 0.0
def contain(inner,outer):
    ti,to=set(norm(inner)),set(norm(outer))
    return len(ti&to)/len(ti) if ti else 0.0

def run_gates(item):
    pts={p["id"]:p for p in POINTS}
    correct=item["correct_options"]; dis=item["distractors"]; res=[]
    def add(g,s,d=""): res.append((g,s,d))
    # RTG5 structure+binding
    ok=True
    if not correct: add("RTG5","block","no correct"); ok=False
    elif not dis: add("RTG5","block","no distractors"); ok=False
    else:
        bad=None
        for o in correct:
            if not o.get("text"): bad="correct no text"
            if o.get("source_scoring_point_id") not in pts: bad="correct binds fake point"
        for d in dis:
            if not d.get("text"): bad="distractor no text"
            if d.get("source_scoring_point_id"): bad="distractor binds point"
        add("RTG5","block" if bad else "pass",bad or "")
    # RTG1 collision
    ck={norm(o["text"]) for o in correct}
    hit=next((d["text"] for d in dis if norm(d["text"]) in ck),None)
    add("RTG1","block" if hit else "pass", ("collides: "+hit) if hit else "")
    # RTG2 dedup
    seen=set(); dup=None
    for d in dis:
        k=norm(d["text"])
        if k in seen: dup=d["text"]
        seen.add(k)
    add("RTG2","block" if dup else "pass", ("dup: "+dup) if dup else "")
    # RTG3 error_code
    nh=False; bc=None
    for d in dis:
        c=str(d.get("error_code") or "").strip()
        if c=="NEEDS_REVIEW": nh=True
        elif c not in ERROR_CODE_REGISTRY: bc=c
    add("RTG3","block" if bc else ("needs_human" if nh else "pass"), ("bad code: "+str(bc)) if bc else "")
    # RTG8 faithfulness
    unf=None
    for o in correct:
        p=pts.get(o.get("source_scoring_point_id"))
        if p:
            ct,st=norm(o["text"]),norm(p["st"])
            if not(ct in st or st in ct or overlap(o["text"],p["st"])>=0.6): unf=o["text"]
    add("RTG8","block" if unf else "pass", ("unfaithful: "+str(unf)) if unf else "")
    # RTG4 candidate subset (candidates=all E) — soft
    out=next((d["error_code"] for d in dis if str(d.get("error_code")).strip() not in CASE_CODES and str(d.get("error_code")).strip()!="NEEDS_REVIEW"),None)
    add("RTG4","soft_fail" if out else "pass", ("outside: "+str(out)) if out else "")
    # RTG6 shape — soft
    reflen=max((len(norm(o["text"])) for o in correct),default=0); soft=None
    cn=[norm(o["text"]) for o in correct]
    for d in dis:
        dn=norm(d["text"])
        if reflen and not(0.3*reflen<=len(dn)<=3*reflen): soft="len "+d["text"]
        if any(dn and dn in c for c in cn): soft="substring "+d["text"]
        if any(contain(d["text"],o["text"])>=0.85 for o in correct): soft="near_correct "+d["text"]
        if str(d["text"]).lstrip()[:1] in("不","无","未","非"): soft="negation "+d["text"]
    add("RTG6","soft_fail" if soft else "pass", soft or "")
    st={s for _,s,_ in res}
    verdict="block" if "block" in st else "needs_human" if "needs_human" in st else "soft_fail" if "soft_fail" in st else "pass"
    return verdict,res

def build_prompt(target):
    tp=next(p for p in POINTS if p["id"]==target)
    menu="\n".join("  - %s: %s"%(c,ERROR_CODE_REGISTRY[c]["label"]) for c in CASE_CODES)
    other="\n".join("  - "+p["st"] for p in POINTS if p["id"]!=target)
    return ("你在为一建建筑实务案例题出一道『命中采分点』点选题。正确项已给定(采分点原文),\n"
        "你只需生成迷惑性干扰项——每个干扰项必须是采分点的可辨识错误变形:\n"
        "禁止与正确项字面相同、禁止『其实也对』、禁止只加『不』做廉价反转。\n\n"
        "【正确采分点(不要改写)】%s\n【本小问其它真采分点(不可当干扰项)】\n%s\n\n"
        "【可选错因码(每个干扰项选一个;拿不准填 NEEDS_REVIEW)】\n%s\n\n"
        '输出严格 JSON:{"distractors":[{"text":"...","error_code":"E0X"}]},共 3 个。只输出 JSON。'
        %(tp["st"],other,menu))

def parse(raw):
    s=raw.strip()
    if s.startswith("```"): s=s.split("```",2)[1].lstrip("json").strip().strip("`").strip()
    a,b=s.find("{"),s.rfind("}")
    return json.loads(s[a:b+1]).get("distractors") or []

async def one(cf,key,prompt):
    return await cf(prompt=prompt,system_prompt="You output only strict JSON.",model="deepseek-chat",api_key=key,max_retries=1,temperature=0)

def main():
    key=os.environ.get("DEEPSEEK_API_KEY")
    cf=functools.partial(complete,base_url="https://api.deepseek.com",binding="deepseek")
    prompt=build_prompt(TARGET)
    tp=next(p for p in POINTS if p["id"]==TARGET)
    runs=[]
    for i in range(3):
        try:
            raw=asyncio.run(one(cf,key,prompt))
            dis=parse(raw)
        except Exception as e:
            print("RUN%d ERROR: %r"%(i+1,e)); runs.append(None); continue
        item={"stem":"关于『起鼓割补』,下列哪一项是正确的采分点?",
              "correct_options":[{"text":tp["st"],"source_scoring_point_id":TARGET}],
              "distractors":dis}
        verdict,gates=run_gates(item)
        runs.append({"distractors":dis,"verdict":verdict,"gates":gates})
        print("=== RUN %d ==="%(i+1))
        print("  correct(逐字采分点): %s"%tp["st"])
        for d in dis: print("  干扰: %s  [%s]"%(d.get("text"),d.get("error_code")))
        print("  RTG verdict: %s"%verdict)
        for g,s,d in gates:
            if s!="pass": print("    %s=%s %s"%(g,s,d))
    # stability across 3 runs (temp=0 → identical distractor texts)
    keys=[tuple((d.get("text"),d.get("error_code")) for d in r["distractors"]) for r in runs if r]
    stable = len(keys)==3 and keys[0]==keys[1]==keys[2]
    print("=== STABILITY (temp=0, 3 runs identical?) : %s ==="%stable)
    # explicit re-verify of the 2026-07-09 run-2 near-synonym case:
    probe={"stem":"x","correct_options":[{"text":tp["st"],"source_scoring_point_id":TARGET}],
           "distractors":[{"text":"分层剥离旧卷材","error_code":"E12"}]}
    pv,pg=run_gates(probe)
    rtg6=next(s for g,s,_ in pg if g=="RTG6")
    print("=== NEAR-SYNONYM PROBE 『分层剥离旧卷材』 vs 正确『%s』 : RTG6=%s verdict=%s ==="%(tp["st"],rtg6,pv))
    print("=== RESULT JSON ==="); print(json.dumps({"stable":stable,"near_synonym_rtg6":rtg6,"runs":runs},ensure_ascii=False))

main()
