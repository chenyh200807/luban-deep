#!/usr/bin/env python3
"""4 源异源团语义审 · 自动化 (Layer-2, 量产品质核心).

用法: python jury_audit.py <pack.md> [<source.json>]
自动跑 3 个异源谱系各独立语义审 + 自动算收敛(≥2源撞同处=高可信):
  - DeepSeek V4 Pro  (deepseek-v4-pro, API)
  - Qwen 3.7 Max     (qwen-max-latest, DashScope API)
  - GPT-5.5          (codex exec --sandbox read-only, best-effort)
确定性事实(题号/point_id)归两道闸,本脚本只做语义。各源中立取证、禁互看。
输出: 各源原始审 + 收敛报告(高可信必改在前)。不改 pack(改由人/汇编据收敛报告做)。
"""
import os, re, json, sys, subprocess, time
from concurrent.futures import ThreadPoolExecutor

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"

def key(*names):
    for n in names:
        if os.environ.get(n): return os.environ[n]
    if os.path.exists(os.path.join(ROOT, ".env")):
        for l in open(os.path.join(ROOT, ".env"), errors="ignore"):
            for n in names:
                if l.startswith(n + "="):
                    return l.split("=", 1)[1].strip().strip('"').strip("'").split(",")[0]
    return None

def build_prompt(pack_path, src_path):
    pack = open(pack_path, encoding="utf-8").read()
    q = {}
    if src_path and os.path.exists(src_path):
        src = json.load(open(src_path, encoding="utf-8"))
        for u in src.get("units", []):
            for sp in u.get("scoring_points", []):
                if sp.get("point_id"): q[sp["point_id"]] = (sp.get("quote") or "")[:200]
    cited = set(re.findall(r"(?:ca|kc|cc|m35):[0-9A-Za-z_\-一-鿿]+(?::[0-9A-Za-z_\-一-鿿]+)?", pack))
    srcmap = "\n".join(f"{p} :: {q[p]}" for p in sorted(cited) if p in q)
    sys_p = "你是异源独立语义裁判,中立取证(不是检察官,宁可标存疑也别为凑数编问题)。"
    usr = f"""审一份 Opus 团编的考点 pack。【分工】确定性脚本已验:真题锚 0 漂移、point_id 都存在。你别核题号/point_id 存在性,只做语义判断。
专查 4 类(简洁,每条带证据):
A. 标🟢的关键数值/规范点,其 point_id 的 quote 是否真支持该论断? 还是 quote 截断/语境不符却当🟢?
B. R2 不变量/examiner_intent 逻辑能否覆盖声称场景? 漏洞?
C. R8 误区→error_code 映射语义贴不贴(E 案例/M 客观题? E06 程序顺序/E07 概念混淆用对场景)?
D. 本体 vs 邻接噪声剔除判断对不对?
输出: 语义问题清单,每条一行 `位置 | 问题 | 证据 | 建议三色降级`。没问题的明说"语义成立"。最后一句总裁决。

=== PACK ===
{pack}

=== 源料锚 quote(供核🟢) ===
{srcmap}"""
    return sys_p, usr

def call_api(name, base, api_key, models, sys_p, usr):
    if not api_key: return name, f"[{name}] 缺 key,跳过"
    try:
        from openai import OpenAI
        cli = OpenAI(base_url=base, api_key=api_key)
        for m in models:
            try:
                r = cli.chat.completions.create(model=m, messages=[{"role":"system","content":sys_p},{"role":"user","content":usr}], temperature=0.2, timeout=300)
                return name, f"[{name} · {m}]\n" + r.choices[0].message.content
            except Exception as e:
                last = f"[{name}] {m} 失败: {str(e)[:160]}"
        return name, last
    except Exception as e:
        return name, f"[{name}] 异常: {str(e)[:160]}"

