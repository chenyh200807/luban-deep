# FINDING — M7 AI Expert Council Final → Registry v1 Candidate Compiler Hardening

**日期**: 2026-06-04
**目标**: 把 M5D council-final 规则固化成 deterministic compiler hard gates，再用 6 个 approve 点做 hardened candidate preview。
**边界**: 不生成正式 Registry v1，不接 production runtime / DB / RAG / kernel / web / BI / billing，不发 live LLM，不 commit / 不 stage。

## 调用账 / 复现

```bash
python3 -m scripts.build_luban_registry_v1_council_hardened_candidate_m7
```
0 次 live LLM。输入 = M5D council 结果（9 题 / 25 点）+ M5A refined packet（取锚）+ 2026 教材（确定性 verbatim 复验）。确定性、可复现。

## 10 个必答

### 1. M5D 25 个点是否全部读取并分类？
**YES。** `m5d_council_input_audit.json`：`total_points_read=25`，`all_points_classified=true`，
`by_council_action = {approve_with_repaired_anchor:6, split_point:5, require_external_source:5, rewrite_point:4, drop_point:4, keep_draft:1}`，
`final_authority_seen=["ai_expert_council_final"]`，`human_reviewed_any=false`。

### 2. 6 个 approve_with_repaired_anchor 中多少通过 deterministic exact-match 复验？
**6 / 6 全部通过。** `repaired_anchor_reverification.json`：6 个均为 `exact_required` 单点单锚，
对 2026 教材独立重跑 verbatim 成员测试，`reverification_passed=true`、`compiled_auto_certifiable=true`。
这 6 点 = M2-2015-34-01 的 P2/P3/P5/P7 + M2-2016-30-01 的 P3/P4（全是"改错题正确做法句 / 逐条情形句"）。

### 3. 是否有任何 list_rule partial anchor 被 auto？
**NO。** `list_rule_coverage_audit.json`：8 个 list_rule 点，`auto_eligible_by_full_coverage_count=0`，
`partial_coverage_auto_blocked=true`。覆盖率从 0.0 到 0.6 不等，**无一**达到 1.0，全部被硬门拦下。
（注：M7 对每个 list item 独立重跑全教材 verbatim，比 M5D 单题锚更严，部分题覆盖数上升但仍 <1.0。）

### 4. split/rewrite/drop/external_source/keep_draft 是否全部 blocked from auto？
**YES。** `blocked_by_council_action.json`：`blocked_point_count=19`，
`by_action={split_point:5, rewrite_point:4, require_external_source:5, drop_point:4, keep_draft:1}`。
artifacts preview 中**唯一** `auto_certifiable=true` 的点其 `council_action` 必为 `approve_with_repaired_anchor`（测试 `test_non_approve_actions_all_blocked_from_auto` 强制）。

### 5. council final 是否没有替代 textbook source authority？
**YES（没有替代）。** 每个 auto 点的 `source_authority` 必须是 `textbook_exact_match`，且经独立 verbatim 复验；
`final_authority=ai_expert_council_final` 只是 triage/终裁标签。`source_authority` 取值域被限制为 `{textbook_exact_match, source_gap}`；
凡 `source_gap` 的点 `auto_certifiable` 一律 false（测试强制）。

### 6. hardened candidate preview 中题数/点数/auto_certifiable 数？
**题数 9 / 点数 25 / auto_certifiable 6。** 见 `hardened_candidate_registry_preview.json`
（`question_count=9, point_count=25, auto_certifiable_point_count=6`）。注意：这 9 题仍**全部** `council_not_publish`——
没有一题所有点都达标，6 个 auto 点散落在 2 道题里，单题内仍有 blocked 点。

### 7. runtime gate dry-run 是否仍 prod_connected=false、正式 auto=0？
**YES。** `runtime_gate_dry_run_results.json`：`production_runtime_connected=false`、`formal_runtime_connected=false`、
`artifact_auto_certification_allowed_count=0`、`point_auto_certified_after_gate_count=0`。
原因：candidate 产物 status=`candidate_dry_run` ≠ `published`，现有 ArtifactRuntimeGate 对非 published 一律下调，
即使 6 个点编译期标了 auto_certifiable，**runtime 也不放行**。复用既有 gate，零改动。

### 8. v0 是否被覆盖、删除或 supersede？
**NO。** `v0_integrity_audit.json`：`v0_overwritten_by_m7=false`、`v0_deleted_by_m7=false`、`v0_superseded=false`、
`v0_exists=true`，并记录了 v0 目录 SHA256 摘要。M7 全程不读不写 v0，v0 仍是唯一 canonical published registry。

### 9. M8 是否可以进入 gated beta？
**WEAK-GO。**
- 支撑 GO 的：root cause（list partial over-credit）已在编译期堵死并有测试守护；6 个 auto 点经独立 verbatim 复验；runtime gate 证明 candidate 不会误放行；v0 完好。
- 拉回 WEAK 的：9 道争议题**0 题可整题 publish**；可 auto 的 6 个点全集中在 2 道题且都是"改错题正确做法"单点形态，样本太薄，不足以支撑一个有意义的 gated beta 数据面；其余 19 点需补源/改写/拆分。
- 结论：可以进入**极窄范围**的 gated beta（仅 shadow / 仅这 6 个已复验点参与 auto，其余继续 review），但**不能**当作 Registry v1 正式数据面。建议 M8 = "gated shadow beta on the 6 reverified points only"，而非全量 beta。

### 10. 下一步是扩大 source repair factory，还是开始 QA beta？
**先扩大 source repair factory（主线），QA beta 仅作窄 shadow 并行。**
理由：当前瓶颈是 auto 点供给太少（25 → 6，且 0 整题 publish）。19 个 blocked 点里
5 个 split / 4 个 rewrite / 5 个 require_external 都是**可工程化修复**的——
做一个确定性的 "source repair factory"（按 item 逐项 verbatim 锚定、改错题只取正确做法句、列表拆分、外部源补齐工单）能把 auto 点供给放大一个量级。
QA beta 此刻数据面太薄，单独开收益低；让它以"仅 6 个已复验点的 shadow"形式并行，积累 runtime 证据即可。

## 产物清单（本目录）
compiler_hard_gate_rules.json · m5d_council_input_audit.json · repaired_anchor_reverification.json ·
list_rule_coverage_audit.json · hardened_candidate_registry_preview.json · hardened_candidate_artifacts_preview.jsonl ·
blocked_by_council_action.json · runtime_gate_dry_run_results.json · v0_integrity_audit.json · m7_summary.json · 本 FINDING
