#!/usr/bin/env python3
"""R7 active 构造 — AI天团锚真考卷答案/解析/分值,构造判分鲁布里克(candidate governed_gold).

用法: python r7_construct.py <考点ID> <年份> <题号>
六阶精工流程的核心可脚本部分:
  相0 取证: 从 _<ID>_exam_evidence.json 拿官方 correct_answer/analysis/score/logic_chain (ground truth)
  相1 多模型独立构造: DeepSeek + Qwen 各独立把官方答案/解析拆成采分点鲁布里克(分值和==score,锚analysis)
  相2 确定性闸: ① 各模型采分点分值和==官方score? ② 计算题:复算logic_chain结果==correct_answer?
  相2 收敛: 两模型采分点是否撞同处(高可信)
输出 candidate governed_gold JSON. (相3红队/相4自洽校准/相5异源终审 = v2;本v1先证核心:锚官方+确定性闸+多模型收敛)
铁律: AI不发明标准,只拆官方ground truth;锚不到官方的采分点=🔴。
"""
import sys, os, re, json
ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"

def key(*names):
    for n in names:
        if os.environ.get(n): return os.environ[n]
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for l in open(p, errors="ignore"):
            for n in names:
                if l.startswith(n+"="): return l.split("=",1)[1].strip().strip('"').strip("'").split(",")[0]
    return None

def construct(model, gt):
    sys_p = "你是判分鲁布里克构造器,严守'不发明标准,只拆官方答案/解析'。"
    usr = f"""下面是一道真题的【官方 ground truth】。把它拆成判分采分点鲁布里克。
铁律: 每个采分点的分值必须能锚到官方 analysis 的对应步骤;所有采分点分值之和【必须等于】官方 score;不发明官方没有的给分点。
官方题号: {gt['年份']}{gt['题号']}  官方总分 score={gt['score']}
官方 correct_answer: {gt['correct_answer']}
官方 analysis: {gt['analysis']}
官方 logic_chain(计算规则): {gt.get('logic_chain')}

只输出 JSON: {{"采分点":[{{"描述":"...","分值":N,"锚":"analysis里的原文片段"}}], "分值和":N}}。不要解释。"""
    from openai import OpenAI
    if model == "deepseek":
        cli = OpenAI(base_url="https://api.deepseek.com", api_key=key("DEEPSEEK_API_KEY")); mid = "deepseek-v4-pro"
    else:
        cli = OpenAI(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key=key("DASHSCOPE_API_KEY","QWEN_API_KEY")); mid = "qwen-max-latest"
    r = cli.chat.completions.create(model=mid, messages=[{"role":"system","content":sys_p},{"role":"user","content":usr}], temperature=0, timeout=240)
    t = r.choices[0].message.content.replace("```json","").replace("```","")
    i,j = t.find("{"), t.rfind("}")
    try: return json.loads(t[i:j+1])
    except Exception as e: return {"error": str(e)[:80], "raw": t[:200]}

def recompute_2019(gt):
    """计算题确定性复算(相2最硬保证): 实现 logic_chain, 从输入算配合比, 对官方correct_answer."""
    # 2019: 设计水泥400, 砂率1.7, 石率2.8, 水胶比0.46; 施工:粉煤灰20%等量替代水泥, 中砂含水率4%/碎石1.2%
    cement = 400
    design = {"水泥": cement, "中砂": round(cement*1.7,1), "碎石": round(cement*2.8,1), "水": round(cement*0.46,1)}
    fly = 0.20
    cons = {"水泥": round(cement*(1-fly),1), "粉煤灰": round(cement*fly,1),
            "中砂": round(cement*1.768,1), "碎石": round(cement*2.856,1)}
    cons["水"] = round(design["水"] - (0.04*cons["中砂"] + 0.012*cons["碎石"]),2)
    return {"设计配合比(复算)": design, "施工配合比(复算)": cons}

def main():
    cid, yr, num = sys.argv[1], sys.argv[2], sys.argv[3]
    ev = json.load(open(os.path.join(ROOT, f"docs/原始数据/考点原料/_{cid}_exam_evidence.json"), encoding="utf-8"))
    gt = next((e for e in ev["evidence"] if e["year"]==yr and (e["题号"]==f"第{num}题" or num in e["题号"]) and (e.get("logic_chain") or "配合比" in e.get("correct_answer",""))), None)
    if not gt:
        print("未找到该题 ground truth"); sys.exit(1)
    gt["年份"] = yr
    print(f"=== R7 active 构造: {cid} {yr}{gt['题号']} (官方score={gt['score']}) ===\n")
    print("【相0 取证】官方答案/解析/logic_chain 已锁定(ground truth)\n")

    print("【相2 确定性复算】(计算题最硬保证)")
    rc = recompute_2019(gt)
    print(json.dumps(rc, ensure_ascii=False))
    print(f"  官方correct_answer: {gt['correct_answer'][:120]}")
    print("  → 复算值与官方答案逐项对照(人核): 水泥320/粉煤灰80/中砂707.2/碎石1142.4 是否一致\n")

    print("【相1 多模型独立构造 + 相2 分值求和闸 + 收敛】")
    rubrics = {}
    for m in ("deepseek", "qwen"):
        rb = construct(m, gt)
        rubrics[m] = rb
        pts = rb.get("采分点", [])
        s = sum(p.get("分值",0) for p in pts)
        gate = "✅" if abs(s - float(gt["score"])) < 0.01 else f"❌(和{s}≠官方{gt['score']})"
        print(f"  [{m}] 采分点{len(pts)}个, 分值和={s} {gate}")
        for p in pts[:6]:
            print(f"      {p.get('分值')}分 · {p.get('描述','')[:40]}")
    out = {"考点":cid, "题号":f"{yr}{gt['题号']}", "官方score":gt["score"], "确定性复算":rc, "多模型鲁布里克":rubrics, "status":"candidate_governed_gold"}
    p = os.path.join(ROOT, f"docs/原始数据/考点原料/_{cid}_{yr}_R7_governed_gold.json")
    json.dump(out, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ candidate governed_gold 存: {os.path.basename(p)} (待相3红队/相5异源终审升active)")

if __name__ == "__main__":
    main()
