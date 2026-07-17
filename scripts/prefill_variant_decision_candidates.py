#!/usr/bin/env python3
"""Prefill variant decision CANDIDATES (machine drafts, NEVER signed).

为签发变体银行的 practice 资格接入（设计：docs/plan/鲁班移动端提分闭环/
2026-07-16-variant-eligibility-design.md）生成逐条 decision 机器候选：

- fact_id：按 (rule_group, correct_statement) 聚类查本脚本的 per-pack 人工映射表
  （与 compiled MCQ 同一命名空间 ``{pack小写}-fact-{语义slug}``）；
- skeleton_id：``{pack小写}-vskel-{rule_group小写}-{ok|bad}`` 机械派生；
- probe_role：每个 fact 内按 variant_id 排序交替 immediate_confirm / d1_probe；
- temptation / loss_reason：按 rule_group 模板 + params 生成的初稿（机器候选，
  暖语气、禁「看穿/识破」类审视词）；
- 佐证：同 pack 签发考点卡的教材原文（point_id 精确 join，join 不中如实留空；
  join 到的 quote 还须与 fact 主题一致——bigram 重叠核验，防 E5 类错锚）
  与 compiled MCQ 疑似同 fact 题号（CJK bigram 重叠，候选性质）。

富化文案纪律（2026-07-16 对抗审查裁决，S05/N01 终轮 REFUTED 后收紧）：
  * loss_reason 只允许三类内容：教材/编译点原文支持的事实、正确表述
    （correct_statement）、与题面的差异点；禁一切无来源机理句
    （如「失去上级保护」「松动打火」「无法准确分断」类工程机理）；
  * 禁判分承诺句（如「通常单独设采分点」「缺一件丢一分」「把对判错同样丢分」
    「判断方向错了同样丢分」——无评分统计来源）；判断题的方向错误只用
    「与规范要求一致/不符」表述，不提丢分；
  * 禁无来源泛化记法（如 C 组「环境越危险，电压档位越低」——教材只列各场所
    具体限值，未定义危险度序列）；
  * temptation 只写心理层（为什么顺手会判错），不发明工程机理、
    不虚构题面外事实。

无有效锚 fact 剔除（2026-07-16 终轮裁决）：kc_anchor/textbook_quote 双空、且
唯一真题锚经异源核验不支撑该 fact 断言者，视为「无任何有效锚」，其全部变体
不进本批候选（bank 只读、原样保留，待补可读教材/规范原文锚后再入批）。生成器
无法语义判定真题锚支撑度，故由对抗审查裁决在 ``_PACK_EXCLUDED_FACTS`` 登记。

Hard safety guarantees（同 prefill_practice_review_anchors.py 惯例）：
  * bank 只读，绝不修改；
  * ``decision.review`` 恒为 pending、零签名、checks 全 False——机器绝不代签；
  * 输出携带 ``"machine_candidates_only": true``，下游工具不得误当人签决定；
  * 输出确定性（无时间戳），可重跑逐字节比对。

Usage:
    python scripts/prefill_variant_decision_candidates.py S05
    python scripts/prefill_variant_decision_candidates.py S05 --out-dir /tmp/x
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.luban_lesson.variant_eligibility import (  # noqa: E402
    VARIANT_DECISION_SCHEMA,
    VARIANT_PROBE_ROLES,
    decision_identity_sha256,
    review_signature_envelope_sha256,
    variant_content_sha256,
)

CANDIDATES_SCHEMA = "luban_variant_decision_candidates.v1"
DEFAULT_BASE_DIR = REPO_ROOT / "docs" / "原始数据" / "考点原料" / "成品"
DEFAULT_OUT_DIR = DEFAULT_BASE_DIR / "_practice_review_packets"
COMPILED_DIR = REPO_ROOT / "deeptutor" / "services" / "luban_lesson" / "compiled"
_CJK_RE = re.compile(r"[一-鿿]")
_MCQ_MATCH_THRESHOLD = 0.30
_MCQ_TOP_K = 3


def _num(value: Any) -> str:
    """0.7 -> '0.7', 12.0 -> '12'——文案里的数字口径与题面一致。"""
    text = f"{value}"
    return text[:-2] if text.endswith(".0") else text


# --------------------------------------------------------------------- S05 表
# fact 映射：(rule_group, correct_statement) → 与 compiled MCQ 同一命名空间的
# fact slug（人工审定命名先例的机器候选；MCQ 侧签发时必须写同一字符串才互认）。
_S05_FACTS: dict[tuple[str, str], str] = {
    ("B-send", "送电顺序应为总配电箱→分配电箱→开关箱"): "s05-fact-send-power-order",
    ("B-stop", "停电顺序应为开关箱→分配电箱→总配电箱"): "s05-fact-stop-power-order",
    ("C-voltage", "手持灯具照明电压不得大于 36V"): "s05-fact-handheld-lamp-36v",
    ("C-voltage", "金属容器内照明电压不得大于 12V"): "s05-fact-metal-container-12v",
    ("C-voltage", "锅炉内照明电压不得大于 12V"): "s05-fact-boiler-12v",
    (
        "D-one-switch",
        "每台用电设备必须有各自专用的开关箱，严禁 2 台及以上共用",
    ): "s05-fact-one-device-one-switchbox",
    (
        "D-one-switch",
        "配电箱、开关箱电源进线端严禁采用插头插座做活动连接",
    ): "s05-fact-no-plug-socket-inlet",
    ("E-bury", "电缆直接埋地敷设深度不应小于 0.7m"): "s05-fact-cable-burial-depth-07m",
    (
        "E-color",
        "N 线必须为蓝色、PE 线必须为黄绿双色，不得混用",
    ): "s05-fact-n-pe-color-code",
    ("F-mgmt", "电工须经职业资格考试合格后持证上岗"): "s05-fact-electrician-certified",
    ("F-mgmt", "用电设备拆除应由电工完成"): "s05-fact-removal-by-electrician",
    ("F-mgmt", "总容量 50kW 及以上应编制用电组织设计"): "s05-fact-50kw-org-design",
    (
        "F-mgmt",
        "50kW 以下编制安全用电和电气防火措施即可",
    ): "s05-fact-below-50kw-measures",
    (
        "F-mgmt",
        "装饰装修阶段应补充编制单项施工用电方案",
    ): "s05-fact-fitout-supplement-plan",
    ("X-distance", "开关箱与配电箱的间距不得大于 30m"): "s05-fact-switchbox-distance-30m",
}


def _s05_b_order(v: dict[str, Any]) -> tuple[str, str]:
    op = str(v["params"].get("op") or "")
    label, other = ("送电", "停电") if op == "send" else ("停电", "送电")
    correct = (
        "总配电箱→分配电箱→开关箱" if op == "send" else "开关箱→分配电箱→总配电箱"
    )
    order = "→".join(str(x) for x in v["params"].get("order") or [])
    if v["expected_ok"]:
        return (
            f"{label}顺序与{other}顺序容易互相记串，看到正确顺序反而不敢确认。",
            f"{label}操作顺序应为{correct}，本题顺序与规范要求一致；"
            "记法：送电从总到开、停电从开到总，两句连着背。",
        )
    other_correct = (
        "开关箱→分配电箱→总配电箱" if op == "send" else "总配电箱→分配电箱→开关箱"
    )
    if order == other_correct:
        temptation = (
            f"「{order}」看着眼熟——它正是{other}的正确顺序，"
            f"最容易顺手当成{label}顺序判「妥当」。"
        )
    else:
        temptation = (
            f"三级箱都出现了，顺序「{order}」乍看齐全，容易只核对"
            "「有没有」而漏核对「先后」。"
        )
    return (
        temptation,
        f"{label}操作顺序应为{correct}；本题给的是「{order}」，与正确顺序"
        "不符即违规，答题要点是写明正确顺序。",
    )


def _s05_c_voltage(v: dict[str, Any]) -> tuple[str, str]:
    place = str(v["params"].get("place") or "")
    surface_v = _num(v["params"].get("surface_v"))
    limit_v = _num(v["params"].get("limit_v"))
    if v["expected_ok"]:
        return (
            f"36V/24V/12V 三档限值容易混记，见到{place}用 {surface_v}V 会拿不准。",
            f"{place}照明电压限值为不大于 {limit_v}V，{surface_v}V 未超限，"
            "属于妥当做法。",
        )
    return (
        f"只记得「特殊场所要用安全特低电压」，容易忽略{place}的具体限值档位。",
        f"{place}照明电压不得大于 {limit_v}V；{surface_v}V 已超限即违规，"
        f"答题要点是写明「不大于 {limit_v}V」。",
    )


def _s05_d_one_switch(v: dict[str, Any]) -> tuple[str, str]:
    if v["params"].get("plug_socket_inlet"):
        return (
            "插头插座平时最常见，放在配电箱进线端容易觉得「方便检修」。",
            "配电箱、开关箱电源进线端严禁采用插头插座做活动连接；"
            "本题在进线端使用插头插座即违规。",
        )
    machine = str(v["params"].get("machine") or "用电设备")
    share = int(v["params"].get("share_count") or 1)
    if v["expected_ok"]:
        return (
            "「一机一箱」太熟了，反而会怀疑单独设箱是不是多余。",
            f"每台用电设备必须有各自专用的开关箱，{machine}单独设箱正是规范"
            "要求，与规范要求一致。",
        )
    return (
        f"{share} 台同类{machine}挨得近，共用一个开关箱看起来省料又省事。",
        f"每台用电设备必须有各自专用的开关箱，严禁 2 台及以上用电设备"
        f"（含插座）共用一个开关箱；本题 {share} 台{machine}共用即违规。",
    )


def _s05_e_bury(v: dict[str, Any]) -> tuple[str, str]:
    depth = _num(v["params"].get("depth_m"))
    threshold = _num(v["params"].get("threshold_m"))
    if v["expected_ok"]:
        return (
            f"{threshold}m 这个数字容易与其他埋深/间距数字混记，"
            f"见到 {depth}m 会犹豫。",
            f"电缆直接埋地敷设深度不应小于 {threshold}m，{depth}m 已满足要求，"
            "属于妥当做法。",
        )
    return (
        f"埋深 {depth}m 已经「埋进土里」了，容易凭感觉觉得够深。",
        f"电缆直接埋地敷设深度不应小于 {threshold}m；{depth}m 未达到最小埋深"
        f"即违规，答题要点是写明「不应小于 {threshold}m」。",
    )


def _s05_e_color(v: dict[str, Any]) -> tuple[str, str]:
    n_color = str(v["params"].get("n") or "")
    pe_color = str(v["params"].get("pe") or "")
    if v["expected_ok"]:
        return (
            "N 线与 PE 线的颜色规定容易记反，看到正确配色反而不敢确认。",
            "N 线必须为蓝色、PE 线必须为黄绿双色，本题配色正确；"
            "记法：零线蓝、地线黄绿。",
        )
    return (
        "只记得「要用蓝色和黄绿双色」，容易忽略各自对应哪根线、能不能混用。",
        f"N 线必须为蓝色、PE 线必须为黄绿双色且不得混用；本题 N 线={n_color}、"
        f"PE 线={pe_color}，与规定色标不符即违规。",
    )


_S05_F_MGMT: dict[str, tuple[str, str]] = {
    "S05-F-mgmt-064": (
        "现场赶工期时「先干着、证再补」的情形常见，容易觉得情有可原。",
        "电工必须经职业资格考试合格、持证后方可上岗作业；未取得职业资格证"
        "即上岗接线属于违规，答题要写明「持证上岗」。",
    ),
    "S05-F-mgmt-065": (
        "安全员天天盯现场安全，由他拆除用电设备听起来顺理成章。",
        "用电设备拆除应由电工完成；题面未证明该安全员具备电工资格，"
        "答题要点是「应由（持证）电工完成」。",
    ),
    "S05-F-mgmt-066": (
        "题面里 60kW 只是一个不起眼的数字，容易被当成普通参数扫过，"
        "忽略 50kW 这条容量线。",
        "总容量 50kW 及以上应编制施工用电组织设计；60kW 已达线未编制即违规，"
        "答题要点是点出容量门槛与「用电组织设计」名称。",
    ),
    "S05-F-mgmt-067": (
        "题面只出现「安全用电和电气防火措施」而没出现「用电组织设计」，"
        "容易觉得少编了东西而判违规，忽略容量只有 40kW、未到 50kW 门槛。",
        "总容量 50kW 以下编制安全用电和电气防火措施即可；40kW 编制了措施"
        "已满足要求，属于妥当做法。",
    ),
    "S05-F-mgmt-068": (
        "开工时已编过用电方案，容易以为一份方案管到工程收尾。",
        "进入装饰装修阶段应补充编制单项施工用电方案；未补充编制即违规。",
    ),
}


def _s05_f_mgmt(v: dict[str, Any]) -> tuple[str, str]:
    drafts = _S05_F_MGMT.get(str(v.get("variant_id") or ""))
    if drafts is None:
        raise KeyError(f"F-mgmt 变体缺人工初稿: {v.get('variant_id')}")
    return drafts


def _s05_x_distance(v: dict[str, Any]) -> tuple[str, str]:
    dist = _num(v["params"].get("dist_m"))
    threshold = _num(v["params"].get("threshold_m"))
    if v["expected_ok"]:
        return (
            f"{threshold}m 的箱间距限值容易与其他间距数字混记，"
            f"见到 {dist}m 会犹豫。",
            f"开关箱与配电箱的间距不得大于 {threshold}m，{dist}m 未超限，"
            "属于妥当做法。",
        )
    return (
        f"堆场空旷，把开关箱拉远一点似乎不影响使用，容易忽略 {threshold}m 上限。",
        f"开关箱与配电箱的间距不得大于 {threshold}m；{dist}m 已超限即违规，"
        f"答题要点是写明「不得大于 {threshold}m」。",
    )


_S05_DRAFTS: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "B-send": _s05_b_order,
    "B-stop": _s05_b_order,
    "C-voltage": _s05_c_voltage,
    "D-one-switch": _s05_d_one_switch,
    "E-bury": _s05_e_bury,
    "E-color": _s05_e_color,
    "F-mgmt": _s05_f_mgmt,
    "X-distance": _s05_x_distance,
}


# --------------------------------------------------------------------- N01 表
# fact 映射：与 compiled MCQ（n01.practice.authority.json）完全同一命名空间。
# A-line / B-expr / C-delay / G-logic 复用 MCQ 已签 fact_id（同 fact 互认——尤其
# C-delay = 关键工作 TF=0 族，与 compiled 侧 `n01-fact-critical-work-zero-float`
# 同字符串即互认）；D / E / F 三族 MCQ 侧尚未 fact 标注，本侧按 (rule_group,
# correct_statement) 聚类起语义 slug，作为该 fact 的命名先例。
_N01_FACTS: dict[tuple[str, str], str] = {
    (
        "A-line",
        "并列最长路径必须全部列出（2015/2020 均两条）；线路须落到具体线路且节点连续无跳号；关键工作按「总时差最小」判据判定并落到具体工作",
    ): "n01-fact-parallel-critical-paths",
    (
        "B-expr",
        "总工期 = 关键线路上各工作持续时间之和，答案须「线路 + 算式 + 单位」三件齐全",
    ): "n01-fact-duration-along-critical-path",
    (
        "C-delay",
        "延误 ≤ 该工作总时差则不影响总工期；延误工作在关键线路上（总时差为 0）或延误超过总时差则影响总工期，必须比较「延误 vs 总时差」后下结论",
    ): "n01-fact-critical-work-zero-float",
    (
        "D-adjust",
        "进度计划调整方法为封闭五类：关键工作调整（重点）/逻辑关系调整/重新编制计划/非关键工作调整/资源调整",
    ): "n01-fact-schedule-adjustment-methods",
    (
        "E-monitor",
        "进度监测内容为封闭枚举：记录实际时间/观测关键线路/检查非关键工作/核查逻辑关系/收集变更",
    ): "n01-fact-progress-monitoring-content",
    (
        "F-procedure",
        "应按「绘图（含补虚工作）→ 计算时间参数（各路径长/时差）→ 确定关键线路→ 编制/实施」顺序进行，顺序不可乱",
    ): "n01-fact-network-procedure-order",
    (
        "G-logic",
        "题干紧前逻辑不全应先补虚工作/调节点（2015：3—4 之间增加一个虚工作），再在正确的网络图上计算关键线路",
    ): "n01-fact-dummy-activity-logic",
}


def _n01_a_line(v: dict[str, Any]) -> tuple[str, str]:
    params = v["params"]
    if "criterion" in params:  # 关键工作判定依据面
        if v["expected_ok"]:
            return (
                "「总时差最小」这个判据平时用得少，看到正确写法反而怀疑是不是漏了什么。",
                "关键工作的判据就是「总时差最小」，且必须落到本网络图的"
                "具体工作上；本题判据与落点都对，与作答要求一致。",
            )
        return (
            "只背下「关键工作 = 总时差最小」这句判据，容易以为写出判据就够了。",
            "判据对但没落到本网络图的具体工作，不满足「落到具体工作」的要求；"
            "答题要点是判据 +「本图哪几项工作总时差最小」都写出。",
        )
    # 关键线路书写面
    total = int(params.get("lines_total") or 0)
    listed = int(params.get("lines_listed") or 0)
    if not v["expected_ok"] and listed < total:
        return (
            "两条线路一样长，写出其中一条看着「已经找到关键线路」了，"
            "容易就此收笔。",
            f"并列最长路径必须全部列出（本题 {total} 条只写了 {listed} 条），"
            "漏列即未全部列出；答题要点是把并列的关键线路逐条写全。",
        )
    if not v["expected_ok"] and not params.get("concrete_path"):
        return (
            "「最长的线路就是关键线路」这句判据本身没错，容易以为写到这就算答完。",
            "只写判据、未落到本图的具体线路（哪几个节点串成的路径），"
            "不满足「落到具体线路」的要求；要点是把线路节点逐一写出。",
        )
    if not v["expected_ok"] and not params.get("nodes_continuous"):
        return (
            "线路里的节点看着都在，容易只核对「有没有这些点」而漏核对前后连不连得上。",
            "写出的关键线路节点跳号、前后不连续，不能构成从开始到结束的连续路径；"
            "答题要点是节点连续无跳号地贯通全线。",
        )
    return (
        "关键线路的正确写法要素多，看到一条完整线路反而担心是不是还少了什么。",
        "本题关键线路落到了具体路径、节点连续无跳号，写法完整，"
        "与作答要素一致。",
    )


def _n01_b_expr(v: dict[str, Any]) -> tuple[str, str]:
    params = v["params"]
    if v["expected_ok"]:
        return (
            "总工期只要一个数就够了？看到「线路 + 算式 + 单位」全写反而怀疑是否啰嗦。",
            "总工期 = 关键线路上各工作持续时间之和，答案须「线路 + 算式 + 单位」"
            "三件齐全；本题三件都在，与作答要求一致。",
        )
    if params.get("sum_along") == "noncritical":
        return (
            "算式、单位都规整，容易只核对「算得对不对」而漏看是沿哪条线路求和的。",
            "总工期必须沿关键线路求和；本题沿非关键线路加总，路径选错则结果错，"
            "答题要点是先定关键线路再沿它求和。",
        )
    return (
        "答案直接给出一个数字，看着干净利落，容易觉得「结果对就行」。",
        "只写数字、缺线路与算式，不满足「线路 + 算式 + 单位」三件齐全的"
        "要求；答题要点是三件都写出。",
    )


def _n01_c_delay(v: dict[str, Any]) -> tuple[str, str]:
    params = v["params"]
    tf = _num(params.get("tf")) if params.get("tf") is not None else None
    delay = _num(params.get("delay")) if params.get("delay") is not None else None
    on_critical = bool(params.get("on_critical"))
    if on_critical:  # 关键线路上，总时差为 0
        if v["expected_ok"]:
            return (
                "关键工作听起来「最重要」，反而会犹豫它延误到底算不算数。",
                "该工作在关键线路上、总时差为 0，延误即影响总工期；"
                "本题判「影响总工期」正确，判断链要写明「TF=0 → 影响总工期」。",
            )
        return (
            "总觉得任何工作都能挤出点机动时间，容易顺手给关键工作也留一份缓冲。",
            "关键线路上工作总时差为 0，延误即影响总工期；"
            "本题误判为「不影响」，要点是先认定 TF=0 再下「影响」的结论。",
        )
    # 非关键工作，delay 与 tf 比较
    if v["expected_ok"]:
        return (
            f"一看到「延误」两个字就担心工期，容易忘了先和 {tf} 的总时差比一比。",
            f"该工作是非关键工作、总时差 {tf}，延误 {delay} 未超过总时差，"
            "不影响总工期；判读链要写明「延误 vs 总时差」的比较再下结论。",
        )
    return (
        f"「延误了就会拖工期」是最顺手的直觉，容易跳过与 {tf} 总时差的比较。",
        f"该工作总时差 {tf}、延误 {delay} 未超总时差，本不影响总工期；"
        "本题误判为「拖延」，要点是先比「延误 vs 总时差」再下结论，不能凭直觉。",
    )


def _n01_d_adjust(v: dict[str, Any]) -> tuple[str, str]:
    method = str(v["params"].get("method") or "")
    if v["expected_ok"]:
        return (
            f"进度调整方法有五类，「{method}」是否算一类容易记不牢。",
            f"进度计划调整方法为封闭五类：关键工作调整（重点）/逻辑关系调整/重新编制"
            f"计划/非关键工作调整/资源调整，「{method}」正是其中一类。",
        )
    return (
        f"五类调整方法里，「{method}」名字不如「压缩关键工作」直白，容易被漏认。",
        f"「{method}」确属进度计划调整方法五类之一；本题误判为「不属于」，"
        "答题要点是把五类方法记全，别漏项。",
    )


def _n01_e_monitor(v: dict[str, Any]) -> tuple[str, str]:
    item = str(v["params"].get("item") or "")
    if v["expected_ok"]:
        return (
            f"监测内容和调整动作容易混，「{item}」到底算监测还是算调整拿不准。",
            f"进度监测内容为封闭枚举：记录实际时间/观测关键线路/检查非关键工作/"
            f"核查逻辑关系/收集变更，「{item}」正是其中一项。",
        )
    return (
        f"「{item}」听着像日常工作，容易觉得它不属于「监测」这个专门环节。",
        f"「{item}」确属进度实施监测内容之一；本题误判为「不属于」，"
        "答题要点是把监测五项内容记全，且别混入调整动作。",
    )


def _n01_f_procedure(v: dict[str, Any]) -> tuple[str, str]:
    violation = v["params"].get("violation")
    if v["expected_ok"]:
        return (
            "网络计划各环节的先后顺序背着顺，真到判对错时反而担心是不是有步骤能省。",
            "绘图应先于计算时间参数、计算时间参数应先于确定关键线路、确定关键"
            "线路应先于编制/实施；本题所列环节的相对先后顺序正确，与规范要求一致。",
        )
    if violation == "未绘图先算参数":
        return (
            "现场赶时间，图还没画就想先把数算出来，看着「效率高」。",
            "未绘图就先计算时间参数，不符合「先绘图再算参数」的相对先后顺序；"
            "绘图应先于时间参数计算。",
        )
    return (
        "时间参数看着繁琐，容易想跳过它直接「凭最长路径」定关键线路。",
        "跳过「计算时间参数」直接确定关键线路，不符合相对先后顺序；"
        "正确顺序是先算参数（各路径长/时差）再确定关键线路。",
    )


def _n01_g_logic(v: dict[str, Any]) -> tuple[str, str]:
    if v["expected_ok"]:
        return (
            "题干临时加了一条紧前关系，容易想直接在原图上接着算，觉得补图太麻烦。",
            "新增紧前逻辑（F 须 B、C 均完成）后，应先在 3—4 节点间增设虚工作补全逻辑，"
            "再在正确的网络图上算关键线路；本题先补图再计算，做法正确。",
        )
    return (
        "原图就在眼前，新增一条逻辑关系后，容易顺手在原图上直接开算。",
        "新增紧前逻辑却未调整网络图、未补虚工作，就在未补全逻辑的图上算"
        "关键线路，不满足「先补虚工作再计算」的要求；答题要点是先补虚工作/"
        "调节点，再在正确图上计算。",
    )


_N01_DRAFTS: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "A-line": _n01_a_line,
    "B-expr": _n01_b_expr,
    "C-delay": _n01_c_delay,
    "D-adjust": _n01_d_adjust,
    "E-monitor": _n01_e_monitor,
    "F-procedure": _n01_f_procedure,
    "G-logic": _n01_g_logic,
}


# 逐变体 fact 改挂（2026-07-16 N01 对抗审查 6 条 REFUTED 的裁决落地）：
# (rule_group, correct_statement) 聚类对复合 correct_statement 的 rule_group
# 分辨率不够——同组内的不同探针面必须按已签发 MCQ 的 fact 先例改挂。
_N01_FACT_OVERRIDES: dict[str, str] = {
    # A-line-005/006「关键工作判据」面：已签发 q1（判据题）归
    # n01-fact-critical-work-zero-float，不得挂并列线路 fact（名实不符）。
    "N01-A-line-005": "n01-fact-critical-work-zero-float",
    "N01-A-line-006": "n01-fact-critical-work-zero-float",
    # C-delay-010..013 非关键工作「延误 vs 总时差」是另一决策边界（已签发
    # zero-float fact 的 q1/q5/q8 均以关键工作 TF=0 为中心，同型非关键题 q7
    # 未签入该 fact）；不得静默复用，新建独立 fact 候选等待人签命名先例。
    "N01-C-delay-010": "n01-fact-delay-vs-total-float",
    "N01-C-delay-011": "n01-fact-delay-vs-total-float",
    "N01-C-delay-012": "n01-fact-delay-vs-total-float",
    "N01-C-delay-013": "n01-fact-delay-vs-total-float",
}

# 改挂新建 fact 的元信息（facts 佐证行用；机器候选，等待人签）。
_N01_EXTRA_FACTS: dict[str, tuple[str, str]] = {
    "n01-fact-delay-vs-total-float": (
        "C-delay",
        "非关键工作延误 ≤ 该工作总时差则不影响总工期，必须比较"
        "「延误 vs 总时差」后下结论",
    ),
}

# facts[] 摘要层 correct_statement 覆盖（对抗审查二轮新病 1）：改挂后旧
# fact 摘要不得再含已拆去新 fact 的「延误≤总时差不影响」子句（否则新旧
# fact 摘要语义包含 = package 级 authority 分叉）；覆盖稿两个子句均取自
# bank 已签 correct_statement（A-line 判据子句 + C-delay 关键线路子句），
# 不引入新知识。聚类 key 用的原始 statement 不受影响。
_N01_FACT_STATEMENT_OVERRIDES: dict[str, str] = {
    "n01-fact-critical-work-zero-float": (
        "关键工作按「总时差最小」判据判定并落到具体工作；"
        "延误工作在关键线路上（总时差为 0）则影响总工期"
    ),
    # F-procedure 共享 fact 失真修正（2026-07-16 终轮对抗审查裁决）：教材原文
    # 为「7 阶段 18 步骤」，不得压成「四步」；「补虚工作」仅在 2015 具体案例/
    # 讲义有锚，只属 G-logic 逻辑补图 fact，不是每个网络计划的通用必经步骤。
    # 摘要收敛为「所列环节的相对先后顺序」，只保留 bank 已支撑的相对次序断言。
    "n01-fact-network-procedure-order": (
        "绘图、计算时间参数（各路径长/时差）、确定关键线路、编制/实施等"
        "环节的相对先后顺序不可颠倒"
    ),
}


# 无有效锚 fact 剔除（2026-07-16 终轮对抗审查裁决）：kc_anchor/textbook_quote
# 双空、且唯一真题锚经异源核验不支撑该 fact 的断言——视为「无任何有效锚」，
# 全部变体不进本批候选（bank 只读、原样保留，待补可读教材/规范原文锚后再入批）。
# 生成器无法语义判定真题锚是否支撑断言，故由对抗审查裁决在此登记。
#   * s05-fact-below-50kw-measures：仅挂 {2018,第17题}，该题只证「50kW 及以上
#     应编制用电组织设计」，不证「50kW 以下编制措施即可」；全库教材/讲义分片
#     亦未检出对应原文。
_S05_EXCLUDED_FACTS: frozenset[str] = frozenset({"s05-fact-below-50kw-measures"})


# 命名先例裁决 note（2026-07-16 终轮主控终裁）：Codex 建议拆 min-total-float
# 独立 fact，主控终裁沿用 MCQ 已签 fact_id 不改名，仅在候选文件显式声明其复合
# 事实性质，并把 005/006 的名实异议逐条记录在案（条目保留）。
_N01_FACT_ADJUDICATION_NOTES: dict[str, str] = {
    "n01-fact-critical-work-zero-float": (
        "本 fact 为已签复合事实（判据『总时差最小』/条件取值 TF=0/延误后果），"
        "命名沿用 MCQ 签发先例；Codex 对 zero-float 命名的名实异议记录在案，"
        "主控终裁保留命名与条目。"
    ),
}
_N01_ITEM_ADJUDICATION_NOTES: dict[str, str] = {
    "N01-A-line-005": (
        "Codex 异议：本条验证「关键工作=总时差最小」判据面，挂 zero-float fact "
        "存在「最小 vs 0」名实张力；主控终裁沿用 MCQ 签发先例保留条目。"
    ),
    "N01-A-line-006": (
        "Codex 异议：本条验证「关键工作=总时差最小」判据面，挂 zero-float fact "
        "存在「最小 vs 0」名实张力；主控终裁沿用 MCQ 签发先例保留条目。"
    ),
}


# 每个 pack 一张表；没有表的 pack 明确拒绝（不产低质量模板）。
_PACK_TABLES: dict[str, tuple[dict[tuple[str, str], str], dict[str, Any]]] = {
    "S05": (_S05_FACTS, _S05_DRAFTS),
    "N01": (_N01_FACTS, _N01_DRAFTS),
}

# pack → (variant_id → fact_id) 改挂表；pack → (fact_id → 元信息) 新 fact 表；
# pack → (fact_id → 摘要 statement 覆盖) 表；pack → 无锚剔除集；裁决 note 表。
_PACK_FACT_OVERRIDES: dict[str, dict[str, str]] = {"N01": _N01_FACT_OVERRIDES}
_PACK_EXTRA_FACTS: dict[str, dict[str, tuple[str, str]]] = {"N01": _N01_EXTRA_FACTS}
_PACK_FACT_STATEMENT_OVERRIDES: dict[str, dict[str, str]] = {
    "N01": _N01_FACT_STATEMENT_OVERRIDES
}
_PACK_EXCLUDED_FACTS: dict[str, frozenset[str]] = {"S05": _S05_EXCLUDED_FACTS}
_PACK_FACT_ADJUDICATION_NOTES: dict[str, dict[str, str]] = {
    "N01": _N01_FACT_ADJUDICATION_NOTES
}
_PACK_ITEM_ADJUDICATION_NOTES: dict[str, dict[str, str]] = {
    "N01": _N01_ITEM_ADJUDICATION_NOTES
}


# ----------------------------------------------------------------- 佐证 join


def _cjk_bigrams(text: str) -> set[str]:
    chars = _CJK_RE.findall(text)
    return {a + b for a, b in zip(chars, chars[1:])}


# quote↔fact 主题一致性阈值（E5 类错锚防线）：实测正确 join 的重叠 ≥0.545，
# 错锚（色标 fact 引三级配电 quote）= 0.0，0.30 干净分界。
_QUOTE_MATCH_THRESHOLD = 0.30


def _quote_supports(correct_statement: str, quote: str) -> bool:
    """join 到的教材 quote 是否与 fact 主题一致（CJK bigram 重叠）。"""
    bigrams = _cjk_bigrams(correct_statement)
    if not bigrams or not quote:
        return False
    overlap = len(bigrams & _cjk_bigrams(quote)) / len(bigrams)
    return overlap >= _QUOTE_MATCH_THRESHOLD


def _textbook_quotes(base_dir: Path, pack_id: str) -> dict[str, dict[str, Any]]:
    """同 pack 签发考点卡 quote 索引（point_id → 卡）；缺失/未签发如实空。"""
    path = base_dir / f"_{pack_id}_concept_card_bank.v0.json"
    try:
        bank = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(bank, dict) or bank.get("status") != "signed":
        return {}
    index: dict[str, dict[str, Any]] = {}
    for card in bank.get("cards") or []:
        if isinstance(card, dict) and card.get("point_id"):
            index[str(card["point_id"])] = {
                "quote": str(card.get("quote") or ""),
                "front": str(card.get("front") or ""),
                "page_num": (card.get("source_ref") or {}).get("page_num"),
            }
    return index


def _compiled_mcq_texts(pack_id: str) -> list[tuple[str, str]]:
    path = COMPILED_DIR / f"{pack_id.lower()}.practice.authority.json"
    try:
        authority = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows: list[tuple[str, str]] = []
    for item in authority.get("items") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("stem") or "") + str(item.get("model_answer") or "")
        for option in item.get("options") or []:
            if isinstance(option, dict) and option.get("is_correct"):
                text += str(option.get("text") or "")
        rows.append((str(item.get("variant_id") or ""), text))
    return rows


def _mcq_candidates(
    correct_statement: str, mcq_texts: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    bigrams = _cjk_bigrams(correct_statement)
    if not bigrams:
        return []
    scored = []
    for variant_id, text in mcq_texts:
        score = len(bigrams & _cjk_bigrams(text)) / len(bigrams)
        if score >= _MCQ_MATCH_THRESHOLD:
            scored.append({"variant_id": variant_id, "match_score": round(score, 3)})
    scored.sort(key=lambda row: (-row["match_score"], row["variant_id"]))
    return scored[:_MCQ_TOP_K]


# ----------------------------------------------------------------- 生成主体


def _kc_anchor(anchor: str) -> str:
    head = str(anchor or "").split(" + ")[0].strip()
    return head if head.startswith("kc:") else ""


def build_candidates(pack_id: str, base_dir: Path) -> dict[str, Any]:
    if pack_id not in _PACK_TABLES:
        raise SystemExit(
            f"prefill: pack {pack_id} 还没有 fact/初稿人工映射表"
            "（本工具拒绝无表低质量模板输出；先在 _PACK_TABLES 补表）"
        )
    fact_table, draft_table = _PACK_TABLES[pack_id]
    fact_overrides = _PACK_FACT_OVERRIDES.get(pack_id, {})
    extra_facts = _PACK_EXTRA_FACTS.get(pack_id, {})
    statement_overrides = _PACK_FACT_STATEMENT_OVERRIDES.get(pack_id, {})
    excluded_facts = _PACK_EXCLUDED_FACTS.get(pack_id, frozenset())
    fact_notes = _PACK_FACT_ADJUDICATION_NOTES.get(pack_id, {})
    item_notes = _PACK_ITEM_ADJUDICATION_NOTES.get(pack_id, {})
    bank_path = base_dir / f"_{pack_id}_variant_bank.v0.json"
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    variants = [v for v in bank.get("variants") or [] if isinstance(v, dict)]
    quotes = _textbook_quotes(base_dir, pack_id)
    mcq_texts = _compiled_mcq_texts(pack_id)

    # fact 聚类（(rule_group, correct_statement) 表 + 逐变体改挂）+ fact 内
    # 按 variant_id 排序交替分配 probe_role（双池非空）。
    by_fact: dict[str, list[dict[str, Any]]] = {}
    fact_of: dict[str, str] = {}
    for v in variants:
        key = (str(v.get("rule_group") or ""), str(v.get("correct_statement") or ""))
        if key not in fact_table:
            raise SystemExit(f"prefill: {pack_id} fact 表缺聚类 {key}")
        fact_id = fact_overrides.get(str(v["variant_id"]), fact_table[key])
        # 无有效锚 fact → 不产候选：跳过其全部变体（不进 fact_of/by_fact/items）。
        if fact_id in excluded_facts:
            continue
        fact_of[str(v["variant_id"])] = fact_id
        by_fact.setdefault(fact_id, []).append(v)
    role_of: dict[str, str] = {}
    for rows in by_fact.values():
        for index, v in enumerate(sorted(rows, key=lambda r: str(r["variant_id"]))):
            role_of[str(v["variant_id"])] = VARIANT_PROBE_ROLES[
                index % len(VARIANT_PROBE_ROLES)
            ]

    def _quote_of(kc: str) -> str:
        card = quotes.get(kc.removeprefix("kc:")) or quotes.get(kc) or {}
        return str(card.get("quote") or "")

    items: list[dict[str, Any]] = []
    for v in variants:
        variant_id = str(v["variant_id"])
        if variant_id not in fact_of:  # 无有效锚 fact 的变体已被剔除
            continue
        rule_group = str(v.get("rule_group") or "")
        temptation, loss_reason = draft_table[rule_group](v)
        content_sha = variant_content_sha256(
            v, temptation=temptation, loss_reason=loss_reason
        )
        skeleton_id = (
            f"{pack_id.lower()}-vskel-{rule_group.lower()}-"
            f"{'ok' if v.get('expected_ok') else 'bad'}"
        )
        # source_anchor：kc 头能被同 pack 签发卡 quote 复核且主题一致才截取；
        # quote 主题不一致（E5 类错锚）→ 从 composite 中**剥掉错锚 kc 头**、
        # 只保留其余已裁决证据（如真题 anchor）——绝不把无关教材点声明为
        # 本 fact 佐证，也绝不截掉真题部分（对抗审查二轮 E5 余项）。
        anchor = str(v.get("anchor") or "")
        kc = _kc_anchor(anchor)
        kc_quote = _quote_of(kc) if kc else ""
        source_anchor = kc or anchor
        if kc and kc_quote and not _quote_supports(
            str(v.get("correct_statement") or ""), kc_quote
        ):
            rest = [
                part.strip()
                for part in anchor.split(" + ")
                if part.strip() and part.strip() != kc
            ]
            source_anchor = " + ".join(rest) if rest else anchor
        decision: dict[str, Any] = {
            "schema": VARIANT_DECISION_SCHEMA,
            "fact_id": fact_of[variant_id],
            "skeleton_id": skeleton_id,
            "probe_role": role_of[variant_id],
            "temptation": temptation,
            "loss_reason": loss_reason,
            "source_anchor": source_anchor,
            "source_sha256": str(bank.get("source_pack_sha256") or ""),
            "content_sha256": content_sha,
        }
        decision["decision_identity_sha256"] = decision_identity_sha256(decision)
        decision["review"] = {
            "status": "pending",
            "verdict": "pending",
            "reviewed_content_sha256": content_sha,
            "reviewed_decision_sha256": decision["decision_identity_sha256"],
            "signatures": [],
            "checks": {
                "source_verified": False,
                "answer_verified": False,
                "diagnosis_verified": False,
                "longest_option_checked": False,
                "template_leakage_checked": False,
            },
        }
        decision["review"]["signature_envelope_sha256"] = (
            review_signature_envelope_sha256(decision)
        )
        item: dict[str, Any] = {
            "variant_id": variant_id,
            "rule_group": rule_group,
            "surface": v.get("surface"),
            "expected_ok": v.get("expected_ok"),
            "correct_statement": v.get("correct_statement"),
            "anchor": v.get("anchor"),
            "extension": bool(v.get("extension")),
            "decision_candidate": decision,
        }
        if variant_id in item_notes:  # 逐条裁决 note（如 005/006 名实异议保留）
            item["adjudicated_note"] = item_notes[variant_id]
        items.append(item)

    fact_meta: dict[str, tuple[str, str]] = {
        fact_id: key for key, fact_id in fact_table.items()
    }
    fact_meta.update(extra_facts)
    facts: list[dict[str, Any]] = []
    for fact_id in sorted(fact_meta):
        if fact_id in excluded_facts:  # 无有效锚 fact 不进本批候选的 facts[]
            continue
        rule_group, correct_statement = fact_meta[fact_id]
        rows = by_fact.get(fact_id) or []
        # facts[] 元数据必须与实际挂载一致（对抗审查二轮新病 1）：
        # rule_group 从实际挂载的变体派生（跨组改挂后如实标多组）；
        # statement 按覆盖表呈现拆分后的摘要，不复读已拆走的子句。
        if rows:
            rule_group = "/".join(
                sorted({str(row.get("rule_group") or "") for row in rows})
            )
        correct_statement = statement_overrides.get(fact_id, correct_statement)
        kc = ""
        for v in rows:
            kc = _kc_anchor(str(v.get("anchor") or ""))
            if kc:
                break
        card = quotes.get(kc.removeprefix("kc:")) or quotes.get(kc) or {}
        quote = str(card.get("quote") or "")
        page_num = card.get("page_num")
        if quote and not _quote_supports(correct_statement, quote):
            # E5 类错锚：kc 头 join 到的教材点与本 fact 主题不一致——
            # 如实留空（join 不中），不把无关教材原文当本 fact 证据。
            kc, quote, page_num = "", "", None
        fact_entry: dict[str, Any] = {
            "fact_id": fact_id,
            "rule_group": rule_group,
            "correct_statement": correct_statement,
            "variant_count": len(rows),
            "core_variant_count": sum(1 for v in rows if not v.get("extension")),
            "kc_anchor": kc,
            "textbook_quote": quote,
            "textbook_page": page_num,
            "compiled_mcq_candidates": _mcq_candidates(correct_statement, mcq_texts),
        }
        if fact_id in fact_notes:  # 命名先例/复合事实性质的显式声明
            fact_entry["adjudicated_note"] = fact_notes[fact_id]
        facts.append(fact_entry)

    return {
        "schema": CANDIDATES_SCHEMA,
        "machine_candidates_only": True,
        "note": (
            "机器候选，绝不签名：fact/skeleton/probe_role 提案 + temptation/"
            "loss_reason 初稿，等待决策卡人签 + 异源对抗后经转写 bake 进 bank；"
            "review 恒 pending、零签名。"
        ),
        "pack_id": pack_id,
        "bank_status": bank.get("status"),
        "generated_from_bank_sha256": bank.get("source_pack_sha256"),
        "candidate_count": len(items),
        "facts": facts,
        "items": items,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packs", nargs="+", help="pack ids，如 S05")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for pack in args.packs:
        pack_id = pack.strip().upper()
        payload = build_candidates(pack_id, args.base_dir)
        out = args.out_dir / f"{pack_id.lower()}.variant.decision.candidates.json"
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        ready = sum(1 for f in payload["facts"] if f["core_variant_count"] >= 2)
        print(
            f"prefill: {pack_id} -> {out} "
            f"(items={payload['candidate_count']}, facts={len(payload['facts'])}, "
            f"facts_with_2plus_core={ready})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
