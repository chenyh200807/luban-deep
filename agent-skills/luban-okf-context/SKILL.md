---
name: luban-okf-context
description: "Use when a task asks what Luban/DeepTutor data assets contain, where教材/真题/讲义/规范/编译资产 are, how a 建筑实务 topic is covered, or which source evidence supports an answer. Routes agents through AI-only OKF cards before reading raw sources."
---

# Luban OKF Context

Use this skill to make Claude Code, Codex, or another repo-local agent discover
and use the AI-only OKF bundle consistently.

## Boundary

OKF is an AI context and source-navigation layer only.

It is not:

- production runtime supply;
- official scoring authority;
- LearnerState, GBrain, RAG, or registry truth;
- a full mirror of PDFs, JSON, textbooks, standards, or lecture payloads.

## Trigger

Read this skill when the user asks about:

- what data assets exist;
- where教材、真题、讲义、规范、PDF、JSON、编译资产 are;
- a topic such as 屋面防水、流水施工、网络计划、索赔、质量验收;
- exam frequency, topic coverage, source evidence, or answer grounding;
- whether an artifact is candidate, release, fixture, runtime-shadow, or governance context.

## Workflow

1. Start at `docs/原始数据/数据盘点/okf_bundle_v0/index.md`.
2. For asset inventory questions, follow `assets/*` and `content_cards/index.md`.
3. For topic questions, follow `topics/index.md`, then the specific topic card.
4. Treat all OKF counts and snippets as navigation evidence. Before making a
   high-stakes claim, follow the linked source paths to raw JSON, rubric
   candidate, standard, textbook, or inventory report.
5. State the boundary in the answer when relevant: candidate evidence, not
   official scoring or production runtime truth.

## Thin Wrapper / Fat Skill Split

This skill is the thin wrapper: it only tells the agent when and where to read.

The fat work stays in the OKF compiler scripts and generated cards:

- `docs/原始数据/数据盘点/scripts/build_okf_bundle.py`
- `docs/原始数据/数据盘点/scripts/build_topic_okf.py`
- `docs/原始数据/数据盘点/okf_bundle_v0/`

## Red Flags

- Answering a topic question from memory without checking OKF.
- Treating keyword hit counts as official exam frequency.
- Treating `artifacts/*` workbench output as runtime supply.
- Copying full source payloads into an answer when a path and short summary are enough.
- Adding a production consumer for OKF without a separate signed runtime-supply gate.

## Verification

- [ ] The answer names the OKF card or source path used.
- [ ] Candidate vs official vs runtime truth boundary is clear.
- [ ] For topic answers, the relevant `topics/*.md` card was checked first.
- [ ] High-stakes claims were verified against linked raw sources or inventory reports.
