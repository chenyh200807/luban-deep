#!/usr/bin/env python3
"""autofix v2 — 自动应用高可信(≥2源收敛)jury发现 (真量产最后一公里).

用法: python autofix_v2.py <pack.md> <jury_sidecar.json>
安全边界: 只自动应用 count≥2 的高可信发现; 且不让LLM自由改正文——reviser出"最小手术编辑"
{old_string(从pack逐字复制的唯一短串), new_string}, 脚本验证 old_string 在pack里唯一存在才应用,
否则跳过+记录. 改完复跑两闸兜底. 单源候选仍只记录(autofix v1 行为).
"""
import sys, os, re, json, subprocess
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

def reviser(pack_text, hi):
    """让 DeepSeek-v4-pro 把高可信发现转成最小手术编辑."""
    findings = "\n".join(f"{i+1}. [{'+'.join(f.get('flagged_by',[]))}|{f['count']}] {f['issue']} @ {f.get('location','')} → 建议:{f.get('fix','')}" for i,f in enumerate(hi))
    sys_p = "你是手术编辑器,严谨保守。"
    usr = f"""下面是一份考点pack 和 多个异源AI收敛(≥2源)的高可信问题。对【每一条】给一个最小手术编辑,把问题改掉(通常=三色降级🟢→🔵/🔴 + 加简短括注说明,或补'待GB50300核'等)。
严格要求:
- old_string 必须从 pack 里【逐字复制】一段【唯一】能定位的短串(含要改的三色标记/措辞),不确定能否唯一定位就【跳过该条】(宁可不改)。
- new_string = 改后的串(保留原信息,加降级标记和括注)。
- 只输出 JSON 数组,每元素 {{"ref":条号, "old_string":"...", "new_string":"...", "note":"改了什么"}}。跳过的条不输出。不要解释。

=== 高可信发现 ===
{findings}

=== PACK ===
{pack_text}"""
    from openai import OpenAI
    cli = OpenAI(base_url="https://api.deepseek.com", api_key=key("DEEPSEEK_API_KEY"))
    r = cli.chat.completions.create(model="deepseek-v4-pro", messages=[{"role":"system","content":sys_p},{"role":"user","content":usr}], temperature=0, timeout=300)
    t = r.choices[0].message.content.replace("```json","").replace("```","")
    i,j = t.find("["), t.rfind("]")
    return json.loads(t[i:j+1]) if i>=0 else []

def run_gate(script, pack):
    r = subprocess.run(["python3", os.path.join(ROOT,"docs/原始数据/考点原料",script), pack], capture_output=True, text=True, cwd=ROOT)
    return ("PASS" in r.stdout or "全部确定性命中" in r.stdout), (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

def main():
    pack, jury = sys.argv[1], sys.argv[2]
    findings = json.load(open(jury, encoding="utf-8"))
    hi = [f for f in findings if f.get("count",0) >= 2]
    print(f"=== autofix v2: {os.path.basename(pack)} ===")
    print(f"高可信(≥2源) {len(hi)} 条 → 让 DeepSeek-v4-pro 转成手术编辑")
    if not hi:
        print("无高可信发现, 无需自动应用 (单源候选见 autofix v1 的 §9 记录)"); return
    text = open(pack, encoding="utf-8").read()
    edits = reviser(text, hi)
    applied, skipped = [], []
    for e in edits:
        old, new = e.get("old_string",""), e.get("new_string","")
        if old and old in text and text.count(old) == 1 and new:
            text = text.replace(old, new, 1)
            applied.append(e)
        else:
            skipped.append({**e, "_reason": "old_string 不存在或不唯一" if old else "空"})
    # 追加自动应用记录
    log = [f"\n### 9.x autofix v2 自动应用记录\n",
           f"高可信 {len(hi)} 条; 自动应用 {len(applied)} 条; 跳过(无法唯一定位,留人工) {len(skipped)} 条。\n",
           "| ref | 改了什么 | 状态 |", "|---|---|---|"]
    for e in applied: log.append(f"| {e.get('ref')} | {e.get('note','')[:50]} | ✅自动应用 |")
    for e in skipped: log.append(f"| {e.get('ref')} | {e.get('note','')[:50]} | ⚠跳过·留人工 |")
    text = text.rstrip() + "\n" + "\n".join(log) + "\n"
    open(pack, "w", encoding="utf-8").write(text)
    g1,t1 = run_gate("verify_pack.py", pack)
    g2,t2 = run_gate("verify_exam_anchors.py", pack)
    print(f"自动应用 {len(applied)} / 跳过 {len(skipped)}")
    print(f"复跑闸1: {'✅' if g1 else '❌'} {t1}")
    print(f"复跑闸2: {'✅' if g2 else '❌'} {t2}")
    print("裁决: " + ("✅ v2闭环完成(高可信自动改+两闸绿)" if (g1 and g2) else "❌ 改后闸未过,回滚检查"))
    sys.exit(0 if (g1 and g2) else 1)

if __name__ == "__main__":
    main()
