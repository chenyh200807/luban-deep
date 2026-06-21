#!/usr/bin/env python3
"""Append-only 统一标准复核 §9.y 子段 (2026-06-21) + 复跑两闸.

与 autofix.py 的区别: autofix.py 会用正则 *删除* 旧 §9 块再追加 = 覆盖早期记录,
违反本轮 append-only 红线。本脚本把新一轮 4 源异源 jury 发现作为新的 dated 子段,
插在既有 §9 块之后、紧邻其下的 `---`/`## 注册表对齐` 之前, 早期 §9 一字不动保留。

用法: python3 append_jury_2026-06-21.py <pack.md> <jury_sidecar.json> "<verify_note>"
"""
import sys, os, re, json, subprocess

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
ENG = os.path.join(ROOT, "docs/原始数据/考点原料")
DATE = "2026-06-21"


def run_gate(script, pack):
    r = subprocess.run(["python3", os.path.join(ENG, script), pack],
                       capture_output=True, text=True, cwd=ROOT)
    ok = "PASS" in r.stdout or "全部确定性命中" in r.stdout
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(无输出)"
    return ok, tail


def build_block(findings, note):
    hi = [f for f in findings if f.get("count", 0) >= 2]
    lo = [f for f in findings if f.get("count", 0) < 2]
    lines = [
        f"\n### 9.y 统一标准复核 (当前统一 4 源异源标准 · jury_audit · {DATE})\n",
        "> 用**当前统一 4 源异源标准**(DeepSeek-V4-Pro + Qwen-3.7-Max + GPT-5.5/Codex + DeepSeek 合成)复核本 pack,",
        "> 产标准 sidecar `_<ID>_jury.json`。**本子段 append-only,上方早期 §9 记录一字不动保留**(区分早晚两轮)。",
        "> 收敛规则: count≥2=高可信(回真源核实后采纳/驳回) / count=1=单源(回真源核,非丢弃)。",
        f"> **复核员人工裁决**: {note}\n",
        f"**统计**: 高可信(≥2源) {len(hi)} 条 | 单源候选 {len(lo)} 条 | 合计 {len(findings)} 条。\n",
        "| # | issue | location | 源 | count | disposition | 建议fix |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, f in enumerate(findings, 1):
        disp = "🔴高可信·回源核" if f.get("count", 0) >= 2 else "🟡单源·回源核"
        srcs = "+".join(f.get("flagged_by", []))
        issue = str(f.get("issue", "")).replace("|", "／")[:80]
        fix = str(f.get("fix", "")).replace("|", "／")[:60]
        loc = str(f.get("location", "")).replace("|", "／")
        lines.append(f"| {i} | {issue} | {loc} | {srcs} | {f.get('count','')} | {disp} | {fix} |")
    return "\n".join(lines) + "\n"


def main():
    pack, sidecar, note = sys.argv[1], sys.argv[2], sys.argv[3]
    findings = json.load(open(sidecar, encoding="utf-8"))
    block = build_block(findings, note)
    txt = open(pack, encoding="utf-8").read()

    # 幂等: 删掉本脚本上一次插入的同名子段(只删 9.y 自身, 不碰早期 §9)
    txt = re.sub(r"\n### 9\.y 统一标准复核 .*?(?=\n## |\n### 9\.[a-z] |\Z)", "\n", txt, flags=re.S)

    # 找既有 §9 块, 在其结尾(下一个 `## ` 之前)插入
    m = re.search(r"\n## 9 · 4源异源团自动审计记录.*?(?=\n## )", txt, flags=re.S)
    if not m:
        # 没有旧 §9 (理论上不该发生): 追加到文末
        new = txt.rstrip() + "\n\n## 9 · 4源异源团自动审计记录\n" + block
    else:
        end = m.end()
        new = txt[:end] + block + txt[end:]
    open(pack, "w", encoding="utf-8").write(new)

    print(f"=== append 9.y: {os.path.basename(pack)} ===")
    print(f"jury 发现 {len(findings)} 条 → 已 append-only 写入 §9.y (早期 §9 保留)")
    g1, t1 = run_gate("verify_pack.py", pack)
    g2, t2 = run_gate("verify_exam_anchors.py", pack)
    print(f"复跑闸1机器闸: {'✅' if g1 else '❌'} {t1}")
    print(f"复跑闸2真题核验: {'✅' if g2 else '❌'} {t2}")
    print("裁决: " + ("✅ 两闸绿+发现透明入表" if (g1 and g2) else "❌ 闸未过"))
    sys.exit(0 if (g1 and g2) else 1)


if __name__ == "__main__":
    main()
