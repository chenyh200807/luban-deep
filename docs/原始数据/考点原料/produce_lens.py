#!/usr/bin/env python3
"""多模型镜头生产 — 把生产环单个镜头分派给指定谱系(让 DeepSeek/Qwen/Codex 真"造内容",不只质检).

用法: python produce_lens.py <考点ID> <model> <lensKey>
  model: deepseek | qwen | codex     (Opus 不在此脚本,走 Workflow agent)
  lensKey: A_聚拢原理 | C_采分边界 | D_误区动画   (B_出题人=Opus走Workflow)
读 _<ID>_compiled_source.json(教材锚) + 可选 _<ID>_exam_evidence.json(真题证据), 嵌入 prompt,
调指定谱系产出该镜头 markdown, 存 _<ID>_lens_<key>.md 并打印.
"""
import sys, os, re, json, subprocess

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
ERRCODES = "deeptutor/contracts/error_codes.py"

def key(*names):
    for n in names:
        if os.environ.get(n): return os.environ[n]
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for l in open(p, errors="ignore"):
            for n in names:
                if l.startswith(n + "="):
                    return l.split("=", 1)[1].strip().strip('"').strip("'").split(",")[0]
    return None

LENS = {
  "A_聚拢原理": "(1)R1 source_refs清单 (2)跨章知识点全景表(每行 知识点|所属章|node_code|关键数值|三色,如实标本体vs邻接噪声) (3)原理因果层:把散点压成可讲给学生的因果逻辑链(成因→机理→为什么这措施有效),标三色.",
  "C_采分边界": "R5采分点(引源料point_id,合理分组) + R6答案骨架(满分要点) + R7边界(满分vs压线vs0分near-miss). R7是最弱项只能给候选全标🔴待真人/专家裁决.",
  "D_误区动画": "R8误区5-8个(每个映射"+ERRCODES+"真实error_code,禁自造;给 现象→错误心智模型→对症解药) + 动画分镜原料(视觉隐喻+reveal顺序+aha时刻+旁白锚点).",
}

def build_prompt(cid):
    src = json.load(open(os.path.join(ROOT, f"docs/原始数据/考点原料/_{cid}_compiled_source.json"), encoding="utf-8"))
    name = src.get("考点", cid)
    lines = []
    for u in src.get("units", [])[:120]:
        for sp in u.get("scoring_points", []):
            lines.append(f"{sp.get('point_id')} :: {sp.get('statement','')[:80]} :: {(sp.get('quote') or '')[:90]}")
    srcmap = "\n".join(lines[:200])
    ev_path = os.path.join(ROOT, f"docs/原始数据/考点原料/_{cid}_exam_evidence.json")
    ev = open(ev_path, encoding="utf-8").read()[:6000] if os.path.exists(ev_path) else "(无真题证据文件,真题锚一律标🔴)"
    base = (f"考点: {cid} {name}. 你是深母题生产的【镜头专家】,产出该镜头的内容(不是审查,是创作).\n"
            "三色铁律: 🟢锚定(附source/point_id/真题年题号) / 🔵工程通识 / 🔴待验证(禁编造冒充🟢).\n"
            "真题锚只能引下方真题证据里的{年份+题号},证据外禁写'某年第N题'. 教材锚引下方source的point_id.\n"
            "错因码只引 deeptutor/contracts/error_codes.py 已注册码(E01-E12/M01-M10),禁自造.")
    return base, srcmap, ev, name

def call(cid, model, lenskey):
    if lenskey not in LENS:
        print("lensKey 须是:", list(LENS.keys())); sys.exit(2)
    base, srcmap, ev, name = build_prompt(cid)
    sys_p = "你是深母题镜头生产专家,严守三色铁律与锚定要求,产出结构化markdown。"
    usr = f"{base}\n\n你的镜头: {LENS[lenskey]}\n\n=== 教材锚源料(point_id::statement::quote) ===\n{srcmap}\n\n=== 真题证据(唯一真题锚源) ===\n{ev}\n\n直接输出该镜头完整markdown。"
    out = ""
    if model == "deepseek":
        from openai import OpenAI
        cli = OpenAI(base_url="https://api.deepseek.com", api_key=key("DEEPSEEK_API_KEY"))
        out = cli.chat.completions.create(model="deepseek-v4-pro", messages=[{"role":"system","content":sys_p},{"role":"user","content":usr}], temperature=0.3, timeout=300).choices[0].message.content
    elif model == "qwen":
        from openai import OpenAI
        cli = OpenAI(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key=key("DASHSCOPE_API_KEY","QWEN_API_KEY"))
        for m in ("qwen-max-latest","qwen-max"):
            try:
                out = cli.chat.completions.create(model=m, messages=[{"role":"system","content":sys_p},{"role":"user","content":usr}], temperature=0.3, timeout=300).choices[0].message.content; break
            except Exception as e: out = f"qwen {m} 失败: {str(e)[:120]}"
    elif model == "codex":
        p = subprocess.run(["codex","exec","--sandbox","read-only","-"], input=sys_p+"\n\n"+usr, capture_output=True, text=True, timeout=420, cwd=ROOT)
        out = (p.stdout or "")[-6000:] or f"codex 空输出 rc={p.returncode}"
    else:
        print("model 须是 deepseek|qwen|codex"); sys.exit(2)
    outp = os.path.join(ROOT, f"docs/原始数据/考点原料/_{cid}_lens_{lenskey}.md")
    open(outp, "w", encoding="utf-8").write(f"<!-- 镜头 {lenskey} by {model} -->\n" + out)
    print(f"=== {cid} 镜头 {lenskey} by {model} ({len(out)}字) → {os.path.basename(outp)} ===\n")
    print(out[:2500])

if __name__ == "__main__":
    call(sys.argv[1], sys.argv[2], sys.argv[3])
