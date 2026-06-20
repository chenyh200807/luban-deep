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
timestamp: "2026-06-20T00:00:00+08:00"
status: "ai_project_context_only"
---

# DeepTutor Governance Map

## What It Is

This card helps AI find the right project governance source before changing plans, contracts, runbooks, or agent behavior.

## Counts

- Files: 256
- Total bytes: 5890667

## Domain Split

- `plan`: 188
- `agent_skills`: 45
- `contracts`: 14
- `runbook`: 7
- `docs_contracts`: 2

## Area Split

- `governance_context`: 76
- `contract_authority`: 37
- `ci_quality_gate`: 31
- `data_knowledge`: 29
- `learner_state`: 24
- `billing_business`: 19
- `agent_skill`: 11
- `release_operations`: 10
- `wechat_frontend`: 10
- `planning_index`: 9

## Risk Split

- `low`: 98
- `medium`: 80
- `high`: 78

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
