#!/usr/bin/env python3
"""统一标准复核 append-only 闭环 (2026-06-21).

与 autofix.py 的区别:这些 marathon 早期 pack **已有早期 §9**(jury_audit · 2026-06-20)。
autofix.py 的 re.sub 会删掉早期 §9 = 违反 append-only 红线。
本脚本改为追加一个**独立标题**的 §10 区块「统一标准复核 (jury_audit · 2026-06-21)」,
绝不触碰早期 §9,幂等只替换同标题的 §10。

用法: python autofix_append.py <pack.md> <jury_sidecar.json>
"""
import sys, os, re, json, subprocess, datetime

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
ENG = os.path.join(ROOT, "docs/原始数据/考点原料")
HEADER = "## 10 · 统一标准复核 · 4源异源团审计 (jury_audit · 2026-06-21)"

def extract_findings(jury_path):
    t = open(jury_path, encoding="utf-8").read().replace("```json", "").replace("```", "")
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
    r = subprocess.run(["python3", os.path.join(ENG, script), pack],
                       capture_output=True, text=True, cwd=ROOT)
    ok = "PASS" in r.stdout or "全部确定性命中" in r.stdout
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(无输出)"
    return ok, tail

def main():
    pack, jury = sys.argv[1], sys.argv[2]
    findings = extract_findings(jury)
    hi = [f for f in findings if f.get("count", 0) >= 2]
    lo = [f for f in findings if f.get("count", 0) < 2]
    today = "2026-06-21"

    lines = [f"\n{HEADER}\n",
             "> **统一标准复核**:本 pack 为 marathon 早期产物,早期 §9 (2026-06-20) 为早期方法跑的记录,**保留不动**。",
             "> 本段用**当前统一 4 源异源标准**(DeepSeek-V4-Pro + Qwen-3.7-Max + GPT-5.5/Codex + DeepSeek 合成)复核,append-only。",
             "> 收敛规则: count≥2=高可信(回真源核实再采纳) / count=1=单源候选(回真源核,非丢弃)。",
             f"> 高可信确证真问题才 surgical 改正文;同源幻觉/假警报驳回(理由见下方处置)。\n",
             f"**统计**: 高可信(≥2源) {len(hi)} 条 | 单源候选 {len(lo)} 条 | 合计 {len(findings)} 条。\n",
             "| # | issue | location | 源 | count | disposition | 建议fix |",
             "|---|---|---|---|---|---|---|"]
    def neutralize(s):
        # §10 是评注,不是引用。把 citation 形 ca:/kc:/m35: 前缀的冒号换成全角∶,
        # 保证人眼可读、但不被 verify_pack 的引用正则误读成"活引用"去核存在性。
        return re.sub(r"(ca|kc|m35):", r"\1∶", str(s))
    for i, f in enumerate(findings, 1):
        disp = "🔴高可信·回真源核" if f.get("count", 0) >= 2 else "🟡单源·回真源核"
        srcs = "+".join(f.get("flagged_by", []))
        issue = neutralize(f.get('issue', ''))[:70]
        loc = neutralize(f.get('location', ''))
        fix = neutralize(f.get('fix', ''))[:60]
        lines.append(f"| {i} | {issue} | {loc} | {srcs} | {f.get('count','')} | {disp} | {fix} |")
    block = "\n".join(lines) + "\n"

    txt = open(pack, encoding="utf-8").read()
    # 幂等: 只删本脚本的 §10 同标题段(绝不碰早期 §9)
    txt = re.sub(r"\n## 10 · 统一标准复核 · 4源异源团审计.*?(?=\n## |\Z)", "", txt, flags=re.S)
    # 追加到末尾(在注册表对齐等尾部块之后,作为审计附录)
    open(pack, "w", encoding="utf-8").write(txt.rstrip() + "\n" + block)

    print(f"=== autofix_append: {os.path.basename(pack)} ===")
    print(f"jury发现 {len(findings)} 条 → 已 append §10 统一标准复核 (高可信 {len(hi)} / 单源 {len(lo)}); 早期§9保留")
    g1, t1 = run_gate("verify_pack.py", pack)
    g2, t2 = run_gate("verify_exam_anchors.py", pack)
    print(f"复跑闸1机器闸: {'✅' if g1 else '❌'} {t1}")
    print(f"复跑闸2真题核验: {'✅' if g2 else '❌'} {t2}")
    print("─" * 50)
    print(f"裁决: {'✅ 闭环完成(两闸绿+发现透明入§10)' if (g1 and g2) else '❌ 闸未过'}")
    if hi:
        print(f"⚠ {len(hi)} 条高可信需回真源核实再决定采纳(本脚本只透明记录)")
    sys.exit(0 if (g1 and g2) else 1)

if __name__ == "__main__":
    main()
