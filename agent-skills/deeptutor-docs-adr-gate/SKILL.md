---
name: deeptutor-docs-adr-gate
description: "Controls DeepTutor documentation and ADR updates. Use when changing AGENTS.md, CLAUDE.md, CONTRACT.md, contracts/index.yaml, docs/plan files, runbooks, README-like files, or recording architecture decisions."
---

# DeepTutor Docs ADR Gate

Use this skill to keep documentation as a single authority map rather than a
pile of duplicate rules.

## Workflow

1. Identify the doc authority:
   - `AGENTS.md` for project rules;
   - `CONTRACT.md` and `contracts/index.yaml` for stable control-plane
     contracts;
   - `docs/plan/INDEX.md` for plan lanes;
   - runbooks for operational procedures;
   - local `agent-skills/` for long agent workflows.
2. Update the thinnest entry point and put long procedures in the right skill or
   plan file.
3. Avoid duplicating the same rule in multiple files. Cross-link instead.
4. If a plan file changes location or status, update `docs/plan/INDEX.md`.
5. Validate links, frontmatter, and wording boundaries.

## Red Flags

- `CLAUDE.md` restates rules already in `AGENTS.md`.
- New docs claim production, release, or WeChat closure without evidence.
- A stable contract is described only in prose but not indexed.
- Agent workflow skills are moved into product runtime skills.

## Verification

- [ ] The correct doc authority was updated.
- [ ] Indexes and links are current.
- [ ] No duplicate rule source was introduced.
- [ ] Claims are conservative and evidence-scoped.
