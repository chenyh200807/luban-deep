# -*- coding: utf-8 -*-
"""Self-contained read-only harness: full real-LLM chain end-to-end.
  真 DeepSeek 生成干扰项 → 真 RTG1-8 确定性门 → 真 Qwen(异源)RTG9 分流 → 确定性判分

Runs inside the deployed deeptutor container. Imports ONLY deployed modules
(llm.factory.complete + error_codes.ERROR_CODE_REGISTRY); F16 points + generator
+ RTG gate logic are inlined (mirrors the feat-branch modules verbatim).
Read-only: no DB write, no /app mutation. Cross-source RTG9 uses DASHSCOPE (Qwen),
a genuinely different vendor than the DeepSeek generator, so it cannot self-attest.

投送:base64 本文件 | ssh Aliyun-ECS-2 "docker cp deeptutor:/tmp/x.py && \
  docker exec deeptutor sh -lc 'cd /app && PYTHONPATH=/app python /tmp/x.py; rm -f /tmp/x.py'"
"""
import os, re, json, asyncio, functools, unicodedata

from deeptutor.services.llm.factory import complete
from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

# ── F16 起鼓割补 dev anchor (7 atomized points; live-validated) ──
POINTS = [
    ("a1", "用刀将鼓泡卷材割开放气", ["割开", "放气"], 0.25),
    ("a2", "擦干水分", ["擦干"], 0.15),
    ("a3", "清除旧胶结料", ["清除旧胶结料"], 0.20),
    ("a4", "喷灯烘烤旧卷材槎口", ["喷灯烘烤"], 0.20),
    ("a5", "分层剥开旧卷材(关键区分点)", ["分层剥开"], 0.30),
    ("a6", "重新粘贴新卷材", ["重新粘贴"], 0.25),
    ("a7", "周边压实刮平", ["压实", "刮平"], 0.15),
]
TARGET = "a5"
TP = next(p for p in POINTS if p[0] == TARGET)
CASE_CODES = [c for c, s in ERROR_CODE_REGISTRY.items() if s.get("series") == "E"]

# ── RTG normalize + similarity (inlined from case_light_practice_rtg.py) ──
_PUNCT = re.compile(r"[\s　\.,,。;;:：、!!??()()\"'“”‘’\-—_/\\]+")


def norm(t):
    return _PUNCT.sub("", unicodedata.normalize("NFKC", str(t or ""))).casefold()


def jaccard(a, b):
    ta, tb = set(norm(a)), set(norm(b))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def containment(inner, outer):
    ti, to = set(norm(inner)), set(norm(outer))
    return len(ti & to) / len(ti) if ti else 0.0


# ── ① real DeepSeek distractor generation ──
def gen_distractors(complete_fn, key):
    menu = "\n".join("  %s:%s" % (c, ERROR_CODE_REGISTRY[c]["label"]) for c in CASE_CODES)
    other = "\n".join("  " + p[1] for p in POINTS if p[0] != TARGET)
    prompt = (
        "为一建案例题出『命中采分点』点选题的干扰项。正确采分点(不改写):%s\n"
        "本小问其它真采分点(不可当干扰):\n%s\n可选错因码:\n%s\n"
        '严格JSON:{"distractors":[{"text":"...","error_code":"E0X"}]},3个,只输出JSON。'
        % (TP[1], other, menu)
    )
    raw = asyncio.run(
        complete_fn(prompt=prompt, system_prompt="只输出JSON。", model="deepseek-chat",
                    api_key=key, max_retries=1, temperature=0)
    )
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1].lstrip("json").strip().strip("`").strip()
    a, b = s.find("{"), s.rfind("}")
    return json.loads(s[a:b + 1]).get("distractors") or []


# ── ② real deterministic RTG1-8 gates (crash/dedup/code/near-synonym) ──
def rtg1_8(dis):
    issues = []
    ck = norm(TP[1])
    seen = set()
    for d in dis:
        t, c = d.get("text", ""), str(d.get("error_code", "")).strip()
        if norm(t) == ck:
            issues.append("RTG1撞车:%s" % t)
        if norm(t) in seen:
            issues.append("RTG2重复:%s" % t)
        seen.add(norm(t))
        if c not in ERROR_CODE_REGISTRY and c != "NEEDS_REVIEW":
            issues.append("RTG3坏码:%s" % c)
        if containment(t, TP[1]) >= 0.85:
            issues.append("RTG6近义(可疑):%s" % t)
    return issues


# ── ③ real cross-source RTG9 (Qwen, genuinely different vendor) ──
def qwen_equiv(complete_fn, key, distractor, correct):
    prompt = (
        "正确采分点:「%s」。选项:「%s」。这个选项和正确采分点是否语义等价/其实也对"
        "(阅卷会算对)?只回答 是/否。" % (correct, distractor)
    )
    raw = asyncio.run(
        complete_fn(prompt=prompt, system_prompt="只回答'是'或'否'。", model="qwen-plus",
                    api_key=key, max_retries=1, temperature=0)
    )
    return str(raw).strip().startswith("是")


def main():
    dk = os.environ.get("DEEPSEEK_API_KEY")
    qk = os.environ.get("DASHSCOPE_API_KEY")
    ds = functools.partial(complete, base_url="https://api.deepseek.com", binding="deepseek")
    qw = functools.partial(complete, binding="dashscope")

    print("=== 全链路真 LLM 端到端(F16 起鼓割补)===")
    print("① 真 DeepSeek 生成干扰项...")
    dis = gen_distractors(ds, dk)
    print("   正确(采分点原文): %s" % TP[1])
    for d in dis:
        print("   干扰: %s [%s]" % (d.get("text"), d.get("error_code")))

    print("② 真 RTG1-8 确定性门:")
    iss = rtg1_8(dis)
    print("   %s" % ("全过" if not iss else " / ".join(iss)))

    print("③ 真 Qwen 异源 RTG9(对相似度过阈的判其实也对):")
    flagged = []
    for d in dis:
        s = jaccard(d.get("text", ""), TP[1])
        if s >= 0.5:
            eq = qwen_equiv(qw, qk, d.get("text"), TP[1])
            print("   干扰「%s」相似%.2f → Qwen判也对=%s" % (d.get("text"), s, eq))
            if eq:
                flagged.append(d.get("text"))
    print("   可疑队列(只分流): %s" % (flagged or "无"))

    print("④ 确定性判分(两份作答):")
    ids = {p[0] for p in POINTS}
    sc = {p[0]: p[3] for p in POINTS}
    a = sum(sc[i] for i in ids - {"a5"})   # 漏『分层剥开』
    b = sum(sc[i] for i in ids)            # 全命中
    print("   作答A漏『分层剥开』=%.2f / 作答B写了=%.2f (满分%.2f)"
          % (a, b, sum(sc.values())))
    print("=== 整条真链路(真DeepSeek生成→真RTG门→真Qwen异源→确定性判分)跑通 ===")


if __name__ == "__main__":
    main()
