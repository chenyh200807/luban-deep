#!/usr/bin/env python3
"""图解微课卡 schema spine 轻量校验器（v0 收口）。

自动发现本目录下所有 schema_version==luban_diagram_microlesson.v1 的卡（不靠手维护清单，
防"新卡漏进校验门"的 dormant authority），校验是否共用同一条 schema spine、body 是否互斥、
authority 是否诚实、学生端安全字段是否分离。**不做知识判断、不判分、不改 renderer、不引外部依赖、不做 HTML 扫描。**

约束（与 SCHEMA.md / v0 principles 一致）：
- 不新增 schema_version；candidate/prototype 不得 official_score_allowed=true；
- renderer/compute_cpm 是渲染/校验，不是评分 authority（本脚本不涉及，只查 JSON 结构）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_diagram_microlesson.v1"
HERE = Path(__file__).resolve().parent

# 不再手维护清单：main() 按 schema_version 内容发现所有卡（见 discover_cards）。

# 旧卡无 template_type 时, 从 scenario.diagram_type 推断
DIAGRAM_TYPE_TO_TEMPLATE = {
    "roof_section_step_reveal": "process_step_reveal",
    "section_layer_reveal": "layer_section_reveal",
}
CANDIDATE_STATUSES = {"candidate", "candidate_teaching_prototype", "prototype", "draft"}


def get(card: dict[str, Any], dotted: str) -> Any:
    cur: Any = card
    for k in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def infer_template_type(card: dict[str, Any]) -> tuple[str | None, bool]:
    tt = card.get("template_type")
    if tt:
        return tt, False
    dt = get(card, "scenario.diagram_type")
    if dt in DIAGRAM_TYPE_TO_TEMPLATE:
        return DIAGRAM_TYPE_TO_TEMPLATE[dt], True
    return None, True


def detect_body(card: dict[str, Any]) -> str:
    has_steps = bool(card.get("steps"))
    has_network = bool(get(card, "question_data.activities"))
    has_diag = bool(card.get("diagnosis"))
    has_contrast = bool(card.get("contrast_items"))
    has_decision = bool(get(card, "decision.judgment_points"))
    bodies = [
        b
        for b, present in (
            ("steps", has_steps),
            ("network", has_network),
            ("diagnosis", has_diag),
            ("contrast", has_contrast),
            ("decision", has_decision),
        )
        if present
    ]
    if len(bodies) != 1:
        return "AMBIGUOUS:" + ("+".join(bodies) if bodies else "none")
    return bodies[0]


def authority_status(card: dict[str, Any]) -> str:
    status = get(card, "authority.status") or get(card, "provenance.kind")
    if status:
        return status
    # 旧卡: 看是否有已签发 artifact + 候选/教学 step 混合
    if get(card, "authority.judging_artifact_id"):
        kinds = {get(b, "exam_binding.kind") for b in card.get("steps") or []}
        kinds |= {sp.get("kind") for sp in card.get("scoring_points") or []}
        if "signed_candidate" in kinds and ("teaching_step" in kinds or None in kinds):
            return "candidate_or_signed_mixed"
        return "signed_candidate"
    return "unspecified"


def has_student_boundary(card: dict[str, Any]) -> bool:
    return bool(str(get(card, "authority.student_boundary") or "").strip())


def official_score_claimed(card: dict[str, Any]) -> bool:
    """递归找任何 official_score_allowed=true。"""
    def walk(x: Any) -> bool:
        if isinstance(x, dict):
            if x.get("official_score_allowed") is True:
                return True
            return any(walk(v) for v in x.values())
        if isinstance(x, list):
            return any(walk(v) for v in x)
        return False
    return walk(card)


def check_network(card: dict[str, Any], errs: list[str]) -> None:
    for f in ("question_data.activities", "question_data.dependencies",
              "question_data.expected.critical_path", "question_data.expected.project_duration",
              "question_data.expected.float"):
        if get(card, f) in (None, [], {}):
            errs.append(f"network 缺字段: {f}")
    if authority_status(card) in CANDIDATE_STATUSES and official_score_claimed(card):
        errs.append("candidate/prototype 不得 official_score_allowed=true")


def check_diagnosis(card: dict[str, Any], errs: list[str]) -> None:
    for f in ("question", "model_answer_skeleton", "student_sample", "diagnosis"):
        if not card.get(f):
            errs.append(f"diagnosis 草案缺字段: {f}")
    sp_ids = {sp.get("id") for sp in card.get("scoring_points") or []}
    for i, d in enumerate(card.get("diagnosis") or []):
        st = d.get("status")
        if st not in ("hit", "partial", "miss"):
            errs.append(f"diagnosis[{i}].status 非法: {st!r} (只允许 hit/partial/miss)")
        spid = d.get("scoring_point_id")
        if spid not in sp_ids:
            errs.append(f"diagnosis[{i}].scoring_point_id {spid!r} 不在 scoring_points")
    status = authority_status(card)
    if status not in CANDIDATE_STATUSES:
        errs.append(f"D01 必须标 candidate/draft authority, 实际: {status!r}")
    if official_score_claimed(card):
        errs.append("draft 不得 official_score_allowed=true / production_ready")


def check_contrast(card: dict[str, Any], errs: list[str]) -> None:
    items = card.get("contrast_items") or []
    if not items:
        errs.append("contrast 草案缺字段: contrast_items")
    sp_ids = {sp.get("id") for sp in card.get("scoring_points") or []}
    for i, it in enumerate(items):
        if not get(it, "wrong.text"):
            errs.append(f"contrast_items[{i}].wrong.text 缺失")
        if not (get(it, "right.text") or get(it, "right.scoring_expression")):
            errs.append(f"contrast_items[{i}].right 缺 text/scoring_expression")
        binding = it.get("scoring_point_binding")
        if binding is not None and binding not in sp_ids:
            errs.append(
                f"contrast_items[{i}].scoring_point_binding {binding!r} 不在 scoring_points (reference 未闭合)"
            )
    # 采分点候选必须诚实标 kind: reference-not-duplicate 的前提 + 防 candidate 冒充签发
    for sp in card.get("scoring_points") or []:
        if not sp.get("kind"):
            errs.append(f"scoring_points[{sp.get('id')!r}] 缺 kind (candidate 不冒充签发)")
    status = authority_status(card)
    if status not in CANDIDATE_STATUSES:
        errs.append(f"contrast 草案必须标 candidate/draft authority, 实际: {status!r}")
    if official_score_claimed(card):
        errs.append("draft 不得 official_score_allowed=true / production_ready")


def check_decision(card: dict[str, Any], errs: list[str]) -> None:
    d = card.get("decision") or {}
    points = d.get("judgment_points") or []
    if not points:
        errs.append("decision 缺字段: judgment_points")
    sp_ids = {sp.get("id") for sp in card.get("scoring_points") or []}
    pids = {p.get("id") for p in points}
    oids = {o.get("id") for o in (d.get("outcomes") or [])}
    for p in points:
        if p.get("verdict") not in ("met", "unmet", "na"):
            errs.append(f"judgment_points[{p.get('id')!r}].verdict 非法: {p.get('verdict')!r}")
        for nxt in (p.get("next_on_met"), p.get("next_on_unmet")):
            if nxt is None:
                continue
            if str(nxt).startswith("outcome:"):
                if str(nxt).split(":", 1)[1] not in oids:
                    errs.append(f"{p.get('id')!r} 走向指向未知 outcome: {nxt!r}")
            elif nxt not in pids:
                errs.append(f"{p.get('id')!r} 走向指向未知判断点: {nxt!r}")
        b = p.get("scoring_point_binding")
        if b is not None and b not in sp_ids:
            errs.append(f"{p.get('id')!r}.scoring_point_binding {b!r} 不在 scoring_points (reference 未闭合)")
    if d.get("reached_outcome") not in oids:
        errs.append(f"reached_outcome {d.get('reached_outcome')!r} 不在 outcomes")
    for sp in card.get("scoring_points") or []:
        if not sp.get("kind"):
            errs.append(f"scoring_points[{sp.get('id')!r}] 缺 kind (candidate 不冒充签发)")
    status = authority_status(card)
    if status not in CANDIDATE_STATUSES:
        errs.append(f"decision 草案必须标 candidate/draft authority, 实际: {status!r}")
    if official_score_claimed(card):
        errs.append("draft 不得 official_score_allowed=true / production_ready")


def check_student_safety(card: dict[str, Any], errs: list[str]) -> str:
    if not has_student_boundary(card):
        errs.append("缺 authority.student_boundary")
    rc = get(card, "rendering_contract.student_safe_fields")
    if rc is None:
        return "boundary_only"
    if not isinstance(rc, list) or not rc:
        errs.append("rendering_contract.student_safe_fields 必须是非空白名单")
        return "contract_invalid"
    # 至少包含面向展示的字段(title 或讲解/诊断文案)
    joined = " ".join(rc)
    if "title" not in joined and "student_comment" not in joined and "display_label" not in joined and "stem" not in joined:
        errs.append("student_safe_fields 未包含任何面向展示字段")
    # 不得把内部 id 放进白名单
    for bad in ("scoring_points[].id", "scoring_points[].source_ref", "common_errors[].error_code"):
        if bad in rc:
            errs.append(f"内部字段 {bad} 不应在 student_safe_fields")
    return "contract+boundary"


def validate_one(path: Path) -> bool:
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"{path.name}: FAIL 无法解析 JSON: {e}")
        return False
    errs: list[str] = []

    if card.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version 必须是 {SCHEMA_VERSION}, 实际 {card.get('schema_version')!r}")

    tt, inferred = infer_template_type(card)
    tt_label = (tt or "UNKNOWN") + (" (inferred)" if inferred else "")

    body = detect_body(card)
    if body.startswith("AMBIGUOUS"):
        errs.append(f"body 不互斥: {body} (steps/network/diagnosis/contrast/decision 只能其一为主 body)")

    status = authority_status(card)
    safe = check_student_safety(card, errs)

    # template 专属
    if tt == "network_plan_keypath":
        check_network(card, errs)
    elif tt in ("answer_point_diagnosis", "answer_point_diagnosis_draft"):
        check_diagnosis(card, errs)
        if tt == "answer_point_diagnosis":
            tt_label += "  [建议标 answer_point_diagnosis_draft]"
    elif tt in ("contrast_pair_reveal", "contrast_pair_reveal_draft"):
        check_contrast(card, errs)
        if body != "contrast":
            errs.append(f"{tt} 的 body 应为 contrast, 实际 {body}")
        if tt == "contrast_pair_reveal":
            tt_label += "  [建议标 contrast_pair_reveal_draft]"
    elif tt in ("decision_branch_reveal", "decision_branch_reveal_draft"):
        check_decision(card, errs)
        if body != "decision":
            errs.append(f"{tt} 的 body 应为 decision, 实际 {body}")
        if tt == "decision_branch_reveal":
            tt_label += "  [建议标 decision_branch_reveal_draft]"
    elif tt in ("process_step_reveal", "layer_section_reveal"):
        if body != "steps":
            errs.append(f"{tt} 的 body 应为 steps, 实际 {body}")
    elif tt is None:
        errs.append("无法确定 template_type (缺 template_type 且 scenario.diagram_type 不可推断)")

    ok = not errs
    print(
        f"{path.name}: {'OK' if ok else 'FAIL'} "
        f"template_type={tt_label} body={body} authority={status} student_safe={safe}"
    )
    for e in errs:
        print(f"    - {e}")
    return ok


def discover_cards() -> list[Path]:
    """按内容发现卡: 本目录下所有顶层 schema_version==SCHEMA_VERSION 的 *.json。

    不靠手维护清单 —— 防"新卡漏进校验门"的 dormant authority。非卡 JSON 自动跳过。
    """
    cards: list[Path] = []
    for p in sorted(HERE.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue  # 非法 JSON 不在本门职责内(此门只校验声明为本 schema 的卡)
        if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION:
            cards.append(p)
    return cards


def main() -> int:
    print(f"schema spine 校验 (schema_version={SCHEMA_VERSION})")
    cards = discover_cards()
    if not cards:
        print("未发现任何 luban_diagram_microlesson.v1 卡")
        return 1
    results = [validate_one(p) for p in cards]
    n_ok = sum(results)
    print(f"\n汇总: {n_ok}/{len(results)} OK")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
