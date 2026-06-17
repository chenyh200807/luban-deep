---
name: deeptutor-source-grounded-change
description: "Grounds DeepTutor changes in authoritative sources. Use when a task depends on current framework, library, OpenAI, WeChat, Supabase, browser, protocol, API, or external-product behavior where stale model memory could be wrong."
---

# DeepTutor Source Grounded Change

Use this skill when correctness depends on facts outside the current repo.

## Workflow

1. Identify the source category: repo contract, official docs, provider docs,
   GitHub upstream, standards document, or product UI behavior.
2. Prefer local authority first: `AGENTS.md`, `CONTRACT.md`,
   `contracts/index.yaml`, `docs/plan/INDEX.md`, runbooks, and tests.
3. For external facts, use official or primary sources. Avoid blog summaries
   unless the task is explicitly about community sentiment.
4. Record the exact version, date, URL, commit, package version, or doc page
   used for the decision.
5. Translate the source into DeepTutor's existing authority. Do not add a new
   router, state source, memory, RAG, or release checklist just because the
   upstream has one.
6. Verify with focused tests or doc/skill validation, then cite the source in
   the final report when source facts influenced the result.

## Red Flags

- Using model memory for an API that may have changed.
- Treating a third-party sample app as DeepTutor architecture.
- Copying upstream commands that bypass local deployment or memory guardrails.

## Verification

- [ ] Primary source or local authority was identified.
- [ ] Source-derived facts are versioned or linked.
- [ ] External advice was translated into DeepTutor concepts.
- [ ] No second authority was introduced.
