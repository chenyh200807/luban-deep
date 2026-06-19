---
type: "Concept"
title: "Asset Gap Map v1"
description: "Known gaps before candidate knowledge can become signed runtime supply."
resource: "docs/原始数据/数据盘点/extractions/asset_gap_map_v1/manifest.json"
tags:
  - "luban"
  - "okf"
  - "gap-map"
timestamp: "2026-06-19T00:00:00+08:00"
status: "asset_gap_map_only"
---

# Asset Gap Map v1

## Counts

- Open gap items: 9
- P1 gaps: 5
- P2 gaps: 4

## Next Actions

- PP1: `exam_content_gap` (139 affected) - Backfill exam taxonomy/analysis/score candidate gaps before signed grading release.
- PP1: `pdf_p1_compile_or_map` (21 affected) - Run PDF compiler or mapping workflow for the P1 queue before any release signing.
- PP1: `okf_case_level_alignment_backfill` (16 affected) - Backfill sub-question-level source alignment for the 16 case-level-only cases.
- PP1: `okf_candidate_not_signed_release` (25 affected) - Create signed release-candidate review pack; do not promote candidate scope directly.
- PP1: `runtime_policy_conflict_live_reader` (1 affected) - Decide whether to publish/sign the bank or change the reader default to a published pointer path.
- PP2: `runtime_published_pointer_consumer_evidence` (4 affected) - For each published pointer, run or record a true consumer read proof before calling it runtime-ready.
- PP2: `pdf_p2_verify_provenance` (39 affected) - Backfill PDF->JSON provenance map for candidate derivatives.
- PP2: `json_source_claim_review_gap` (383 affected) - Review source claims by bucket, prioritizing exam, standard, textbook, and taxonomy before lectures.
- PP2: `runtime_candidate_or_blocked_pointers` (11 affected) - Review candidate/blocked pointers one by one; publish only via signed gate.

## Boundary

This is a navigation concept for gaps. The OKF bundle stays Markdown-first; release signing remains outside the OKF format.
