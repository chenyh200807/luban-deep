#!/usr/bin/env python3
"""自动修复闭环 (量产闭环最后一块): jury发现 → 自动写进pack审计记录 → 复跑两闸 → 残留报告.

用法: python autofix.py <pack.md> <jury_output_file>
安全边界: 只做"安全自动"的部分——把4源jury的全部发现自动整理进pack的审计记录段(append-only,不改正文prose),
按收敛规则标disposition(count≥2=高可信待改/count=1=单源候选回真源核),再复跑两道确定性闸.
深度改写(补规范锚等=研究活)留在审计记录里当透明残留,不自动瞎改正文(防LLM改写引入新错).
这把"660个问题手动整理"的瓶颈自动掉,同时不假装自动做研究级修复.
"""
import sys, os, re, json, subprocess, datetime

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"

def extract_findings(jury_path):
    t = open(jury_path, encoding="utf-8").read().replace("```json", "").replace("```", "")
    # 取最后一个能解析成数组的 [...] (合成JSON在3源审之后)
    dec = json.JSONDecoder()
    best = None
    for i, ch in enumerate(t):
        if ch == "[":
            try:
                arr, _ = dec.raw_decode(t[i:])
                if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "issue" in arr[0]:
                    best = arr
            except Exception:
                pass
    return best or []

def run_gate(script, pack):
    r = subprocess.run(["python3", os.path.join(ROOT, "docs/原始数据/考点原料", script), pack],
                       capture_output=True, text=True, cwd=ROOT)
    ok = "PASS" in r.stdout or "全部确定性命中" in r.stdout
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(无输出)"
    return ok, tail

def main():
    pack, jury = sys.argv[1], sys.argv[2]
    findings = extract_findings(jury)
    if not findings:
        print("⚠ 未解析到 jury 发现, 中止"); sys.exit(1)
    hi = [f for f in findings if f.get("count", 0) >= 2]
    lo = [f for f in findings if f.get("count", 0) < 2]
    today = datetime.date(2026, 6, 20).isoformat()

    # 生成审计记录段
    lines = [f"\n## 9 · 4源异源团自动审计记录 (jury_audit · {today})\n",
             f"> 自动闭环(autofix)生成。4源异源团(Opus/Codex/DeepSeek/Qwen)中立独立审,DeepSeek合成。",
             f"> 收敛规则: count≥2=高可信(必改) / count=1=单源真catch(回真源核,**非丢弃**)。",
             f"> 本段 append-only 透明记录全部 {len(findings)} 条发现;深度改写(补规范锚等)为研究级残留,人工/下轮收。\n",
             f"**统计**: 高可信(≥2源) {len(hi)} 条 | 单源候选 {len(lo)} 条 | 合计 {len(findings)} 条。\n",
             "| # | issue | location | 源 | count | disposition | 建议fix |",
             "|---|---|---|---|---|---|---|"]
    for i, f in enumerate(findings, 1):
        disp = "🔴高可信·必改" if f.get("count",0) >= 2 else "🟡单源·回真源核"
        srcs = "+".join(f.get("flagged_by", []))
        lines.append(f"| {i} | {f.get('issue','')[:60]} | {f.get('location','')} | {srcs} | {f.get('count','')} | {disp} | {f.get('fix','')[:50]} |")
    block = "\n".join(lines) + "\n"

    txt = open(pack, encoding="utf-8").read()
    # 幂等: 删旧的同类段再追加
    txt = re.sub(r"\n## 9 · 4源异源团自动审计记录.*?(?=\n## |\Z)", "", txt, flags=re.S)
    open(pack, "w", encoding="utf-8").write(txt.rstrip() + "\n" + block)

    print(f"=== autofix: {os.path.basename(pack)} ===")
    print(f"jury发现 {len(findings)} 条 → 已自动写入 §9 审计记录 (高可信 {len(hi)} / 单源 {len(lo)})")
    g1, t1 = run_gate("verify_pack.py", pack)
    g2, t2 = run_gate("verify_exam_anchors.py", pack)
    print(f"复跑闸1机器闸: {'✅' if g1 else '❌'} {t1}")
    print(f"复跑闸2真题核验: {'✅' if g2 else '❌'} {t2}")
    print("─"*50)
    status = "✅ 闭环完成(两闸绿+发现已透明入表)" if (g1 and g2) else "❌ 闸未过,需处理"
    print(f"裁决: {status}")
    if hi:
        print(f"⚠ {len(hi)} 条高可信待人复核应用(autofix只透明记录,不自动改正文)")
    sys.exit(0 if (g1 and g2) else 1)

if __name__ == "__main__":
    main()
