# Compiled Knowledge Shadow Lessons

Date: 2026-06-09

Scope: M34 general knowledge compiled teaching context, TutorBot RAG-only vs RAG+compiled shadow evaluation, source pollution feedback, and system-wide default gate.

## Current Status

```text
capability_go=true
test2_shadow_opt_in_bridge_verified=true
system_wide_default_go=false
canonical_truth_written=false
production_write_count=0
default_decision=NO-GO
```

M34 has proved that compiled teaching context can be attached to general TutorBot knowledge turns through the existing `/api/v1/ws` path. It has not yet proved that the capability should be broadly default-on for every learner conversation.

## Evidence

- Local capability gate: M34 runner and `/api/v1/ws` TestClient gate passed with safety invariants: `official_score_allowed=false`, `llm_may_decide_correctness=false`, `canonical_truth_written=false`, `production_write_count=0`.
- test2 online shadow smoke: 10 TutorBot questions, 9 evaluable. compiled hit `7/9=77.8%`, wrong path `0%`, source validity `7/7=100%`, fail-open `2/9=22.2%`, answer improvement `1/9=11.1%`, answer regression `0%`, token delta avg `-25.6`. One control arm stream failed and was excluded as transport/service error.
- test2 50-case online shadow: 50/50 cases eventually evaluable after retry batching; `compiled_hit_rate=19/50=38%`, `wrong_path_rate=5/50=10%`, `source_validity_rate=14/19=73.7%`, `fail_open_rate=31/50=62%`, `answer_improvement_rate=0%`, `answer_regression_rate=0%`, `token_delta_avg=+25.08`. The run required 122 attempted turn pairs because test2 repeatedly hit WS `1012 service restart` / nginx `502` windows and the container was observed recreated during the run.
- Online wrong-path cases: `open_019` 幕墙防火封堵→幕墙面板分类, `open_020` 四节一环保→绿色施工信息化系统, `open_036` 地下防水等级→种植屋面防水等级, `open_046` 施工组织设计审批→装配式混凝土施工组织设计要求, `open_049` 冬期施工混凝土养护→一般混凝土养护要求.
- Local 50-query compiler pollution audit: `103` `repair_compiled_source_path_alignment` work orders across `88` affected nodes. All entries stayed in `namespace=luban_compiler_candidate`, with `promote_to_release=false`, `release_truth_written=false`.
- Online wrong-path compiler feedback: the five online wrong-path queries generated `21` additional `repair_compiled_source_path_alignment` work orders across `21` affected nodes, still only in `namespace=luban_compiler_candidate` with no release/canonical write.
- Local compiler repair overlay: `runtime_supply/v_canonical_unified_knowledge/source_alignment_repairs.json` now detaches the high-risk wrong-path source/path clusters for the five online failures. It is bound to the current compiled bundle `content_hash`, remains `tier=teaching_context_not_answer_key`, and keeps `official_score_allowed=false`, `llm_may_decide_correctness=false`, `canonical_truth_written=false`, `production_write_count=0`.
- Local 50-case resolver recheck after review fix: compiled hit `13/50=26%`, wrong path `0/50=0%`, source validity `13/13=100%`, fail-open `37/50=74%`. This is local compiled resolver evidence only; it does not replace a fresh test2 `/api/v1/ws` online shadow after deploy. The review fix keeps `detach_node_from_general_compiled_context` scoped to general query planning; direct canonical packs remain available to other consumers.
- Local compiler pollution audit after repair: `106` candidate work orders across `90` affected nodes remain. This means the repair reduced prompt pollution for the observed high-risk cases but the compiler source-attach pipeline still needs broader detach/re-anchor work before system-wide default.

## Lessons

1. Prove pack delivery before answer quality. If compiled metadata does not reach TutorBot prompt metadata, a shadow test measures wiring failure rather than knowledge quality.
2. Run 10 before 50/100. A small online smoke catches flag, cohort, route, metadata, and transport problems before wasting large samples.
3. Treat hit rate as conditional. High hit rate is only good when query, canonical path, and source text agree.
4. Fail-open is a product requirement, not a weakness. Low confidence, off-domain, or query/path/source mismatch must continue through original TutorBot RAG without compiled prompt pollution.
5. Runtime gating is not compiler repair. Cases like network-plan/total-float snippets attached to cement or concrete nodes must become compiler detach/re-anchor work orders.
6. Shadow pass is not production default. Default-on requires hit rate, wrong path, source validity, answer improvement/regression, token cost, fail-open, and compiler repair evidence.
7. Retry-batched online shadow is acceptable for eval accounting only if each case is deduped to first successful control+treatment pair and failed attempts are reported separately. Do not hide the operational instability behind the deduped metrics.

## Required Gate Before System-Wide Default

Before broad default-on, run a 50/100+ online TutorBot shadow over the real `/api/v1/ws` entry and report:

- compiled hit rate
- wrong path rate
- source validity
- answer improvement and regression
- token cost delta
- fail-open rate and fail-open type breakdown
- non-evaluable transport/service errors
- compiler pollution work orders and repair status

Current default decision: **NO-GO**. Default can only be discussed after the repair overlay is deployed to test2 shadow cohort, a fresh 50/100+ online `/api/v1/ws` shadow confirms low wrong-path/source-validity regressions under real TutorBot traffic, broader compiler pollution work orders are triaged, and all safety invariants remain false/zero for grading authority and learner-truth writes.
