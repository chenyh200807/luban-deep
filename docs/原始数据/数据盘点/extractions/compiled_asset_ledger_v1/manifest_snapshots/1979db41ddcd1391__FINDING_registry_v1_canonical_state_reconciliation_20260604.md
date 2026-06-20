# FINDING — Registry v1 Canonical State Reconciliation（2026-06-04）

1. 当前最新 canonical 状态：**Registry v1 direct M6 publish-candidate = NO-GO**。M5C 是最新队列 authority：30 题全部 `pending_po`，live-reviewed 11 题中 publish_ready=0，source_anchor_dispute=9。
2. 仍有效的 M5 结论：34 题 / 150 点事实表仍有效；25 个 `auto_certifiable` 只作为 deterministic baseline；112 个 `official_weak` 和 13 个 `rewrite_needed` 不能 auto；formal registry 未生成。
3. 已被 supersede 的 M5 结论：M5 `publish_ready_candidate=2` 已被 M5B/M5C 下调；M5 `M6 WEAK-GO` 已变为 direct M6 NO-GO；M5 provider_unavailable 已被 M5R provider readiness 修正。
4. 是否允许现在直接跑 M6：**NO-GO**。M5R 的 1 个 publish_candidate（M2-2015-32-00）也被 live M5B/M5C 下调为 `needs_po_review`；当前可直接进入 M6 publish_candidate 的题数是 0。
5. M5D 应处理的 source_anchor_dispute：M2-2015-30-00, M2-2015-32-00, M2-2015-32-01, M2-2015-33-00, M2-2015-34-00, M2-2015-34-01, M2-2015-34-03, M2-2016-30-01, M2-2016-31-02。这些题的 live jury 判定教材锚不支撑采分点或需要重写/外部源。
6. 无真人专家时的 AI Expert Council Final contract：可以引入 `review_source=ai_expert_council_final` / `reviewer_type=ai_expert_council` 作为非人类 review finality；必须写 `human_reviewed=false`、`po_reviewed=false`，不能写 human/PO/manual teacher 字段；不能替代 `source_authority=deterministic_textbook_exact_match`，不能生成或伪造 textbook_quote/source_ref，不能把 official_answer 升 verified。
7. 下一条执行 prompt：见 `next_step_decision.md`，任务名为 **M5D AI Expert Council Source Court**；不要先跑 M6。

## Additional Notes

- M5B FINDING 中“2 题试点”的文字已陈旧；同目录 `jury_live_summary.json` 与 M5C 证明当前 canonical 是 11 题 live jury、33/33 real votes、publish_ready=0。
- M5R provider_blocked 已解除到 quorum 级别，但 OpenAI/Anthropic 原始 4 模型仍不是全部 configured；这不阻塞 M5D，但不能包装成 full original 4-model council。
- 本轮只生成 reconciliation artifacts；未发起 live LLM，未生成正式 registry，未接 runtime，未改 kernel/RAG/DB/web/BI/billing，未 commit/stage。
