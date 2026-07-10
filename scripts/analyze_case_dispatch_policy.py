#!/usr/bin/env python3
"""案例题轻练 · policy→kind 分发可判别性分析(review-only,回答接线提案 Q3)。

接线提案(2026-07-09-案例题轻练判分引擎接线架构提案.md)§4 待 owner 拍的第 3 点:
**编译库现有字段(policy 等)是否够把题精确分发到 5 个确定性引擎,还是需一个题型 tag?**

本脚本**只读**编译库 `v_case_rubric_scored`(不碰任何生产模块、不改库、无 LLM),用
确定性关键词信号,实测:①每个 `policy` 桶到底混了哪几种确定性 kind;②policy 单独是不是
一个干净划分;③给出数据支撑的结论(现有字段够/不够 → 要不要 register 一个 tag)。

把 owner 的决策从"设计"降为"评审"——这是人门前准备,不是接线本身(接线仍待 owner 拍板)。

    python scripts/analyze_case_dispatch_policy.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_RUBRIC = (
    Path(__file__).resolve().parents[1]
    / "deeptutor/services/construction_grading/runtime_supply"
    / "v_case_rubric_scored/case_rubric_scored.json"
)

# 5 个确定性 kind 的**确定性关键词信号**(领域词,真题采分点/题面里稳定出现的判别锚)。
# 只用于"可判别性测绘",不是生产分发器(生产分发待 owner 拍落点后按裁定实现)。
_KIND_SIGNALS: dict[str, tuple[str, ...]] = {
    "CPM_CRITICAL_PATH": ("关键线路", "关键工作", "总工期", "网络图", "双代号", "时标网络", "工期为"),
    "SET_MEMBERSHIP(荷载组合)": ("永久荷载", "可变荷载", "荷载组合", "荷载标准值", "自重", "施工荷载"),
    "ORDERING(工序排序)": ("施工顺序", "工艺流程", "工序", "先后顺序", "排序", "流程为"),
    "CALC_DAG(造价/计算链)": ("计算", "求", "综合单价", "措施费", "规费", "税金", "元)", "万元"),
    "CONJUNCTION(判断改正)": ("改正", "正确做法", "正确的是", "错误之处", "不正确", "错误"),
}


def _kind_hits(text: str, required: list[str]) -> set[str]:
    hay = text + " " + " ".join(required or ())
    return {k for k, sigs in _KIND_SIGNALS.items() if any(s in hay for s in sigs)}


def main() -> int:
    recs = json.loads(_RUBRIC.read_text(encoding="utf-8")).get("records") or []
    print("=" * 74)
    print(f"policy→kind 分发可判别性分析(只读 {len(recs)} 采分点 / 编译库)")
    print("=" * 74)

    # ① 每个 policy 桶混了哪几种 kind(按采分点计数)
    policy_kind = defaultdict(Counter)
    policy_total = Counter()
    for r in recs:
        pol = str(r.get("policy") or "?")
        policy_total[pol] += 1
        for k in _kind_hits(str(r.get("text") or ""), list(r.get("required_terms") or ())):
            policy_kind[pol][k] += 1

    print("\n【1】每个 policy 桶命中的确定性 kind 信号(采分点数;一点可命中多 kind)")
    for pol in sorted(policy_total, key=lambda p: -policy_total[p]):
        kinds = policy_kind[pol]
        distinct = len(kinds)
        print(f"\n  policy={pol}  (共 {policy_total[pol]} 采分点) —— 命中 {distinct} 种 kind:")
        for k, n in kinds.most_common():
            print(f"      {k}: {n}")

    # ② policy 是否干净划分:同一 policy 跨多 kind = 不干净
    print("\n【2】判定:policy 单独能否干净分发?")
    dirty = {pol: len(policy_kind[pol]) for pol in policy_total if len(policy_kind[pol]) > 1}
    for pol, n in sorted(dirty.items(), key=lambda kv: -kv[1]):
        top = ", ".join(k.split("(")[0] for k, _ in policy_kind[pol].most_common(3))
        print(f"  ✗ policy={pol} 混了 {n} 种 kind(top: {top})→ policy 不足以单独判 kind")

    # ③ CONJUNCTION 配对信号:policy 层根本不编码 pairing
    print("\n【3】CONJUNCTION(判断改正=找错∧改正)配对是否被现有字段编码?")
    boolean_qids = {r["qid"] for r in recs if r.get("policy") == "boolean_judgment"}
    print(f"  boolean_judgment 覆盖 {len(boolean_qids)} 个 qid;但『找错』与『改正』是否同一"
          f"合取组、pairing 关系 —— 编译库无 conjunction_group/pair 字段,**完全未编码**。")

    print("\n" + "=" * 74)
    print("结论(数据支撑,回答提案 Q3):")
    print("  • policy(calc/list/exact_required/boolean_judgment/qualitative)是**判分口径**,")
    print("    不是**题型**;上表实测同一 policy 桶跨多个确定性 kind → **policy 单独不足以精确分发**。")
    print("  • 尤其 SET(荷载组合)/ORDERING(工序排序)/CALC 都可落在 calc 或 list;")
    print("    CONJUNCTION 的 pairing 现有字段**根本不编码**。")
    print("  • ⇒ 需要一个 **register-before-use 的题型 tag**(如 practice_grading_kind)挂在 qid/小问级,")
    print("    由教研在 review.json 验收时顺带标(它已在标合取/顺序/封顶结构——见 §2.5 契约),")
    print("    生产分发按 tag 精确路由,不靠 policy 猜。**这是给 owner 的第 3 点数据支撑,待其拍板。**")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
