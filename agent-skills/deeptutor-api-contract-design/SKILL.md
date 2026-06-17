---
name: deeptutor-api-contract-design
description: "Guides DeepTutor contract-first API and control-plane changes. Use when modifying REST endpoints, /api/v1/ws, session or turn semantics, trace payloads, schemas, compatibility wrappers, frontend-backend contracts, or public module interfaces."
---

# DeepTutor API Contract Design

Use this skill to avoid creating duplicate control planes or hidden schema
drift.

## Hard Gates

- Read `CONTRACT.md` and `contracts/index.yaml` for chat, turn, session,
  stream, replay, resume, TutorBot, or trace work.
- `/api/v1/ws` remains the only chat WebSocket.
- Stable external boundaries may become contract/schema. Internal convenience
  shapes should not.
- If the change creates, changes, renames, removes, or consumes a stable schema
  or typed object, follow `deeptutor-schema-authority-gate`.
- Wrappers normalize, authorize, delegate, preserve trace, and return.

## Workflow

1. Identify the business fact and authority service.
2. Identify every consumer: backend, Web, WeChat, BI, tests, observability,
   release gate, and trace readers.
3. Prefer additive compatible changes. If removal is required, write migration
   and compatibility boundaries explicitly.
4. Validate input only at trust boundaries. Do not scatter duplicate validators
   between internal functions that share typed contracts.
5. For schema-bearing changes, identify whether the authority is
   `deeptutor/contracts/unified_turn.py`,
   `deeptutor/capabilities/request_contracts.py`,
   `contracts/schema_registry.yaml`, or a domain-specific validator registered
   through the contract guard.
6. Update contract tests registered in `contracts/index.yaml` when protected
   files change.
7. Run `python scripts/check_contract_guard.py <changed files>` when touching
   protected contract domains.

## Red Flags

- A new chat route or mobile-specific WebSocket appears.
- Transport code rewrites canonical answers or trace semantics.
- A compatibility alias participates in execution decisions after edge
  normalization.

## Verification

- [ ] Contract files were read when required.
- [ ] Authority service and wrapper boundary are named.
- [ ] Contract tests or guard checks cover the changed boundary.
- [ ] Consumers and compatibility behavior are documented.
