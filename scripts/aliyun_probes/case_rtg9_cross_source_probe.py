# -*- coding: utf-8 -*-
"""只读 harness:RTG9 异源分流真跑——DeepSeek 生成器 vs Qwen(dashscope)异源判别。
证明:确定性 RTG1-8 放过的近义干扰项(分层剥离 vs 分层剥开),异源 Qwen 能判"也对"并分流。
只分流不当真值;不写库不部署。"""
import os, re, asyncio, functools, unicodedata
from deeptutor.services.llm.factory import complete

_PUNCT = re.compile(r"[\s　\.,,。;;:：、!!??()()\"'“”‘’\-—_/\\]+")
def norm(t):
    return _PUNCT.sub("", unicodedata.normalize("NFKC", str(t or ""))).casefold()
def sim(a, b):
    ta, tb = set(norm(a)), set(norm(b))
    return len(ta & tb)/len(ta | tb) if ta and tb else 0.0

CORRECT = "分层剥开旧卷材"
DISTRACTORS = ["分层剥离旧卷材", "用水泥砂浆抹平鼓泡即可"]  # 前者近义(RTG1-8放过),后者不像

def qwen_judge(cf, key, distractor, correct):
    prompt = ("在一建建筑实务案例判分里,正确采分点是:「%s」。\n"
              "有一个选项是:「%s」。\n"
              "请判断这个选项和正确采分点是否**语义等价/其实也对**(即阅卷会不会也算对)?\n"
              "只回答一个字:是 或 否。" % (correct, distractor))
    raw = asyncio.run(cf(prompt=prompt, system_prompt="你只回答'是'或'否'。",
                         model="qwen-plus", api_key=key, max_retries=1, temperature=0))
    ans = str(raw).strip()
    return ans.startswith("是")

def main():
    key = os.environ.get("DASHSCOPE_API_KEY")
    # 异源:不 pin deepseek,用 dashscope(Qwen)——与生成器 DeepSeek 换厂
    cf = functools.partial(complete, binding="dashscope")
    print("=== RTG9 异源真跑(生成器DeepSeek / 校验器Qwen-dashscope)===")
    flagged = []
    for d in DISTRACTORS:
        s = sim(d, CORRECT)
        triaged = s >= 0.5
        verdict = None
        if triaged:
            try:
                verdict = qwen_judge(cf, key, d, CORRECT)
            except Exception as e:
                print("  Qwen ERROR %r" % e); continue
            if verdict:
                flagged.append(d)
        print("  干扰「%s」 相似度=%.2f 送异源=%s Qwen判也对=%s" % (d, s, triaged, verdict))
    print("=== 可疑队列(RTG9只分流不当真值): %s ===" % flagged)
    print("=== RESULT: 近义干扰被异源分流=%s ===" % ("分层剥离旧卷材" in flagged))

main()
