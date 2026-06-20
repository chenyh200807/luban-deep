---
type: "BundleIndex"
title: "Luban OKF-like Rubric Pilot v0"
description: "One-case OKF-like generated review projection for rubric traceability experiments."
timestamp: "2026-06-19T00:00:00+08:00"
canonical_id: "luban_okf_rubric_pilot_v0"
authority: "training_org_analysis_yousen"
not_official: true
official_score_allowed: false
tags: ["luban", "rubric", "okf-pilot"]
---

# Scope

This bundle is a generated review projection from the canonical extraction. It is not official scoring authority and is not wired to runtime.

# Case

- [case_2021_1](cases/case_2021_1.md)

# Counts

- Rubrics: 5
- Scoring points: 15

# Guardrails

- Markdown files in this bundle are generated review projections, not canonical source truth.
- `official_score_allowed` is always `false`.
- Runtime must consume only separately signed/versioned supply.
- This pilot must not write LearnerState, GBrain, or production registry.
