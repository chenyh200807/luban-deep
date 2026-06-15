# 鲁班移动端 P0A Decision Package Template

> Status: Proposed / Decision package template
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

> v1.3 对齐（2026-06-15）：本决策包的 GO 判据已从"闭环走通 + 样本量"改为"**真实 D1/D7 回访留存** + 样本量"。完成率高、NPS 高但用户不回来，最多 WEAK-GO。这是 v1.2 → v1.3 收口要堵的坑（第一波内测 NPS 8-10 但 revisit=no）。

## 0. Decision

Verdict:

- [ ] GO
- [ ] WEAK-GO
- [ ] NO-GO

Recommended next step:

- [ ] Start P0B expansion.
- [ ] Continue P0A with fixes.
- [ ] Roll back / suspend.

Decision date:

Owner:

## 1. Executive Summary

Summarize in 6 lines:

1. What P0A proved.
2. **Whether users actually came back (D1/D7 retention) — the primary P0A question.**
3. What remains risky.
4. Whether user value is visible.
5. Whether authority boundaries held.
6. Whether P0B should start.

## 2. Scope Completed

| Scope item | Completed | Evidence |
| --- | --- | --- |
| F16 single-mother-topic spike | TBD | TBD |
| 3-5 expansion case_family assets after spike | TBD | TBD |
| Today main task | TBD | TBD |
| Light practice | TBD | TBD |
| Semi-write | TBD | TBD |
| Grading result page | TBD | TBD |
| learning_evidence write/readback | TBD | TBD |
| task_scope write/readback | TBD | TBD |
| canonical mistake_tag write/readback | TBD | TBD |
| Mistake review | TBD | TBD |
| Retest readback | TBD | TBD |
| WeChat true-entry smoke | TBD | TBD |

## 3. Case Family Coverage

| case_family | Status | Source | Scoring points | Tasks | Issues |
| --- | --- | --- | --- | --- | --- |
| F16 防水工程 | TBD | TBD | TBD | TBD | TBD |
| F01 | TBD | TBD | TBD | TBD | TBD |
| F02 | TBD | TBD | TBD | TBD | TBD |
| F04 | TBD | TBD | TBD | TBD | TBD |
| F05 | TBD | TBD | TBD | TBD | TBD |
| F03 费用索赔备选 | TBD | TBD | TBD | TBD | TBD |

## 4. Evidence Chain

Evidence required:

```text
attempt
-> grading result
-> point-level evidence
-> learning_evidence
-> mistake/read model
-> next task
-> retest readback
```

| Link | PASS/PARTIAL/FAIL | Evidence |
| --- | --- | --- |
| attempt -> grading | TBD | TBD |
| grading -> learning_evidence | TBD | TBD |
| task_scope -> scoped evidence | TBD | TBD |
| mistake_tag -> mistake read model | TBD | TBD |
| learning_evidence -> mistake read model | TBD | TBD |
| mistake -> next task | TBD | TBD |
| next task -> retest | TBD | TBD |

## 5. Gate Results

| Gate | Verdict | Blocker |
| --- | --- | --- |
| Frontend Source Tree Gate | TBD | TBD |
| Asset Gate | TBD | TBD |
| UX Gate | TBD | TBD |
| Trust Gate | TBD | TBD |
| Cost/SLA Gate | TBD | TBD |
| Authority Gate | TBD | TBD |
| Task Scope Evidence Gate | TBD | TBD |
| Mistake Tag Schema Gate | TBD | TBD |
| Authorization Gate | TBD | TBD |
| WeChat Gate | TBD | TBD |
| Rollback Gate | TBD | TBD |
| Observability Gate | TBD | TBD |
| Privacy Gate | TBD | TBD |
| Scenario Coverage Gate | TBD | TBD |
| Decision Sample Gate | TBD | TBD |

## 6. Metrics Snapshot

Product (留存优先 — 这是 P0A 的主指标):

- **D1 retention（次日回访，未催促）:**
- **D3 retention:**
- **D7 retention:**
- **试用窗口内人均活跃天数:**
- Main task start rate:
- Main task completion rate:
- Second attempt click rate:
- Similar question click rate:
- Mistake review completion rate:
- Retest pass/improve rate:

