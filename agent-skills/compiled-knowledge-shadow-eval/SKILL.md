---
name: compiled-knowledge-shadow-eval
description: Use this for DeepTutor tasks about Nexus-like RAG+compiled knowledge, general_knowledge_context, TutorBot compiled knowledge rollout, online shadow eval, wrong chapter risk, source pollution, compiled rerank, KnowQL-like query planning, or deciding whether compiled teaching context can become a system-wide default.
---

# Compiled Knowledge Shadow Eval

Use this skill when evaluating or changing compiled teaching context for TutorBot knowledge conversations. The core rule is: prove wiring, then evaluate quality, then repair compiler pollution, then decide defaults.

## Start Gate

Write this before changing code, docs, rollout flags, or eval scripts:

```text
one business fact:
one authority:
scope:
current default status:
compiled source of truth:
fallback contract:
verification target:
```

If the default status is uncertain, treat system-wide default as `pending`, not `GO`.

## Authority Rules

- Use the system-level compiled knowledge service as authority. Legacy construction-grading modules may be compatibility wrappers only.
- Reuse canonical resolution and compiled bundles. Do not create a second RAG, registry, taxonomy, learner memory, or context schema.
- Keep `/api/v1/ws` as the only streaming entry.
- Compiled context for general TutorBot turns is teaching context only: no official scoring, no answer key, no canonical learner truth, no DB write.
- Low confidence or query/path/source mismatch must fail open to original TutorBot RAG and must not pollute the prompt.

## Workflow

1. Prove pack delivery: confirm `general_knowledge_context` reaches TutorBot metadata and the LLM prompt path before scoring answer quality.
2. Run a 10-question online smoke through `/api/v1/ws` before any 50/100+ run.
3. Run the 50/100+ online shadow only after the smoke shows compiled hits and clean fail-open behavior.
4. Report every metric: compiled hit rate, wrong path rate, source validity, answer improvement/regression, token cost delta, fail-open rate, and non-evaluable transport/service errors.
5. For each compiled hit, check query intent, canonical path, and source text. A lexical match alone is not enough.
6. Convert source pollution into compiler feedback work orders. Runtime rerank gates protect users, but compiler detach/re-anchor repairs the root cause.
7. Decide default only after online metrics and compiler repair evidence are both clean.

## Commands

Use the repo's current script names if they have changed; these are the expected surfaces:

```bash
python scripts/run_tutorbot_compiled_knowledge_online_shadow.py --api-base-url https://test2.yousenjiaoyu.com --limit 10
python scripts/run_tutorbot_compiled_knowledge_online_shadow.py --api-base-url https://test2.yousenjiaoyu.com --limit 50
python scripts/run_compiled_knowledge_source_pollution_audit.py --limit 50
python scripts/check_contract_guard.py
```

For code changes, run focused pytest for the changed service/script plus the relevant `/api/v1/ws` projection tests.

## Report Template

```text
Status:
Online shadow sample:
compiled_hit_rate:
wrong_path_rate:
source_validity:
answer_improvement:
answer_regression:
token_delta:
fail_open_rate:
non_evaluable:
compiler_pollution:
safety_invariants:
default_decision:
remaining blockers:
```

## Common Mistakes

- Calling local TestClient capability GO a production default GO.
- Measuring answer quality before proving compiled metadata reaches the prompt.
- Treating high hit rate as good when the source belongs to the wrong chapter.
- Fixing source pollution only with runtime thresholds instead of compiler work orders.
- Letting a construction-grading wrapper become a second compiled-knowledge authority.
- Forgetting that off-domain and low-confidence queries should use original TutorBot RAG.
