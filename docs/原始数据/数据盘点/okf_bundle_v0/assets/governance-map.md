---
type: "Concept"
title: "DeepTutor Governance Map"
description: "AI-only map of plans, runbooks, contracts, docs/contracts, and agent-skills."
resource: "docs/原始数据/数据盘点/extractions/governance_okf_v1/manifest.json"
tags:
  - "deeptutor"
  - "okf"
  - "governance"
  - "ai-context-only"
timestamp: "2026-07-16T14:54:49+08:00"
status: "ai_project_context_only"
---

# DeepTutor Governance Map

## What It Is

This card helps AI find the right project governance source before changing plans, contracts, runbooks, or agent behavior.

## Counts

- Files: 348
- Total bytes: 7833394

## Domain Split

- `plan`: 274
- `agent_skills`: 50
- `contracts`: 14
- `runbook`: 8
- `docs_contracts`: 2

## Area Split

- `governance_context`: 145
- `contract_authority`: 40
- `ci_quality_gate`: 36
- `data_knowledge`: 30
- `billing_business`: 25
- `learner_state`: 25
- `agent_skill`: 14
- `wechat_frontend`: 13
- `release_operations`: 11
- `planning_index`: 9

## Risk Split

- `low`: 166
- `medium`: 95
- `high`: 87

## Mandatory Entry Points

- `agent-skills/catalog.yaml`: role=`agent_behavior_guidance`, area=`governance_context`
- `contracts/index.yaml`: role=`contract_reference`, area=`contract_authority`
- `docs/plan/INDEX.md`: role=`plan_index`, area=`planning_index`
- `docs/runbook/ci-runtime-smoke-guardrails.md`: role=`operational_runbook`, area=`ci_quality_gate`

## Use

- Use this map before planning, release, CI repair, contract changes, source-grounded changes, or agent-skill work.
- Follow the referenced source document for exact instructions; this card is only a router.
- Treat high-risk governance documents as mandatory read-before-act context.

## Boundary

This OKF card is only for AI project understanding. It does not replace contracts, runbooks, plans, or skills and does not participate in production.
