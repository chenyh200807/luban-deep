#!/usr/bin/env python3
"""案例题作答层 · 采分点锚定机器闸 (确定性, fail-closed).

治本: 前 3 批样板被异源审抓出"凭真题/凭空另造采分点"(违反 skill 红线1 采分点
ground truth 归 signed R5)。verify_pack.py 只核"出现的 point_id 存在", 核不到
"每个采分点行是否都锚 signed point_id" —— 这是盲区。本闸补这一刀:

  采分点行的"锚"必须是 signed point_id (ca:/kc:/m35:)。
  锚真题 {年份} 而无 signed point_id = 违规 (凭真题造采分点, K01 W8 类)。
  无任何锚 = 待核 (可能 🔵 作答策略行, 也可能漏锚)。

只核确定性的"锚类型"; "内容是否篡改/必写是否夸大/方法是否张冠李戴"是语义,
归异源门 (run_luban_answer_layer_cross_model_audit.py) + 人核, 本闸不管。

用法: python3 verify_answer_layer.py [<作答层.md> ...]   (无参=审成品/全部)
"""
import re
import sys
import glob
import os

KAOYUAN = os.path.dirname(os.path.abspath(__file__))
SIGNED = re.compile(r"(?:ca|kc|m35):[0-9A-Za-z_]")
EXAM = re.compile(r"真题\s*[`｛{]|\{20\d\d")
LABEL = re.compile(r"\*\*([A-Z][0-9A-Za-z\-]*)\*\*")
# 采分点行: | 开头 + 含"锚"字 (有锚字段才是采分点行, 排除说明/小计/错因码行)
BLUE = re.compile(r"🔵|作答策略|非\s*signed|教材锚|邻接|待补")


def audit(md_path):
    txt = open(md_path, encoding="utf-8").read()
    rows = [l for l in txt.splitlines() if l.startswith("|") and "锚" in l]
    signed = exam_only = noanchor = 0
    violations = []
    for l in rows:
        m = LABEL.search(l)
        label = m.group(1) if m else "?"
        # 错因码行 (E07/M08 等纯码 + 无采分点内容) 跳过: label 是 E/M 两位码且行短
        if re.fullmatch(r"[EM]\d{2}", label) and len(l) < 60:
            continue
        has_signed = bool(SIGNED.search(l))
        has_exam = bool(EXAM.search(l))
        if has_signed:
            signed += 1
        elif has_exam:
            exam_only += 1
            violations.append((label, "🔴锚真题无signed(凭真题造点)"))
        elif not BLUE.search(l):
            noanchor += 1
            violations.append((label, "⚠️无锚(漏锚或未标🔵)"))
    return signed, exam_only, noanchor, violations


def main():
    args = sys.argv[1:] or sorted(glob.glob(os.path.join(KAOYUAN, "成品/*_案例题作答层样板.md")))
    print(f"{'pack':6} {'signed锚':8} {'🔴真题造点':10} {'⚠️无锚':7} 裁决")
    total_red = 0
    fails = []
    for f in args:
        pid = re.match(r"([A-Z]\d+)", os.path.basename(f))
        pid = pid.group(1) if pid else os.path.basename(f)
        s, e, n, viol = audit(f)
        total_red += e
        verdict = "❌FAIL" if e > 0 else ("⚠️待核" if n > 0 else "✅PASS")
        if e > 0:
            fails.append((pid, [v for v in viol if "🔴" in v[1]]))
        print(f"{pid:6} {s:<8} {e:<10} {n:<7} {verdict}")
    print("─" * 50)
    print(f"总计 🔴凭真题造采分点(铁违规): {total_red} 行, 涉及 {len(fails)} 个 pack")
    for pid, viol in fails:
        labels = ", ".join(v[0] for v in viol)
        print(f"  {pid}: {labels}")
    return 1 if total_red > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
