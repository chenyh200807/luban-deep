# Upstream P0 Absorption Status - 2026-05-12

Status: Implemented locally

## Goal

Absorb the useful runtime and stability fixes from `HKUDS/DeepTutor` v1.3.7-v1.3.10 without merging upstream wholesale.

## Non-goals

- Do not merge upstream `main`.
- Do not adopt upstream multi-user/PocketBase auth.
- Do not add Zulip, Matrix E2EE, NVIDIA NIM, Book, Space, or Co-writer surface code in this engineering batch.

## Single Authority

- Runtime config remains under our `config_runtime` contract and `.env`/catalog resolver.
- Chat remains under unified `/api/v1/ws`; no new chat transport is introduced.
- Learner/member identity remains under our existing Supabase/member/Learner State authority, not upstream PocketBase multi-user.

## Absorbed

1. Markdown display hardening from v1.3.10:
   - Unknown pseudo HTML tags such as `<think>` or `<mem>` are escaped outside code spans/fences.
   - Citation linkification now skips fenced and inline code.

2. OpenAI-compatible SDK TLS helper:
   - Added a shared `openai_http_client` helper.
   - `DISABLE_SSL_VERIFY` remains rejected in production.
   - OpenAI SDK providers and TutorBot OpenAI-compatible provider reuse the helper.

3. CORS compatibility aliases:
   - `CORS_ORIGIN` and `CORS_ORIGINS` are accepted as aliases when `DEEPTUTOR_CORS_ALLOW_ORIGINS` is absent.
   - Wildcard is still ignored and production still requires explicit origins.

4. Model/runtime reliability:
   - Context-window resolution now supports large model defaults and caps explicit windows at `1_000_000`.
   - Qwen-family vision model detection is enabled.
   - DeepSeek v4 pro pricing is added to token/cost tables.

5. Runtime extra headers:
   - Agentic chat now preserves resolved `extra_headers` for OpenAI SDK clients and explicit LLM calls.

## Deferred

- Upstream multi-user/auth/admin grants: product/architecture review only; direct code copy would compete with our member, wallet, BI, and Learner State authorities.
- Zulip channel, Matrix E2EE dependency split, NVIDIA NIM provider: not on the current Luban/DeepTutor product path.
- `deeptutor start` CLI: useful developer UX but lower priority than runtime correctness.

## Verification

- `node --experimental-strip-types --test tests/markdown-display.test.ts`
- `node --experimental-strip-types --test tests/markdown-display.test.ts && npx tsc --noEmit --pretty false && npx eslint lib/markdown-display.ts tests/markdown-display.test.ts`
- `python -m pytest tests/api/test_main_entrypoints.py::test_cors_accepts_upstream_origin_aliases_without_wildcard tests/services/session/test_context_builder.py::test_context_builder_uses_large_model_default_when_context_missing tests/services/session/test_context_builder.py::test_context_builder_caps_explicit_large_context_window tests/services/llm/test_openai_http_client.py tests/agents/chat/test_agentic_parallel_tools.py::test_agentic_pipeline_keeps_runtime_extra_headers tests/services/llm/test_capabilities.py::test_qwen_model_family_supports_vision tests/agents/research/test_token_tracker_pricing.py -q`
- `python -m pytest tests/api/test_main_entrypoints.py::test_cors_defaults_to_safe_origins_in_non_production tests/api/test_main_entrypoints.py::test_cors_uses_env_allowlist_and_ignores_wildcard tests/api/test_main_entrypoints.py::test_cors_accepts_upstream_origin_aliases_without_wildcard tests/services/session/test_context_builder.py tests/services/llm/test_openai_http_client.py tests/services/llm/test_capabilities.py tests/tutorbot/test_provider_observability.py::test_dashscope_minimal_reasoning_disables_thinking_without_invalid_reasoning_effort tests/agents/chat/test_agentic_parallel_tools.py tests/agents/research/test_token_tracker_pricing.py -q`
- `git ls-files -m -o --exclude-standard | xargs python scripts/check_contract_guard.py`
- `python -m compileall -q deeptutor/api deeptutor/agents/chat deeptutor/services/llm deeptutor/services/session deeptutor/tutorbot/providers deeptutor/agents/research deeptutor/agents/solve deeptutor/logging`
- `git diff --check`
