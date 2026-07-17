---
type: "Concept"
title: "Luban Grading Artifacts Map"
description: "AI-only map of artifacts/luban_grading_artifacts with area and risk boundaries."
resource: "docs/原始数据/数据盘点/extractions/luban_grading_artifacts_okf_v1/manifest.json"
tags:
  - "luban"
  - "okf"
  - "grading-artifacts"
  - "ai-context-only"
timestamp: "2026-07-16T14:54:49+08:00"
status: "ai_project_context_only"
---

# Luban Grading Artifacts Map

## What It Is

This card helps AI understand the shape of `artifacts/luban_grading_artifacts` without treating any artifact as production truth.

## Counts

- Runs: 347
- Files: 3326
- Manifest-like files: 771
- Total bytes: 367180283

## Area Split

- `artifact_workbench`: 84
- `governance_audit`: 62
- `runtime_shadow`: 59
- `release_candidate`: 54
- `source_alignment`: 40
- `eval_benchmark`: 25
- `learning_brain`: 14
- `gold_review`: 7
- `skill_pack`: 2

## Risk Split

- `high`: 146
- `low`: 131
- `medium`: 70

## High-Risk Context Sample

- `rich_leaf_frozen_v1_runtime_default_gate_chain_20260613`: area=`runtime_shadow`, files=13
- `luban_taxonomy_runtime_supply_rebuild_20260612`: area=`runtime_shadow`, files=58
- `rich_leaf_per_leaf_pollution_fix_candidate_v3_20260621`: area=`release_candidate`, files=5
- `rich_leaf_per_leaf_pollution_fix_candidate_20260621`: area=`release_candidate`, files=4
- `rich_leaf_full2026_field_promotion_review_materialized_20260612`: area=`release_candidate`, files=1
- `rich_leaf_full2026_field_candidates_materialized_20260612`: area=`release_candidate`, files=1
- `rich_leaf_full2026_artifact_candidates_materialized_20260612`: area=`release_candidate`, files=1
- `rich_leaf_per_leaf_pollution_fix_candidate_v2_20260621`: area=`release_candidate`, files=4
- `rich_leaf_full2026_candidate_patches_20260612`: area=`release_candidate`, files=1
- `canonical_unified_knowledge_20260606`: area=`release_candidate`, files=4
- `luban_concept_registry_adjudication_20260612`: area=`release_candidate`, files=8
- `rich_leaf_full2026_semantic_runtime_live_provider_trace_20260612`: area=`runtime_shadow`, files=12
- `rich_leaf_full2026_reviewed_source_file_context_candidates_20260612`: area=`release_candidate`, files=1
- `luban_taxonomy_dedup_rehome_candidate_20260612`: area=`release_candidate`, files=2
- `rich_leaf_frozen_v1_learning_brain_closure_20260613`: area=`learning_brain`, files=6
- `knowledge_graph_20260606`: area=`source_alignment`, files=5
- `rich_leaf_full2026_runtime_supply_regression_materialized_20260612`: area=`runtime_shadow`, files=1
- `supabase_canonical_export_20260606`: area=`release_candidate`, files=3
- `rich_leaf_source_gap_candidates_20260611`: area=`release_candidate`, files=1
- `knowledge_hybrid_matrix_live_ab_20260614_qwen_deepseek_6`: area=`runtime_shadow`, files=8

## Use

- Use this map to orient AI around grading experiments, gold reviews, source alignment, runtime-shadow evidence, and learning-brain artifacts.
- Treat high-risk entries as context requiring separate verification, not as usable production supply.
- Follow the ledger files when exact artifact paths are needed.

## Boundary

This OKF card is only for AI project understanding. It does not participate in production, does not sign runtime supply, and does not authorize official scoring.
