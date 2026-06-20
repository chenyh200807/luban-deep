---
type: "Concept"
title: "Knowledge Compiler Workbench"
description: "Compiler-run ledger for artifacts/knowledge_compiler with candidate/release/fixture boundaries."
resource: "docs/原始数据/数据盘点/extractions/knowledge_compiler_okf_v1/manifest.json"
tags:
  - "luban"
  - "okf"
  - "knowledge-compiler"
  - "compiled-assets"
timestamp: "2026-06-20T00:00:00+08:00"
status: "knowledge_compiler_workbench_inventory_only"
---

# Knowledge Compiler Workbench

## What It Is

This card routes AI into `artifacts/knowledge_compiler/2026` without copying compiler payloads into OKF.

## Counts

- Runs: 14
- Files: 189
- Manifest-like files: 31
- Total bytes: 50729003

## Stage Split

- `candidate`: 10
- `fixture`: 4

## Run Kinds

- `test_fixture`: 4
- `scoring_point_recall_calibration`: 3
- `rubric_ab_eval`: 2
- `rubric_artifact_candidate`: 2
- `lecture_compile`: 1
- `answer_rubric_candidate`: 1
- `scoring_point_candidate_assets`: 1

## Top Runs

- `lecture_compile_20260608`: stage=`candidate`, kind=`lecture_compile`, files=8
- `mvp-answer-rubric-20260531`: stage=`candidate`, kind=`answer_rubric_candidate`, files=3
- `mvp-rubric-ab-20260531`: stage=`candidate`, kind=`rubric_ab_eval`, files=4
- `mvp-rubric-ab-20q-20260531`: stage=`candidate`, kind=`rubric_ab_eval`, files=4
- `mvp-rubric-artifact-20260531`: stage=`candidate`, kind=`rubric_artifact_candidate`, files=5
- `mvp-rubric-artifact-20q-20260531`: stage=`candidate`, kind=`rubric_artifact_candidate`, files=5
- `scoring-point-assets-20260602`: stage=`candidate`, kind=`scoring_point_candidate_assets`, files=84
- `scoring-point-recall-calibration-20260602`: stage=`candidate`, kind=`scoring_point_recall_calibration`, files=7
- `scoring-point-recall-calibration-v2-20260602`: stage=`candidate`, kind=`scoring_point_recall_calibration`, files=18
- `scoring-point-recall-calibration-v2-backfill-20260602`: stage=`candidate`, kind=`scoring_point_recall_calibration`, files=26
- `pytest-core-a`: stage=`fixture`, kind=`test_fixture`, files=8
- `pytest-core-b`: stage=`fixture`, kind=`test_fixture`, files=10
- `pytest-inventory`: stage=`fixture`, kind=`test_fixture`, files=2
- `pytest-scoring-point-assets`: stage=`fixture`, kind=`test_fixture`, files=5

## Use

- Use candidate runs to find compiler-produced teaching cards, rubric candidates, scoring-point assets, and recall calibration material.
- Use fixture runs only for test/workbench reproduction.
- Treat release-named runs as release-shaped until runtime supply has a separate signed pointer.

## Boundary

This OKF card is a workbench navigation layer. It does not sign runtime supply, write canonical truth, or authorize official scoring.
