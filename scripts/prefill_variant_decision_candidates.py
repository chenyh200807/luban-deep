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
- 佐证：同 pack 签发考点卡的教材原文（point_id 精确 join，join 不中如实留空）
  与 compiled MCQ 疑似同 fact 题号（CJK bigram 重叠，候选性质）。

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
            f"{label}操作顺序应为{correct}，本题顺序正确，把对判错同样丢分；"
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
        f"{label}操作顺序应为{correct}；本题给的是「{order}」，顺序颠倒会让"
        "下级箱在失去上级保护的状态下操作，答题要点是写明正确顺序。",
    )


def _s05_c_voltage(v: dict[str, Any]) -> tuple[str, str]:
    place = str(v["params"].get("place") or "")
    surface_v = _num(v["params"].get("surface_v"))
    limit_v = _num(v["params"].get("limit_v"))
    if v["expected_ok"]:
        return (
            f"36V/24V/12V 三档限值容易混记，见到{place}用 {surface_v}V 会拿不准。",
            f"{place}照明电压限值为不大于 {limit_v}V，{surface_v}V 未超限，属于"
            "妥当做法；记法：环境越危险，电压档位越低。",
        )
    return (
        f"只记得「特殊场所要用安全特低电压」，容易忽略{place}的具体限值档位。",
        f"{place}照明电压不得大于 {limit_v}V，{surface_v}V 已超限即违规；"
        f"案例题这里通常单独设采分点，要写明「不大于 {limit_v}V」。",
    )


def _s05_d_one_switch(v: dict[str, Any]) -> tuple[str, str]:
    if v["params"].get("plug_socket_inlet"):
        return (
            "插头插座平时最常见，放在配电箱进线端容易觉得「方便检修」。",
            "配电箱、开关箱电源进线端严禁采用插头插座做活动连接——活动连接"
            "易松动打火，进线端必须固定连接。",
        )
    machine = str(v["params"].get("machine") or "用电设备")
    share = int(v["params"].get("share_count") or 1)
    if v["expected_ok"]:
        return (
            "「一机一箱」太熟了，反而会怀疑单独设箱是不是多余。",
            f"每台用电设备必须有各自专用的开关箱，{machine}单独设箱正是规范"
            "要求；判断方向错了同样丢分。",
        )
    return (
        f"{share} 台同类{machine}挨得近，共用一个开关箱看起来省料又省事。",
        "严禁 2 台及以上用电设备（含插座）共用一个开关箱——「一机一闸一漏"
        "一箱」，共用箱在故障时无法准确分断对应设备。",
    )


def _s05_e_bury(v: dict[str, Any]) -> tuple[str, str]:
    depth = _num(v["params"].get("depth_m"))
    threshold = _num(v["params"].get("threshold_m"))
    if v["expected_ok"]:
        return (
            f"{threshold}m 这个数字容易与其他埋深/间距数字混记，"
            f"见到 {depth}m 会犹豫。",
            f"电缆直接埋地敷设深度不应小于 {threshold}m，{depth}m 已满足要求，"
            "属于妥当做法；把对判错同样丢分。",
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
        f"PE 线={pe_color}，色标接错会导致检修时误判带电导体。",
    )


_S05_F_MGMT: dict[str, tuple[str, str]] = {
    "S05-F-mgmt-064": (
        "现场赶工期时「先干着、证再补」的情形常见，容易觉得情有可原。",
        "电工必须经职业资格考试合格、持证后方可上岗作业；未取得职业资格证"
        "即上岗接线属于违规，答题要写明「持证上岗」。",
    ),
    "S05-F-mgmt-065": (
        "安全员天天盯现场安全，由他拆除用电设备听起来顺理成章。",
        "用电设备的安装、维修、拆除应由电工完成，安全员不具备电工作业资格；"
        "答题要点是「应由（持证）电工完成」。",
    ),
    "S05-F-mgmt-066": (
        "现场已经编了安全用电措施，容易误以为够用，忽略 50kW 这条容量线。",
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
        "进入装饰装修阶段用电部位与负荷发生变化，应补充编制单项施工用电"
        "方案；未补充编制即违规。",
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
        "支线过长会降低保护动作的可靠性。",
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

# 每个 pack 一张表；没有表的 pack 明确拒绝（不产低质量模板）。
_PACK_TABLES: dict[str, tuple[dict[tuple[str, str], str], dict[str, Any]]] = {
    "S05": (_S05_FACTS, _S05_DRAFTS),
}


# ----------------------------------------------------------------- 佐证 join


def _cjk_bigrams(text: str) -> set[str]:
    chars = _CJK_RE.findall(text)
    return {a + b for a, b in zip(chars, chars[1:])}


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
    bank_path = base_dir / f"_{pack_id}_variant_bank.v0.json"
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    variants = [v for v in bank.get("variants") or [] if isinstance(v, dict)]
    quotes = _textbook_quotes(base_dir, pack_id)
    mcq_texts = _compiled_mcq_texts(pack_id)

    # fact 聚类 + fact 内按 variant_id 排序交替分配 probe_role（双池非空）。
    by_fact: dict[str, list[dict[str, Any]]] = {}
    fact_of: dict[str, str] = {}
    for v in variants:
        key = (str(v.get("rule_group") or ""), str(v.get("correct_statement") or ""))
        if key not in fact_table:
            raise SystemExit(f"prefill: {pack_id} fact 表缺聚类 {key}")
        fact_id = fact_table[key]
        fact_of[str(v["variant_id"])] = fact_id
        by_fact.setdefault(fact_id, []).append(v)
    role_of: dict[str, str] = {}
    for rows in by_fact.values():
        for index, v in enumerate(sorted(rows, key=lambda r: str(r["variant_id"]))):
            role_of[str(v["variant_id"])] = VARIANT_PROBE_ROLES[
                index % len(VARIANT_PROBE_ROLES)
            ]

    items: list[dict[str, Any]] = []
    for v in variants:
        variant_id = str(v["variant_id"])
        rule_group = str(v.get("rule_group") or "")
        temptation, loss_reason = draft_table[rule_group](v)
        content_sha = variant_content_sha256(
            v, temptation=temptation, loss_reason=loss_reason
        )
        skeleton_id = (
            f"{pack_id.lower()}-vskel-{rule_group.lower()}-"
            f"{'ok' if v.get('expected_ok') else 'bad'}"
        )
        items.append(
            {
                "variant_id": variant_id,
                "rule_group": rule_group,
                "surface": v.get("surface"),
                "expected_ok": v.get("expected_ok"),
                "correct_statement": v.get("correct_statement"),
                "anchor": v.get("anchor"),
                "extension": bool(v.get("extension")),
                "decision_candidate": {
                    "schema": VARIANT_DECISION_SCHEMA,
                    "fact_id": fact_of[variant_id],
                    "skeleton_id": skeleton_id,
                    "probe_role": role_of[variant_id],
                    "temptation": temptation,
                    "loss_reason": loss_reason,
                    "source_anchor": _kc_anchor(str(v.get("anchor") or ""))
                    or str(v.get("anchor") or ""),
                    "source_sha256": str(bank.get("source_pack_sha256") or ""),
                    "content_sha256": content_sha,
                    "review": {
                        "status": "pending",
                        "verdict": "pending",
                        "reviewed_content_sha256": content_sha,
                        "signatures": [],
                        "checks": {
                            "source_verified": False,
                            "answer_verified": False,
                            "diagnosis_verified": False,
                            "longest_option_checked": False,
                            "template_leakage_checked": False,
                        },
                    },
                },
            }
        )

    facts: list[dict[str, Any]] = []
    for (rule_group, correct_statement), fact_id in sorted(
        fact_table.items(), key=lambda kv: kv[1]
    ):
        rows = by_fact.get(fact_id) or []
        kc = ""
        for v in rows:
            kc = _kc_anchor(str(v.get("anchor") or ""))
            if kc:
                break
        card = quotes.get(kc.removeprefix("kc:")) or quotes.get(kc) or {}
        facts.append(
            {
                "fact_id": fact_id,
                "rule_group": rule_group,
                "correct_statement": correct_statement,
                "variant_count": len(rows),
                "core_variant_count": sum(
                    1 for v in rows if not v.get("extension")
                ),
                "kc_anchor": kc,
                "textbook_quote": card.get("quote", ""),
                "textbook_page": card.get("page_num"),
                "compiled_mcq_candidates": _mcq_candidates(
                    correct_statement, mcq_texts
                ),
            }
        )

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
