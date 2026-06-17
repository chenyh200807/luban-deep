---
name: deeptutor-security-hardening-gate
description: "Applies DeepTutor security hardening. Use when changing authentication, authorization, user input, file paths, subprocesses, secrets, third-party integrations, payment/billing, SSH, deployment, or production data boundaries."
---

# DeepTutor Security Hardening Gate

Use this skill when a change touches trust boundaries.

## Workflow

1. Identify untrusted inputs: user text, frontend payloads, third-party API
   responses, files, environment, logs, LLM output, and remote host state.
2. Validate at system edges. Keep internal typed boundaries simple.
3. Keep secrets out of commands, logs, screenshots, reports, and commits.
4. For payment/billing, treat `wallet_ledger` as authority and require
   verified callback plus idempotent crediting.
5. For Aliyun SSH writes, only write inside `/root/deeptutor`; all other paths
   are read-only observation surfaces unless the user gives new explicit
   authorization.
6. Prefer deny-by-default for production writes and irreversible actions.

## Red Flags

- Raw environment dumps, launchctl output, cookies, tokens, or rollout JSONL are
  pasted into reports.
- LLM or RAG output is trusted as policy, score, payment, learner truth, or
  command input.
- A remote script writes outside `/root/deeptutor`.
- Dev/mock login leaks into production authority.

## Verification

- [ ] Trust boundaries and untrusted inputs are named.
- [ ] Secret-safe reporting was preserved.
- [ ] Production writes and remote paths are bounded.
- [ ] Security tests or focused review cover the changed path.
