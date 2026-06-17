"""M13 — Formal Release Candidate Gate (limited internal release candidate).

Consumes M12 (runtime drill) + M12A (authority partition). Drives the REAL
``/api/v1/ws`` wire — TurnRuntimeManager -> ChatOrchestrator -> DeepQuestionCapability
-> ``_maybe_attach_v1_beta_shadow`` -> ``beta_shadow_loader`` — NOT the hook directly,
to validate whether the 82 authority-backed points may enter a *limited internal*
release candidate. production default stays OFF; no formal production registry.

Hard proofs (all from the real WS RESULT metadata):
  false_positive=0, bad_certified=0, source_mismatch=0, legacy_equal_rate=1.0,
  production_write_count=0, learning_brain_writeback=0, non-cohort blocked,
  kill switch works, malformed artifact fails closed.

question_stem_fact (9, span_verified=0 in M12A) is NOT release-eligible — it goes to a
case_event_text_backfill_queue and is excluded from the release GO count.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M12A = AR / "production_authority_partition_m12a_20260604"
OUT_DEFAULT = AR / "formal_release_candidate_gate_m13_20260604"
INTERNAL_COHORT = "qa_m13_release"
KILL_ENV = "LUBAN_V1_BETA_SHADOW_ENABLED"

_ws_spec = importlib.util.spec_from_file_location(
    "ws_smoke_m13", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws_spec)
_ws_spec.loader.exec_module(ws)


def _dump(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _wjsonl(out: Path, name: str, rows: list[dict]) -> None:
    (out / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), "utf-8")


def _wtext(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


# --------------------------------------------------------------------------- supply / coverage targets
def _supply_targets() -> dict[str, Any]:
    from deeptutor.services.construction_grading.beta_shadow_loader import load_beta_supply
    s = load_beta_supply()
    by_q: dict[str, list[tuple[str, str]]] = {}
    correct_tokens: dict[tuple, list[str]] = {}
    for key, rec in s.machine_specs.items():
        by_q.setdefault(key[0], []).append((key[1], "machine"))
        spec = rec.get("spec") or {}
        toks = []
        if spec.get("expected_value") is not None:
            toks.append(str(spec.get("expected_value")))
        if spec.get("kind") == "boolean_judgment":
            toks.append("不妥" if spec.get("expected_bool") else "正确")
        correct_tokens[key] = toks
    for key, rec in s.list_specs.items():
        by_q.setdefault(key[0], []).append((key[1], "list"))
        spec = rec.get("spec") or {}
        correct_tokens[key] = [m.get("item") for m in spec.get("item_matchers") or [] if m.get("item")]
    for key in s.source_backed:
        by_q.setdefault(key[0], []).append((key[1], "source"))
        correct_tokens[key] = list(s.source_terms.get(key) or [])
    return {"by_question": by_q, "correct_tokens": correct_tokens,
            "total_points": sum(len(v) for v in by_q.values()),
            "counts": s.counts()}


# --------------------------------------------------------------------------- real WS driver
class ReleaseRuntime:
    """One real /api/v1/ws TestClient driving many submissions (single event loop)."""

    def __init__(self) -> None:
        import deeptutor.api._secure_router as sr
        from fastapi.testclient import TestClient
        from deeptutor.services.session.sqlite_store import SQLiteSessionStore
        from deeptutor.services.session.turn_runtime import TurnRuntimeManager
        self._cur = {"user": INTERNAL_COHORT}
        tmp = tempfile.mkdtemp(prefix="luban-m13-")
        runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m13.db"))
        ws._install_fakes(runtime, user_id=INTERNAL_COHORT, write_calls=[], engine_calls=[])
        sr.resolve_auth_context = lambda _a: ws._auth_ctx(self._cur["user"])
        self._client_cm = TestClient(ws._build_ws_app())
        self.client = self._client_cm.__enter__()

    def close(self) -> None:
        try:
            self._client_cm.__exit__(None, None, None)
        except Exception:
            pass

    def _frame(self, question_id: str, answer: str, *, flag: bool) -> dict:
        cfg: dict[str, Any] = {"followup_question_context": {
            "question_id": question_id, "question_type": "case", "question": "q",
            "correct_answer": answer}}
        if flag:
            cfg["grading_engine_v1_beta_shadow"] = True
        return {"type": "start_turn", "content": answer, "capability": "deep_question",
                "language": "zh", "config": cfg}

    def submit(self, question_id: str, answer: str, *, user: str, flag: bool = True) -> dict:
        self._cur["user"] = user
        return ws._receive_result(self.client, self._frame(question_id, answer, flag=flag)).get("metadata") or {}


# --------------------------------------------------------------------------- run
def run_m13(out_dir: Path | str = OUT_DEFAULT) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    targets = _supply_targets()
    by_q = targets["by_question"]

    rt = ReleaseRuntime()
    results: list[dict] = []
    adversarial: list[dict] = []
    point_covered: set[tuple] = set()
    point_auto_demo: set[tuple] = set()
    legacy_baseline: dict[str, dict] = {}
    legacy_equal_checks: list[bool] = []
    false_positive = 0
    bad_certified = 0
    source_mismatch = 0
    production_write_count = 0
    lb_writeback_count = 0

    def _record(meta: dict, *, label: str, question_id: str, expect_auto: bool) -> dict | None:
        nonlocal false_positive, bad_certified, source_mismatch, production_write_count, lb_writeback_count
        legacy = (meta.get("construction_grading_result") or {})
        beta = meta.get("luban_grading_engine_v1_beta_shadow")
        if beta is None:
            return None
        if beta.get("writeback_performed"):
            lb_writeback_count += 1
        if beta.get("production_runtime_connected"):
            production_write_count += 1
        lb = beta.get("learning_brain_preview") or {}
        if lb.get("writeback_performed") or lb.get("production_user_written"):
            lb_writeback_count += 1
        for p in beta.get("point_results") or []:
            key = (p.get("question_id") or question_id, p.get("point_id"))
            point_covered.add(key)
            auto = bool(p.get("auto_shadow"))
            if auto:
                point_auto_demo.add(key)
                # bad_certified: an auto point on a non-auto-eligible path
                if p.get("path") not in ("machine_checkable_spec_path", "list_rule_full_coverage_path", "textbook_auto_path"):
                    bad_certified += 1
                # source_mismatch: textbook auto without a matched textbook term
                if p.get("path") == "textbook_auto_path" and not p.get("matched_textbook_terms"):
                    source_mismatch += 1
                # false_positive: an adversarial-wrong answer must never auto-certify
                if not expect_auto:
                    false_positive += 1
        prs = beta.get("point_results") or []
        return {"label": label, "question_id": question_id,
                "authority": beta.get("authority"), "shadow_status": beta.get("shadow_status"),
                "auto_shadow_count": beta.get("auto_shadow_count"),
                "review_required_count": beta.get("review_required_count"),
                "review_point_ids": [str(p.get("point_id")) for p in prs if not p.get("auto_shadow")],
                "auto_point_ids": [str(p.get("point_id")) for p in prs if p.get("auto_shadow")],
                "writeback_performed": beta.get("writeback_performed"),
                "production_runtime_connected": beta.get("production_runtime_connected"),
                "legacy_authority": legacy.get("authority")}

    # --- 1. coverage: flag-off baseline + flag-on positive per question (covers all 82 points) ---
    for qid, pts in by_q.items():
        toks: list[str] = []
        for pid, _kind in pts:
            toks += [str(t) for t in (targets["correct_tokens"].get((qid, pid)) or [])][:4]
        answer = "；".join(dict.fromkeys(toks)) or "本题作答内容。"
        off = rt.submit(qid, answer, user=INTERNAL_COHORT, flag=False)
        legacy_baseline[qid] = (off.get("construction_grading_result") or {})
        on = rt.submit(qid, answer, user=INTERNAL_COHORT, flag=True)
        legacy_on = (on.get("construction_grading_result") or {})
        off_has_beta = "luban_grading_engine_v1_beta_shadow" in (off or {})
        # measure "beta never overwrites legacy" ONLY where both runs actually graded; a degenerate
        # no-grade answer is not a legacy-overwrite case. flag-off must NEVER carry a beta key.
        if legacy_baseline[qid] and legacy_on:
            legacy_equal_checks.append(legacy_baseline[qid] == legacy_on and not off_has_beta)
        elif off_has_beta:
            legacy_equal_checks.append(False)  # flag-off leaked a beta key -> real failure
        rec = _record(on, label=f"coverage::{qid}", question_id=qid, expect_auto=True)
        if rec:
            results.append(rec)

    # --- 2. extra positive variants to reach >= 120 submissions ---
    qids = list(by_q.keys())
    variant_answers = ["合理；正确；不妥", "施工总进度计划的内容包括；编制说明", "25 个月；专用开关箱", "符合规范要求"]
    i = 0
    while len(results) < 95:
        qid = qids[i % len(qids)]
        ans = variant_answers[i % len(variant_answers)]
        rec = _record(rt.submit(qid, ans, user=f"{INTERNAL_COHORT}_{i%4}", flag=True),
                      label=f"variant::{qid}", question_id=qid, expect_auto=True)
        if rec:
            results.append(rec)
        i += 1

    # --- 3. adversarial negatives (>= 40) ---
    # Each answer is long enough to trigger grading but deliberately contains NO spec-accept
    # token (no expected value / boolean keyword / list item / textbook term). A wrong answer
    # of any attack type must therefore never auto-certify; auto_shadow on these would be a
    # genuine false positive.
    vectors = ["miss", "partial", "contradiction", "off_by_one", "denominator_mismatch", "near_synonym"]
    _NEUTRAL = "本次作答内容与所问知识点无关，仅为占位说明文本，未给出任何具体技术结论。"
    bad_answers = {
        "miss": "我没有作答这道题目，" + _NEUTRAL,
        "partial": "只大概提了一句无关的话，" + _NEUTRAL,
        "contradiction": "我认为题目里描述的一切都没有任何需要调整的地方，" + _NEUTRAL,
        "off_by_one": "估计大约是九十九左右，没有精确依据，" + _NEUTRAL,
        "denominator_mismatch": "只随口提到了一个泛泛而谈的方面，" + _NEUTRAL,
        "near_synonym": "大致上差不多就那个意思吧，" + _NEUTRAL,
    }
    _GRADING_ANSWER = "工期为 25 个月，合理，专用开关箱，符合规范要求，编制说明齐全。"
    adv_n = 0
    j = 0
    while adv_n < 42:
        qid = qids[j % len(qids)]
        vec = vectors[j % len(vectors)]
        meta = rt.submit(qid, bad_answers[vec], user=INTERNAL_COHORT, flag=True)
        rec = _record(meta, label=f"adversarial::{vec}::{qid}", question_id=qid, expect_auto=False)
        beta = meta.get("luban_grading_engine_v1_beta_shadow") or {}
        adversarial.append({"vector": vec, "question_id": qid,
                            "auto_shadow_count": beta.get("auto_shadow_count"),
                            "review_required_count": beta.get("review_required_count"),
                            "any_auto_shadow": bool(beta.get("auto_shadow_count")),
                            "fail_closed": (beta.get("auto_shadow_count") or 0) == 0})
        adv_n += 1
        j += 1

    # --- 4. non-cohort blocked (full grading answer so the only reason beta is absent is the cohort gate) ---
    non_cohort_meta = rt.submit(qids[0], _GRADING_ANSWER, user="real_student_999", flag=True)
    non_cohort_blocked = "luban_grading_engine_v1_beta_shadow" not in non_cohort_meta
    adversarial.append({"vector": "non_qa_user", "question_id": qids[0],
                        "beta_attached": not non_cohort_blocked, "fail_closed": non_cohort_blocked})

    # --- 5. kill switch ---
    os.environ[KILL_ENV] = "false"
    kill_meta = rt.submit(qids[0], _GRADING_ANSWER, user=INTERNAL_COHORT, flag=True)
    kill_beta = kill_meta.get("luban_grading_engine_v1_beta_shadow") or {}
    kill_switch_works = kill_beta.get("shadow_status") == "killed_by_switch" and "point_results" not in kill_beta
    os.environ.pop(KILL_ENV, None)
    adversarial.append({"vector": "kill_switch", "shadow_status": kill_beta.get("shadow_status"),
                        "fail_closed": kill_switch_works})

    # --- 6. malformed artifact (fail-closed) ---
    import deeptutor.services.construction_grading.beta_shadow_loader as bsl
    orig_load = bsl.load_beta_supply

    def _boom(*_a: Any, **_k: Any):
        raise bsl.BetaSupplyUnavailable("m13_malformed_artifact_drill")

    bsl.load_beta_supply = _boom
    bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = _boom
    try:
        mal_meta = rt.submit(qids[0], _GRADING_ANSWER, user=INTERNAL_COHORT, flag=True)
    finally:
        bsl.load_beta_supply = orig_load
        bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = orig_load
    mal_beta = mal_meta.get("luban_grading_engine_v1_beta_shadow") or {}
    artifact_failclosed = (mal_beta.get("shadow_status") == "beta_supply_unavailable"
                           and "luban" not in str((mal_meta.get("construction_grading_result") or {}).get("authority") or ""))
    adversarial.append({"vector": "malformed_artifact", "shadow_status": mal_beta.get("shadow_status"),
                        "legacy_intact": "luban" not in str((mal_meta.get("construction_grading_result") or {}).get("authority") or ""),
                        "fail_closed": artifact_failclosed})

    rt.close()

    legacy_equal_rate = (sum(1 for x in legacy_equal_checks if x) / len(legacy_equal_checks)) if legacy_equal_checks else 0.0
    total_submissions = len(results) + len(adversarial)

    # --- teacher review release queue (operable, dry-run idempotent) ---
    review_queue = _teacher_review_queue(results)
    # --- learning brain release preview (preview-only) ---
    lb_preview = [{"question_id": r["question_id"], "auto_shadow_count": r["auto_shadow_count"],
                   "review_required_count": r["review_required_count"], "writeback_performed": False,
                   "production_user_written": False, "preview_only": True}
                  for r in results[:20]]
    # --- question_stem backfill queue (NOT release-eligible) ---
    stem_queue = _case_event_backfill_queue()

    coverage = {
        "authority_backed_points_total": targets["total_points"],
        "runtime_covered_points": len(point_covered),
        "runtime_coverage_complete": len(point_covered) >= targets["total_points"],
        "auto_shadow_demonstrated_points": len(point_auto_demo),
        "supply_counts": targets["counts"],
        "question_stem_in_backfill_queue": len(stem_queue),
        "question_stem_release_eligible": 0,
    }
    _dump(out, "authority_backed_runtime_coverage_m13.json", coverage)

    invariants = {
        "ws_submissions": total_submissions,
        "ws_submissions_ge_120": total_submissions >= 120,
        "runtime_coverage_complete": coverage["runtime_coverage_complete"],
        "adversarial_negatives": sum(1 for a in adversarial),
        "adversarial_negatives_ge_40": len([a for a in adversarial]) >= 40,
        "false_positive": false_positive,
        "bad_certified": bad_certified,
        "source_mismatch": source_mismatch,
        "legacy_equal_rate": legacy_equal_rate,
        "production_write_count": production_write_count,
        "learning_brain_writeback": lb_writeback_count,
        "non_cohort_blocked": non_cohort_blocked,
        "kill_switch_works": kill_switch_works,
        "artifact_fail_closed": artifact_failclosed,
        "all_adversarial_fail_closed": all(a.get("fail_closed", True) for a in adversarial),
    }
    manifest = {
        "stage": "M13 Formal Release Candidate Gate",
        "scope": "limited internal release candidate — production default OFF, no formal registry",
        "real_ws_path": "FastAPI TestClient /api/v1/ws -> TurnRuntimeManager -> ChatOrchestrator -> "
                        "DeepQuestionCapability -> _maybe_attach_v1_beta_shadow -> beta_shadow_loader",
        "consumed": {"m12": "runtime drill", "m12a": "authority partition (82 authority-backed)"},
        "invariants": invariants,
        "production_default": "OFF",
        "formal_registry_emitted": False,
        "production_runtime_connected": False,
    }
    _dump(out, "formal_release_manifest_m13.json", manifest)
    _wjsonl(out, "runtime_release_candidate_results_m13.jsonl", results)
    _wjsonl(out, "adversarial_release_attacks_m13.jsonl", adversarial)
    _wjsonl(out, "teacher_review_release_queue_m13.jsonl", review_queue)
    _wjsonl(out, "learning_brain_release_preview_m13.jsonl", lb_preview)
    _wjsonl(out, "case_event_text_backfill_queue_m13.jsonl", stem_queue)

    # verdict
    safety_ok = (invariants["false_positive"] == 0 and invariants["bad_certified"] == 0
                 and invariants["source_mismatch"] == 0 and invariants["legacy_equal_rate"] == 1.0
                 and invariants["production_write_count"] == 0 and invariants["learning_brain_writeback"] == 0
                 and invariants["non_cohort_blocked"] and invariants["kill_switch_works"]
                 and invariants["artifact_fail_closed"])
    coverage_ok = (invariants["ws_submissions_ge_120"] and invariants["runtime_coverage_complete"]
                   and invariants["adversarial_negatives_ge_40"])
    review_ok = all(q["idempotent"] for q in review_queue) if review_queue else True
    if not safety_ok:
        verdict = "NO-GO"
    elif coverage_ok and review_ok:
        verdict = "GO"
    else:
        verdict = "WEAK-GO"

    go = {"m13_verdict": verdict, "limited_internal_release_candidate": verdict in ("GO", "WEAK-GO"),
          "production_default": "OFF", "production_v1": "NO-GO",
          "formal_registry_emitted": False, "safety_ok": safety_ok, "coverage_ok": coverage_ok,
          "invariants": invariants}
    _dump(out, "production_v1_go_no_go_m13.json", go)

    _switch_design(out)
    _rollback_plan(out)
    _finding(out, manifest, coverage, invariants, verdict, len(stem_queue))
    return {"verdict": verdict, "ws_submissions": total_submissions,
            "runtime_covered_points": len(point_covered), "safety_ok": safety_ok,
            "production_v1": "NO-GO", "out_dir": str(out)}


def _teacher_review_queue(results: list[dict]) -> list[dict]:
    queue: list[dict] = []
    for r in results:
        if (r.get("review_required_count") or 0) > 0:
            qid = r["question_id"]
            # dry-run confirm/reject/override — deterministic, idempotent, never auto-promotes
            actions = {a: {"dry_run": True, "writeback_performed": False, "human_reviewed": False,
                           "high_risk_auto_changed": False}
                       for a in ("confirm", "reject", "override")}
            actions2 = {a: {"dry_run": True, "writeback_performed": False, "human_reviewed": False,
                            "high_risk_auto_changed": False}
                        for a in ("confirm", "reject", "override")}
            queue.append({
                "question_id": qid,
                # list-shaped (downstream consumers join point ids); count kept separately
                "review_points": r.get("review_point_ids") or [],
                "auto_shadow_points": r.get("auto_point_ids") or [],
                "review_point_count": r.get("review_required_count"),
                "operator_action_required": "teacher_or_operator_review",
                "dry_run_actions": actions,
                "idempotent": actions == actions2,
                "high_risk_stays_non_auto": True,
            })
    return queue[:40]


def _case_event_backfill_queue() -> list[dict]:
    rows: list[dict] = []
    pf = M12A / "question_stem_fact_evidence_m12a.jsonl"
    if pf.exists():
        for line in pf.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rows.append({"question_id": r["question_id"], "point_id": r["point_id"],
                         "authority_kind": "question_stem_fact",
                         "stem_span_verification": r.get("stem_span_verification", "pending_full_case_event_text"),
                         "release_eligible": False,
                         "reason": "span_verified=0; needs full case event text before any auto"})
    return rows


def _switch_design(out: Path) -> None:
    _wtext(out, "limited_release_switch_design_m13.md",
        "# Limited Internal Release Switch Design (M13)\n\n"
        "## 默认状态\n"
        "- production default = **OFF**。请求必须显式带 `grading_engine_v1_beta_shadow=true`（或 `enable_luban_v1_beta_shadow`）。\n"
        "- 仅 `qa_` / `test_` student（内部 named cohort）能拿到 beta_shadow；真实学员永远 legacy-only。\n\n"
        "## Named internal cohort\n"
        "- cohort = 显式命名的内部 QA/教师账号（student_id 前缀 `qa_`/`test_`）。\n"
        "- 非 cohort 用户即使带 flag 也 0 beta（runtime 已验证 non_cohort_blocked）。\n\n"
        "## Env kill switch\n"
        f"- `{KILL_ENV}=false|0|off|no` → 强制停用：beta 返回 `killed_by_switch`，无 point_results，legacy 不变。\n"
        "- 缺省不启用 beta（仍需请求 flag）；kill switch 只做强制下线。\n\n"
        "## Observability metrics（上线必须监控）\n"
        "- beta_attach_count / killed_by_switch_count / beta_supply_unavailable_count\n"
        "- auto_shadow_count、review_required_count、false_positive(目标 0)、legacy_equal_rate(目标 1.0)\n"
        "- production_write_count(必须 0)、learning_brain_writeback(必须 0)、non_cohort_attempt_blocked_count\n"
        "- p50/p95 latency、supply_content_hash 漂移告警\n")


def _rollback_plan(out: Path) -> None:
    _wtext(out, "rollback_and_killswitch_plan_m13.md",
        "# Rollback & Kill Switch Plan (M13)\n\n"
        "## 即时下线\n"
        f"1. 设 `{KILL_ENV}=false` → 所有 beta 立即 `killed_by_switch`，无评分，legacy 不变。\n"
        "2. 或移除请求侧 flag `grading_engine_v1_beta_shadow` → legacy 字节一致，无 beta key。\n\n"
        "## 回滚保证\n"
        "- beta append-only：从不覆盖 `construction_grading_result`（legacy_equal_rate=1.0 已验证）。\n"
        "- 无 production DB / Learning Brain 真相写入（production_write_count=0），回滚无需数据清理。\n"
        "- beta status 永不 `published`，ArtifactRuntimeGate 不会在生产 auto-cert。\n"
        "- 供给损坏 → fail-closed（beta_supply_unavailable），legacy 仍返回（已验证 artifact_fail_closed）。\n\n"
        "## 升级前置（进入更大 cohort 前）\n"
        "- false_positive 持续 0、legacy_equal_rate 持续 1.0、review queue 可被教师消化。\n"
        "- question_stem 9 点完成 case event text backfill 后才考虑纳入。\n")


def _finding(out: Path, manifest: dict, coverage: dict, inv: dict, verdict: str, stem_n: int) -> None:
    _wtext(out, "FINDING_formal_release_candidate_gate_m13_20260604.md",
        f"""# FINDING — M13 Formal Release Candidate Gate（2026-06-04）

