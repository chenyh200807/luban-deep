# Upstream DeepTutor Ability Absorption Status

Date: 2026-05-03
Upstream checked: HKUDS/DeepTutor `main` at `eff1c0df` / v1.3.6.

## Goal

Keep our DeepTutor fork close enough to upstream that useful capabilities can be
used in our product, without importing duplicate concepts, unstable product
surfaces, or a second authority for chat/session/model state.

## Current Status

Implemented engineering absorption:

- Batch 1: RAG query authority, local embedding placeholder key support,
  thinking cleanup, TutorBot non-string content normalization, IME/autoscroll.
- Batch 2: knowledge ready/stale status hardening, invalid vector validation,
  re-index API, document extractor, attachment store.
- Batch 3: request snapshot and `messages.metadata_json`, with learner state
  explicitly excluded from the snapshot authority.
- Batch 4: Book / Space / Co-writer / TutorBot channels kept in product-review
  intake, not copied into engineering.
- Batch 5 from upstream v1.3.6: request-scoped LLM model selection via catalog
  IDs, `/api/v1/settings/llm-options`, unified turn `llm_selection`, scoped LLM
  config activation, trace/snapshot metadata, and a main workspace ModelSelector.

Not absorbed directly:

- OpenAI Responses `max_completion_tokens` mapping: our current runtime does not
  have upstream's `provider_core/openai_responses` path, so there is no direct
  local code path to patch now.
- Upstream skill editor validation/modal background: our local tree does not
  carry `web/components/space/SkillsSection.tsx`, so this is not applicable.
- Upstream multi-version RAG no-op validation: our local re-index path rebuilds
  the canonical `llamaindex_storage`; full versioned index adoption remains a
  later architecture decision, not a hidden mirror-state import.

## Authority

The LLM selection authority remains the server-side model catalog:

- Client sends only `profile_id` and `model_id`.
- Provider secret, endpoint, binding, headers, and model metadata stay in the
  catalog and provider runtime.
- A turn can activate a scoped LLM config for the current async context, but it
  does not mutate global catalog or `.env`.
- Request snapshot/session preferences may store the selected IDs for audit and
  replay hints only.

## Verification

Fresh verification run in the upstream absorption worktree:

- `python -m pytest ...` targeted absorption suite: `265 passed, 5 warnings`.
- `python scripts/check_contract_guard.py $(git diff --name-only)`: passed.
- `python -m compileall -q deeptutor/api deeptutor/contracts deeptutor/services deeptutor/tools deeptutor/tutorbot`: passed.
- `npx eslint 'app/(workspace)/page.tsx' 'context/UnifiedChatContext.tsx' 'components/chat/home/ChatComposer.tsx' 'components/chat/home/ModelSelector.tsx' 'lib/llm-options.ts' 'lib/unified-ws.ts'`: passed.
- `git diff --check`: passed.
- `python -m pip check`: no broken requirements.