Quality:

- User-reported grading accuracy:
- Low-confidence OCR rate:
- High-risk grading rate:
- `uncertain` / `needs_review` rate:
- User correction rate:

Cost:

- Avg OCR cost:
- Avg grading cost:
- Grading P50 / P95 latency:
- Async fallback rate:
- Daily cost per active user:
- Free user cost cap status:

Sample:

- Gray users:
- Valid attempts:
- Mistake review / retest entries:
- QA/operator/test/real-student split:

## 7. User And Operator Feedback

User feedback:

- What users understood quickly:
- What confused users:
- Where trust dropped:
- Where users wanted more:

Operator feedback:

- Asset issues:
- Grading issues:
- QA issues:
- Support issues:

## 7.5 Scenario Coverage

| Scenario | PASS/PARTIAL/FAIL | Evidence | Fallback |
| --- | --- | --- | --- |
| Cold start | TBD | TBD | TBD |
| Returning normal | TBD | TBD | TBD |
| Interrupted | TBD | TBD | TBD |
| Exam sprint | TBD | TBD | TBD |
| Weak foundation | TBD | TBD | TBD |
| Low-confidence grading | TBD | TBD | TBD |
| Grading dispute | TBD | TBD | TBD |
| OCR failure / bad image | TBD | TBD | TBD |
| Unauthenticated | TBD | TBD | TBD |
| Entitlement-limited | TBD | TBD | TBD |
| Network failure | TBD | TBD | TBD |
| True WeChat entry | TBD | TBD | TBD |
| Privacy delete/export | TBD | TBD | TBD |

## 8. Authority Review

Answer yes/no:

- Did frontend avoid score computation?
- Did frontend avoid mastery computation?
- Did frontend avoid next_action computation?
- Did OCR raw text stay out of grading?
- Did behavior events stay out of learner memory?
- Did RAG / knowledge map stay out of scoring adjudication?
- Did all chat remain on `/api/v1/ws`?
- Did `priority_score` only rank/explain backend-authorized candidates?
- Did light/semi-write evidence include task_scope?
- Did out-of-scope scoring points avoid miss evidence?
- Did mistake_tag use canonical id and taxonomy version?
- Did retest prefer same scoring_point on a different question?

Any `no` blocks GO.

## 8.1 Authorization Review

Record:

- QA/operator write path:
- Test-user write path:
- Real-student whitelist or governed promotion arm:
- Whether real-student learning_evidence writes are enabled:
- Owner approval:

If real-student writes are enabled without explicit authorization evidence, verdict cannot be GO.

## 9. WeChat Evidence

Record:

- devtools_project_root:
- target_subpackage:
- target_page:
- entry_flow:
- auth_state:
- auth_mode:
- result:
- artifact path:

If this section is pending, verdict cannot be GO.

## 9.1 Frontend Source Tree Evidence

Record:

- development_source_tree:
- validation_tree:
- latest_upload_source:
- sync_manifest_or_porting_evidence:
- drift_check_result:

If development and validation trees differ without sync evidence, verdict cannot be GO.

## 10. Rollback Readiness

- Today entry rollback:
- OCR path rollback:
- case_family rollback:
- high-risk grading preview fallback:
- evidence write protection:
- user-visible fallback copy:

## 11. Final Recommendation

Choose one:

### GO

Use only if all blocking gates pass, true-entry evidence exists, the **pre-registered retention threshold is met** (set D1 / D7 return targets BEFORE the run, e.g. D1 >= X%, D7 >= Y% returned without nagging — not after), and sample thresholds are met: at least 20 gray users, 100 valid attempts, and 30 mistake review/retest entries. High completion or high NPS without real return is NOT a GO.

### WEAK-GO

Use if P0A value is proven but one controlled, named risk remains, or if sample size is below GO threshold. Must include scope limit and expiration date.

### NO-GO

Use if authority, trust, asset, true-entry, or rollback gate fails.

Final recommendation:

Rationale:

Required fixes before P0B:
