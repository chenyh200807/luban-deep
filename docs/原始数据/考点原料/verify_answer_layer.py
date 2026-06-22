#!/usr/bin/env python3
"""案例题作答层 · 采分点锚定机器闸 v1 (确定性, fail-closed).

治本背景: 前 3 批样板被异源审抓出"凭真题/凭空另造采分点 + 冒充教材锚"(违反 skill
红线1 采分点 ground truth 归 signed R5)。verify_pack.py 只核"出现的 point_id 存在",
核不到"每个采分点行的锚声明与实际锚是否一致" —— 这是盲区。本闸补这一刀。

—— v0→v1 关键纠偏(2026-06-22) ——
v0 用"真题锚而无 signed point_id = 造点违规"做唯一判据, **太宽**: 它把两类混为一谈:
  (1) 冒充教材锚: 行坐在 🟢 簇 / 标"现行有效", 只锚真题、无 point_id、不披露 = 真违规 (K01 W8)
  (2) 诚实真题侧披露: 编译库零教材锚, 行如实标"真题侧·待补规范锚" = 合规 (S07 coarse_review)
v0 会把 (2) 也判违规, 等于逼诚实的 coarse_review 去**伪造** point_id (反向失真)。

真正的不变量 = **锚声明与实际锚一致, 不冒充教材锚**, 不是"必须有 point_id"。三分类:
  ① 有 signed point_id (ca/kc/m35) → ✅ OK
     (内容是否被篡改/方法张冠李戴 = 语义, 归异源门 run_..._cross_model_audit.py, 本闸不管)
  ② 无 point_id, 但如实披露真题侧/工程通识 + 锚证据包内真题 → ✅ 诚实披露 (S07)
  ③ 无 point_id, 有真题, 标"现行有效"/坐 🟢 簇而**不披露** → 🔴 冒充教材锚/未披露 (K01 W8, Q01 B/C/V)
  ④ 无任何锚, 非 🔵 行 → ⚠️ 待核 (漏锚或漏标 🔵)

🔵 / 工程通识 / 非采分点 / 背景注 / 对照 行 = 显式非判分眼, 跳过 (不是采分点)。

本闸**只核确定性的"锚声明 vs 实际锚一致性"**; "采分点内容是否忠实 R5 真值"是语义,
归异源门 + 人核, 本闸不管 (K01 W5 那种 point_id 在场但内容篡改, 本闸判 OK 是对的)。

用法: python3 verify_answer_layer.py [<作答层.md> ...]   (无参=审成品/全部)
"""
import re
import sys
import glob
import os

KAOYUAN = os.path.dirname(os.path.abspath(__file__))

SIGNED = re.compile(r"(?:ca|kc|m35):[0-9A-Za-z_]")
# 真题锚: {2015·第26题} / {2015,案例1} / `{2019,第17题}` —— 花括号/反引号后接年份
EXAM_ANCHOR = re.compile(r"[`｛{（(]\s*20\d\d|真题\s*[`｛{｛]")
# 诚实披露真题侧/工程通识来源 (不冒充教材锚) —— S07 coarse_review 的合规口径
DISCLOSE = re.compile(r"真题侧|待补规范锚|真题应用印证|真题印证|真题口径|教材未逐字|单源审")
# 显式非采分点行 (背景注/对照/工程通识) —— 跳过, 不当采分点核。
# ⚠️ 不用裸 🔵: 🔵 会作为内联注(quote截断/法规重申)出现在**真采分点行**的版本状态里,
# 裸 🔵 匹配会误跳过有 signed 锚的真采分点(Q02 C1/C2/C5 实证)。只认显式"非采分点"关键词。
NONSCORING = re.compile(r"工程通识|非\s*采分点|非新采分点|不充.{0,6}采分点|对照背景|背景注")
LABEL = re.compile(r"\*\*([A-Za-z][0-9A-Za-z#\-－]*)\*\*")


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|") and line.count("|") >= 4


def audit(md_path):
    txt = open(md_path, encoding="utf-8").read()
    signed = honest = impersonate = noanchor = 0
    violations = []  # (label, severity, reason)
    in_scoring_table = False  # 只审 §1 采分点可写化表, 不审 §2 句式/§3 批改/§4 实测表
    for raw in txt.splitlines():
        line = raw.strip()
        # 采分点定义表 = 四件套表, 判别特征 = 表头含"采分点"+"必写关键词"+("标准表达"|"版本状态")
        # (拆题示例表 `采分点|必写关键词|五维` 无标准表达/版本状态列, 回指已签采分点标签 → 排除;
        #  用"标准表达"兜底因 J01 漏了版本状态列[J01 自身四件套不合规, 已记返修], 仍须审其采分点)
        if ("采分点" in line and "必写关键词" in line
                and ("标准表达" in line or "版本状态" in line) and _is_table_row(line)):
            in_scoring_table = True
            continue
        if not _is_table_row(line):
            in_scoring_table = False
            continue
        if not in_scoring_table:
            continue  # 表格行但不在采分点表内 (句式/批改/实测表) → 不审
        if re.fullmatch(r"\|[\s\-:|]+\|?", line):
            continue
        m = LABEL.search(line)
        label = m.group(1) if m else None
        if not label:
            continue  # 无标签的不是采分点行 (说明/小计等)
        # 显式非采分点行 → 跳过。⚠️ 只在 "采分点 cell + 版本状态 cell" 两区检测,
        # **不查必写词 cell**: 必写词来源标注 `[工程通识]` 含"工程通识"会误伤真采分点行
        # (N02 R5-2/R5-5 实证)。非采分点状态只合法声明于采分点cell或版本状态cell。
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        zone = (cells[1] + " " + cells[-2]) if len(cells) >= 3 else line
        if NONSCORING.search(zone):
            continue
        # 错因码-only 行 (E07/M08 纯码 + 行短) → 跳过
        if re.fullmatch(r"[EM]\d{2}", label) and len(line) < 70:
            continue
        has_signed = bool(SIGNED.search(line))
        has_exam = bool(EXAM_ANCHOR.search(line))
        discloses = bool(DISCLOSE.search(line))
        if has_signed:
            signed += 1  # ② 内容忠实性归异源门, 本闸放过
        elif has_exam and discloses:
            honest += 1  # ② 诚实真题侧披露 (S07)
        elif has_exam:
            impersonate += 1  # ③ 冒充教材锚 / 未披露真题侧 (K01 W8)
            violations.append((label, "🔴", "真题锚无point_id且未披露真题侧(冒充教材锚)"))
        else:
            noanchor += 1  # ④ 无锚待核
            violations.append((label, "⚠️", "无锚(漏锚或漏标🔵)"))
    return signed, honest, impersonate, noanchor, violations


def main():
    args = sys.argv[1:] or sorted(glob.glob(os.path.join(KAOYUAN, "成品/*_案例题作答层样板.md")))
    print(f"{'pack':6} {'✅signed':8} {'✅真题侧':8} {'🔴冒充':7} {'⚠️无锚':7} 裁决")
    total_red = 0
    fails = []
    for f in args:
        pid = re.match(r"([A-Z]\d+)", os.path.basename(f))
        pid = pid.group(1) if pid else os.path.basename(f)
        s, h, imp, n, viol = audit(f)
        total_red += imp
        verdict = "❌FAIL" if imp > 0 else ("⚠️待核" if n > 0 else "✅PASS")
        if imp > 0:
            fails.append((pid, [v for v in viol if v[1] == "🔴"]))
        print(f"{pid:6} {s:<8} {h:<8} {imp:<7} {n:<7} {verdict}")
    print("─" * 56)
    print(f"总计 🔴冒充教材锚(铁违规): {total_red} 行, 涉及 {len(fails)} 个 pack")
    for pid, viol in fails:
        labels = ", ".join(v[0] for v in viol)
        print(f"  {pid}: {labels}")
    return 1 if total_red > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
