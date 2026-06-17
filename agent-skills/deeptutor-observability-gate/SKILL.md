---
name: deeptutor-observability-gate
description: "Guides DeepTutor logging, metrics, tracing, release-gate, and daily observability work. Use when adding instrumentation, investigating production behavior, validating release readiness, or interpreting observability runner output."
---

# DeepTutor Observability Gate

Use this skill to make production behavior diagnosable without confusing runner
success with release truth.

## Workflow

1. Define the question the signal must answer.
2. Pick the authority payload: trace, release gate, daily report, observer
   snapshot, turn event log, public health endpoints, or Langfuse.
3. Preserve frozen windows for daily reports, especially Asia/Shanghai natural
   day windows.
4. Separate synthetic, shadow, harness, and real product surfaces.
5. Instrument structured fields that can be joined later; avoid free-text-only
   logs for gate decisions.
6. Verify the telemetry itself by reading the emitted payload, not just script
   exit code.

## Red Flags

- `latest.json` wrapper is treated as enough when inner payload says otherwise.
- Daily report uses rolling 24h when the task requires a frozen local day.
- Trace total duration is confused with main answer generation time.
- Observability output is used to claim WeChat or release closure that it did
  not exercise.

## Verification

- [ ] Signal answers a named operational question.
- [ ] Payload, not only runner exit code, was checked.
- [ ] Synthetic/shadow/real surfaces are separated.
- [ ] Remaining blind spots are listed.
