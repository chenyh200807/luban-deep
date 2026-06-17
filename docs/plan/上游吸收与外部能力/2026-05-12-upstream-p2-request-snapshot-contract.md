# Upstream P2 Request Snapshot Contract Comparison

Status: Draft / implementation target

## Scope

This document covers the third upstream absorption batch:

- request snapshot
- `messages.metadata_json`

It explicitly does not cover learner profile, learner summary, learner progress, learner goals, memory events, heartbeat, or bot overlay writeback.

## Contract Reading

Relevant contracts:

- `CONTRACT.md`
- `contracts/index.yaml`
- `contracts/turn.md`
- `contracts/learner-state.md`

Contract conclusion:

- Turn/session request context belongs to `TurnRuntimeManager + SQLiteSessionStore`.
- Long-term learner facts belong to learner-state services and Supabase learner-state tables.
- A request snapshot is a replay/debug/read-model fact for a single user message. It is not a learner fact.

## Single Authority Gate

### One Business Fact

For each persisted user message, the system should preserve the normalized inbound request context needed to explain or replay that message:

- raw user content
- selected capability
- requested tools and knowledge bases
- language
- public request config
- attachment descriptors
- optional references such as notebook/history/question/book references
- optional runtime-internal requested skills, memory references, or model selection hints when they enter through trusted internal adapters

### One Authority

`SQLiteSessionStore.messages.metadata_json` is the only local authority for this per-message request snapshot.

It is written by `TurnRuntimeManager` when the user message is materialized. Readers access it through the existing session/message read model.

### Competing Authorities To Avoid

The snapshot must not compete with:

- `learner_summaries`
- `learner_memory_events`
- `user_profiles`
- `user_stats`
- `user_goals`
- bot learner overlay
- TutorBot workspace memory
- stream event metadata
- Langfuse trace metadata

Trace metadata may observe the request; it is not the replay authority. Learner state may later receive structured writeback through its own pipeline; it must not be inferred directly from this snapshot.

### Canonical Path

1. `/api/v1/ws` start-turn payload enters `TurnRuntimeManager`.
2. Runtime normalizes capability, config, bot defaults, attachments, and references.
3. Runtime builds a sanitized `request_snapshot`.
4. Runtime persists the user message through `SQLiteSessionStore.add_message(..., metadata={...})`.
5. `SQLiteSessionStore` stores metadata in `messages.metadata_json`.
6. Session detail/list readers expose message metadata as read-model data.

### Delete Or Demote

This absorption deliberately does not add:

- a learner-state write
- a second request history table
- a new WebSocket route
- a new public turn schema field
- a second TutorBot identity or grounding mode

## Data Shape

`messages.metadata_json` stores an object. For this batch the only required key is:

```json
{
  "request_snapshot": {
    "content": "user-visible input",
    "capability": "chat",
    "enabledTools": ["rag"],
    "knowledgeBases": ["construction-exam"],
    "language": "zh",
    "config": {},
    "attachments": [],
    "notebookReferences": [],
    "historyReferences": [],
    "questionNotebookReferences": [],
    "bookReferences": [],
    "skills": [],
    "memoryReferences": [],
    "llmSelection": {}
  }
}
```

Empty optional fields should be omitted to keep the read model compact.

Attachment descriptors must not persist raw base64 payloads inside `request_snapshot`.
Sensitive keys such as API keys, tokens, authorization headers, passwords, secrets,
base64 payloads, and raw data fields must be redacted before persistence.
`skills`, `memoryReferences`, and `llmSelection` are not public `/api/v1/ws`
schema fields in this batch; they may only appear when a trusted internal adapter
passes them to the runtime. This keeps the public turn contract unchanged.

## Acceptance Criteria

- User message metadata is persisted and returned by `get_session_with_messages`.
- Existing message rows are migrated with `metadata_json = '{}'`.
- `TurnRuntimeManager` writes `request_snapshot` when persisting the user message.
- Base64 attachment content is stripped from the request snapshot.
- Sensitive config and model-selection fields are redacted from the request snapshot.
- No learner-state service or learner-state table is written by this feature.
- Targeted tests cover store metadata persistence and turn-runtime snapshot materialization.
