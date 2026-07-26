---
name: deeptutor-test-verification-gate
description: "Defines DeepTutor test and evidence requirements. Use when implementing behavior, fixing bugs, changing docs or skills, validating release claims, or deciding whether a result is PASS, partial, blocked, or unverified."
---

# DeepTutor Test Verification Gate

## 分层与进化

本 skill 遵循 [agent-skills/README.md · Evolution Protocol](../README.md#evolution-protocol--所有-skill-共用的分层与进化合同)
(canonical,不在此复制)。本 skill 的分层声明:

| 层 | 本 skill 的内容 |
|---|---|
| **L1 内核** | 「测试通过 ≠ 测试有判别力」——新测试必须双向跑(修复版绿 + 还原版红) |
| **L2 嗅觉** | 单轮 LLM 通过可能是运气、全量 pytest 有隔离污染、exit code 不等于 passed |
| **L3 体系** | eval runner 身份四字段、连跑 ≥3 轮、失败文件先单独跑 |
| **L4 实例** | 具体测试路径与当前基线数字 |

**反向查表**:每次相关的真 bug/故障,先回查本 skill 有没有这一条。
「没有」的频率 = 本 skill 的健康度。

Use this skill to make completion evidence-based.

## Workflow

1. Define the claim being tested in one sentence.
2. Choose the lowest sufficient evidence surface:
   - unit or contract test for deterministic logic;
   - integration test for service boundaries;
   - HTTP+WS smoke for chat control-plane behavior;
   - WeChat DevTools or real device for real package UI closure;
   - script/frontmatter/link validation for docs and skills;
   - GitHub Actions `Tests` plus same-SHA `Deploy Gate` for CI green claims;
   - release payload and public endpoints for deployment truth.
3. For bugs, write or identify a reproducer before fixing when practical.
4. Include at least one counterexample when the fix touches regex, fallback,
   routing, classifier, or semantic interpretation.
5. Run the command and preserve the exact command in the report.
6. Classify the result as `pass`, `partial`, `blocked`, or `not_exercised`.

## Eval Runner Identity

Any eval / smoke / QA run that creates accounts, logs in, binds phone numbers,
generates session activity, or writes member read-models must run as an
**eval runner** identity, never as a real-person-shaped account:

- account names use an obvious test prefix: `qa_eval_...`, `eval_...`, or
  `qa_...`; never real names, real phone owners, or production nicknames;
- every path that can carry identity metadata must write
  `account_kind="eval_runner"`, `actor_type="machine"`,
  `created_by="eval_runner"`, `is_internal_test=true`;
- before any such run, export the runner identity env vars:

  ```bash
  export DEEPTUTOR_EVAL_RUNNER_AGENT=claude_code   # or codex / <agent name>
  export DEEPTUTOR_EVAL_RUN_ID="${DEEPTUTOR_EVAL_RUNNER_AGENT}-$(date +%Y%m%d%H%M%S)-$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
  ```

- new test helpers, seed scripts, and agent automation must reuse these fields
  or call `external_auth.ensure_external_auth_user()` /
  `create_external_auth_user()`, which write them automatically;
- eval runner / machine / synthetic / QA accounts must never count into
  `member_console` or BI member totals, new-member, or activity metrics;
- legacy account-name markers are only a fallback for historical pollution;
  new test accounts need explicit machine-identity fields.

## PASS Discipline

Do not report PASS when:

- only a script exited but the target surface was not exercised;
- DevTools `islogin` or `open --project` ran without a page scenario;
- near-real HTTP+WS is being substituted for real WeChat package closure;
- an observability runner succeeded but payload says `ready=false`;
- a `Tests` job passed but the same-SHA `Deploy Gate` failed or has not run;
- a doc or skill change was not validated for frontmatter and links.

## Verification

- [ ] The claim and evidence surface match.
- [ ] Exact commands are recorded.
- [ ] Counterexamples exist for overfit-prone changes.
- [ ] Unexercised surfaces are named explicitly.
