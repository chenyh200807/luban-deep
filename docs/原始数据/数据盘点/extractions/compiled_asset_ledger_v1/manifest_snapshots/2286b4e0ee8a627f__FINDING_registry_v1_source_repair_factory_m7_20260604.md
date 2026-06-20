# FINDING — Registry v1 Source Repair Factory M7 (2026-06-04)

## 必答
1. 125 blocked points 全量分类？ YES，125/125 全部归类，0 unclassified。每类：{'external_source_needed': 51, 'figure_label_not_runtime_safe': 1, 'calculation_spec_missing': 20, 'semantic_allowed_not_runtime_safe': 28, 'list_rule_denominator_missing': 12, 'rewrite_needed': 13}。
2. 找到可用 repaired textbook exact anchor 的点？ **0**（verbatim 2026 教材 exact-match + runtime-safe policy + council 支撑）。
3. 仍只能 keep_draft？ **0**（有 verbatim 锚但 policy 不完整/非 runtime-safe）。
4. 应 drop / require_external_source？ **125**（无 verbatim 锚）。
5. 是否有 official_answer/explanation 被错误升 textbook？ **NO**（source 仅 2026 教材 verbatim exact-match；official_answer_upgraded_to_textbook=0；invariant 断言）。
6. AI Expert Council 只裁决不替代 source？ **YES**（council 只判语义支撑；source 必须先有 verbatim 锚）。
7. v1 repair 后理论 auto_certifiable？ 25 -> **25**。
8. runtime preview 仍未连接 production？ **YES**（production_runtime_connected=false，dry_run_preview，未发布）。
9. 进入 M8 Registry v1 gated beta？ **NO-GO**（repaired=0）。
   根因：**0/125 点带结构化 required_terms** —— 0 锚可搜，AI Expert Council 可裁决集为空（spawned=0，未空转）。
10. 单句决策建议：M7 证明真瓶颈在**上游 rubric 规范化**（采分点普遍缺 required_terms/spec），其次才是教材锚覆盖；下一步应回 M3 给这 125 点补结构化 required_terms / calculation_spec / list denominator，再重跑 M7 source hunt + AI council，**不要再加模型/再跑 jury**（无 source 可裁）。

## 红线
不生成正式 registry / 不接 runtime / 不改 kernel·RAG·DB / official_answer 不当 textbook / LLM vote 不当 source / human_reviewed=false / 未 commit。