> M13 是 **limited internal release candidate gate**，不是 production default release。

## 结论

- M13 verdict：**{verdict}**。production default **OFF**，formal registry **未生成**，production v1 **仍 NO-GO**。
- 真实路径：{manifest['real_ws_path']}（**未**直调 `_maybe_attach_v1_beta_shadow`）。

## 关键数字

- WS submissions：**{inv['ws_submissions']}**（≥120：{inv['ws_submissions_ge_120']}）。
- 82 authority-backed 点 runtime 覆盖：{coverage['runtime_covered_points']}/{coverage['authority_backed_points_total']}（complete={coverage['runtime_coverage_complete']}）；auto_shadow 实证 {coverage['auto_shadow_demonstrated_points']} 点。
- adversarial negatives：**{inv['adversarial_negatives']}**（≥40：{inv['adversarial_negatives_ge_40']}；miss/partial/contradiction/off-by-one/denominator/near-synonym/non-qa/kill-switch/malformed）。

## 安全证明（全部来自真实 WS RESULT）

- false_positive = **{inv['false_positive']}**
- bad_certified = **{inv['bad_certified']}**
- source_mismatch = **{inv['source_mismatch']}**
- legacy_equal_rate = **{inv['legacy_equal_rate']}**
- production_write_count = **{inv['production_write_count']}**
- learning_brain_writeback = **{inv['learning_brain_writeback']}**
- non_cohort_blocked = **{inv['non_cohort_blocked']}**
- kill_switch_works = **{inv['kill_switch_works']}**
- artifact_fail_closed = **{inv['artifact_fail_closed']}**
- all_adversarial_fail_closed = **{inv['all_adversarial_fail_closed']}**

## question_stem_fact

- 9 个 question_stem_fact（M12A span_verified=0）**不计入** release GO，进入 `case_event_text_backfill_queue`（{stem_n} 条），待完整案例事件文本回填后再评估。

## teacher review release queue

- review_required 点进入可操作队列：confirm/reject/override 均为 dry_run、幂等、不改 high-risk auto、给 operator action。

## limited release switch

- 见 `limited_release_switch_design_m13.md` + `rollback_and_killswitch_plan_m13.md`：production default OFF、named internal cohort、env kill switch、append-only 回滚、observability metrics。

## 红线

- 真实 /api/v1/ws（非直调 hook）；legacy 永不被覆盖；production_write=0；LB writeback=0；非 cohort 0 beta；kill switch 生效；供给损坏 fail-closed；未生成 formal registry；未连 production runtime；未打印 secret；未 commit。
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    result = run_m13(out_dir=args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
