# 鲁班案例题 + rubric 数据 schema v0（Registry v1 解锁前置 · M1）

> Status: `Frozen v0`（2026-06-04）。这是 [数据扩产计划](2026-06-04-luban-case-rubric-data-expansion-plan.md) 的 M1：
> **冻结案例题 + audit packet 数据 schema + verify-on-write 教材锚定规则**，并产出真实样例。
> 不产假 registry v1。红线：不伪造 source_ref/textbook_quote、不把 official_answer 当强锚、
> 不把 node-level 6134 资产当 question rubric、不接 runtime、不改 kernel/RAG、不新增表。
> 校验实现 `scripts/luban_case_rubric_schema.py`；样例 `artifacts/luban_grading_artifacts/case_rubric_data_schema_m1_20260604/`。

## 实体

### CaseRubricSourceRecord（原始题）
`question_id` / `question_text` / `official_answer` / `node_code` / `source_exam`。

### RubricCandidate（候选，非 authority）
`point_id` / `label` / `candidate_source`（`golden_human_anchored` | `model_4jury` | `answer_derived`）/ `is_authority`（默认 false，须 teacher/PO 复核升格）。

### TextbookAnchorEvidence（教材锚证据）
`source_type=textbook` / `chunk_id` / `textbook_quote` / `verified`(bool) / `match_method`(`verbatim` 唯一可 verified)。

### TypedPolicy
`policy_type`（exact_required | list_rule | calculation | penalty_rule | figure_label | high_risk_review）/ `required_terms` / `list_spec{denominator,terms}` / `numeric_spec` / `penalty_spec`。

### QuestionGradingArtifactDraft（采分点）
`point_id` / `label` / `policy_type` / `max_score` / `required_terms` / `list_spec` / `calculation_spec` / `penalty_rule` / `source_refs[]`(TextbookAnchorEvidence-shaped) / `source_status`(ok|missing_or_weak) / `auto_certifiable`。

### AuditPacket（每题一份）
```jsonc
{
  "schema_version": "luban_case_rubric_audit_packet.v0",
  "question_id": "", "question_text": "", "official_answer": "", "node_code": "", "source_exam": "",
  "rubric_candidates": [RubricCandidate],
  "textbook_anchor_evidence": [TextbookAnchorEvidence],
  "teacher_review_status": "unreviewed|reviewed|rejected",
  "artifact_status": "draft|published|blocked",
  "scoring_points": [QuestionGradingArtifactDraft],
  "quality_gate": { "published": bool, "auto_certifiable_points": int, "weak_points": int, "verify_on_write": "verbatim_textbook_only" },
  "provenance": { "compiled_from": "", "compiler": "", "content_hash": "" }
}
```

## verify-on-write（单一 gate）

见 `verify_on_write_rules.md`。要点：`auto_certifiable=true` 当且仅当该点有 ≥1 个
**verbatim** textbook 锚（chunk_id + textbook_quote + 逐字命中 content_markdown）且满足 policy 最小要求；
official_answer / node seed / 语义近义**永不** verified；published ⟹ ≥1 auto 点；draft/blocked ⟹ 0 auto 点。

## authority 顺序

教材 content_markdown 原文 > 官方答案（结构 seed）> 多模型 rubric 候选（只候选）> teacher/PO review（升 authority）。
node-level 6134 资产只作 search seed。

## 样例（真实，非手造）

- `sample_audit_packet_published.json`：Q17-1A433000，2 个 verified textbook 锚（含 chunk `1A412010_068_0132`），status=published，auto 点 2。
- `sample_audit_packet_draft_or_blocked.json`：Q20-1A413000，0 auto，status=draft（`no_auto_certifiable_points`）。

## 测试

`tests/scripts/test_luban_case_rubric_data_schema_m1.py`（7 passed）：published 有 verified 锚 / draft 0 auto /
official_answer 不 verified / 缺 chunk·quote 不 verified / 语义不 verified / auto 无 verified 锚=违规 / schema 字段齐。

## 下一步（M2）

按本 schema 采集第一批 20–30 道新案例题，走「official_answer 解析 → 4-model 候选 → verbatim 教材锚定 →
typed_policy → teacher/PO 复核 → AuditPacket」，喂 `build_luban_question_grading_registry_v1.py`（当前 data_blocked）解锁全题库。