def call_codex(sys_p, usr):
    try:
        p = subprocess.run(["codex","exec","--sandbox","read-only","-"], input=sys_p+"\n\n"+usr,
                           capture_output=True, text=True, timeout=420, cwd=ROOT)
        out = (p.stdout or "")[-4000:]
        return "GPT-5.5(Codex)", f"[GPT-5.5 via codex exec]\n{out}" if out.strip() else f"[GPT-5.5] 空输出/失败 rc={p.returncode}"
    except subprocess.TimeoutExpired:
        return "GPT-5.5(Codex)", "[GPT-5.5] codex exec 超时(420s)"
    except Exception as e:
        return "GPT-5.5(Codex)", f"[GPT-5.5] codex 异常: {str(e)[:140]}"

def synthesize(audits, ds_key):
    joined = "\n\n".join(f"#### 源 {n}\n{a}" for n, a in audits)
    sp = "你是收敛分析器,中立。"
    up = f"""下面是 3 个异源 AI 对同一份 pack 的独立语义审。请聚类成"问题清单",每个问题标注被哪几个源独立提到。
收敛规则: ≥2 个源独立撞同一处=高可信(必改); 仅 1 源=存疑(回真源核)。
只输出 JSON 数组,每元素: {{"issue":"一句话问题","location":"pack位置","flagged_by":["源名"],"count":N,"confidence":"高可信/存疑","fix":"建议改法"}}
按 count 降序。不要解释。

{joined}"""
    if not ds_key: return "[合成跳过:缺 DeepSeek key]"
    try:
        from openai import OpenAI
        cli = OpenAI(base_url="https://api.deepseek.com", api_key=ds_key)
        r = cli.chat.completions.create(model="deepseek-v4-pro", messages=[{"role":"system","content":sp},{"role":"user","content":up}], temperature=0, timeout=300)
        return r.choices[0].message.content
    except Exception as e:
        return f"[合成失败: {str(e)[:140]}]"

def main():
    if len(sys.argv) < 2:
        print("用法: python jury_audit.py <pack.md> [<source.json>]"); sys.exit(2)
    pack = sys.argv[1]
    src = sys.argv[2] if len(sys.argv) > 2 else None
    if not src:
        m = re.match(r"([A-Z]\d+)", os.path.basename(pack))
        if m:
            import glob
            c = glob.glob(os.path.join(os.path.dirname(pack), f"_{m.group(1)}*_compiled_source.json"))
            src = c[0] if c else None
    sys_p, usr = build_prompt(pack, src)
    ds_key = key("DEEPSEEK_API_KEY"); qw_key = key("DASHSCOPE_API_KEY","QWEN_API_KEY")
    print(f"=== 4源异源团语义审: {os.path.basename(pack)} ===  (DeepSeek:{'有' if ds_key else '缺'} Qwen:{'有' if qw_key else '缺'} Codex:CLI)")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [
            ex.submit(call_api, "DeepSeek-V4-Pro", "https://api.deepseek.com", ds_key, ["deepseek-v4-pro"], sys_p, usr),
            ex.submit(call_api, "Qwen-3.7-Max", "https://dashscope.aliyuncs.com/compatible-mode/v1", qw_key, ["qwen-max-latest","qwen-max"], sys_p, usr),
            ex.submit(call_codex, sys_p, usr),
        ]
        audits = [f.result() for f in futs]
    print(f"[3 源审完, {int(time.time()-t0)}s]\n")
    for n, a in audits:
        print("="*70); print(a[:3000])
    print("\n" + "#"*70 + "\n=== 收敛报告 (≥2源=高可信必改) ===")
    syn = synthesize(audits, ds_key)
    print(syn)
    # 存干净 sidecar JSON(供 autofix 读, 不靠 stdout 截断)
    m = re.match(r"([A-Z]\d+)", os.path.basename(pack))
    if m:
        clean = syn.replace("```json", "").replace("```", "")
        i, j = clean.find("["), clean.rfind("]")
        side = os.path.join(os.path.dirname(pack), f"_{m.group(1)}_jury.json")
        try:
            json.loads(clean[i:j+1])  # 校验可解析
            open(side, "w", encoding="utf-8").write(clean[i:j+1])
            print(f"\n[sidecar 已存: {side}]")
        except Exception as e:
            print(f"\n[sidecar 存失败: {str(e)[:80]}]")

if __name__ == "__main__":
    main()
