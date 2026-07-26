# DeepTutor Agent Skills

These skills capture repeatable developer-agent workflows for DeepTutor.
They are not TutorBot runtime skills and must not be loaded by the product
skill loader under `deeptutor/tutorbot/skills/`.

Use them when planning, debugging, reviewing, or QA'ing DeepTutor work:

- `deeptutor-engineering-lifecycle-gate`: DeepTutor-local translation of
  general agent engineering lifecycle skills. Use it as the dispatcher for
  non-trivial implementation, repair, review, documentation, or launch work
  before selecting narrower skills.
- `deeptutor-spec-plan-gate`: spec and implementation-plan workflow for
  roadmap, PRD, architecture, and capability-status work under `docs/plan/`.
- `deeptutor-source-grounded-change`: source-driven workflow for framework,
  library, API, or external-reference changes where stale assumptions are risky.
- `deeptutor-storm-source-inspection`: STORM/Co-STORM-like multi-perspective
  source inspection producing candidate/review-only findings with provenance,
  without runtime, scoring, RAG, or learner-truth authority drift.
- `deeptutor-incremental-implementation`: thin vertical-slice implementation
  workflow for multi-file DeepTutor changes.
- `deeptutor-test-verification-gate`: test-first and evidence-first workflow
  for behavior changes, bug fixes, and doc/skill validations.
- `deeptutor-ci-runtime-fix-gate`: CI/runtime failure workflow for GitHub
  Actions, route smoke, contract guard, detect-secrets, and same-SHA deploy
  gate failures.
- `deeptutor-api-contract-design`: contract-first API and control-plane
  boundary workflow for REST, WebSocket, trace, session, and schema changes.
- `deeptutor-schema-authority-gate`: schema and registry authority workflow for
  stable external boundaries, typed objects, event payloads, view models, and
  machine-checkable schema changes.
- `deeptutor-resource-registry-gate`: register-before-use workflow for
  foundational resources such as DB connections, env vars, feature flags,
  credentials, providers, long-running processes, routes, model authority, and
  governance scanner wiring.
- `deeptutor-web-bi-frontend-gate`: Web/BI/frontend workflow with memory
  preflight and no agent-hosted long-lived Next dev server.
- `deeptutor-authority-debugging`: root-cause workflow for authority, state,
  route, follow-up, refusal, and terminal-truth bugs.
- `tutorbot-student-army-eval-loop`: proactively pressure-tests TutorBot on
  test2 with a multi-persona student army (long conversations), then runs the
  discover→root-cause→fix→verify→sediment loop. Continuously maintained: each
  run appends new bug patterns and ironclad diagnosis/fix rules to the skill.
- `wechat-tutorbot-real-entry-qa`: QA workflow for the real WeChat TutorBot
  path, with explicit evidence-surface boundaries.
- `compiled-knowledge-shadow-eval`: QA and rollout workflow for Nexus-like
  RAG+compiled TutorBot knowledge conversations, source pollution feedback,
  and system-wide default decisions.
- `anti-overfit-repair-review`: review workflow for regex, fallback,
  classifier, and special-case repairs.
- `deeptutor-evidence-discipline`: evidence-to-claim alignment workflow. Use it
  before claiming done/fixed/verified/deployed/checked/ready, before signing off
  an audit, verdict, release, or forensics result, and when writing a subagent
  prompt that should pre-close those escape routes.
- `deeptutor-review-quality-gate`: five-axis review workflow for self-review,
  agent code review, and pre-merge assessment.
- `deeptutor-code-simplification`: behavior-preserving simplification workflow
  for recently changed code that is heavier than necessary.
- `deeptutor-security-hardening-gate`: security review workflow for auth,
  untrusted input, secrets, external integrations, and production boundaries.
- `deeptutor-observability-gate`: logging, metrics, trace, and release-gate
  evidence workflow for production-visible behavior.
- `deeptutor-docs-adr-gate`: documentation and ADR workflow that keeps
  `AGENTS.md`, `CONTRACT.md`, and `docs/plan/INDEX.md` as the authority map.
- `deeptutor-git-workflow-gate`: branch, dirty-worktree, staging, commit,
  merge, and worktree discipline for DeepTutor.
- `deeptutor-release-launch-gate`: release, merge-to-main, push, Aliyun deploy,
  rollback, and post-launch verification workflow.
- `luban-rich-leaf-compiler`: RichLeafArtifact / 2026 source compilation /
  review queue / runtime supply candidate workflow.
- `luban-okf-context`: AI-only OKF source-navigation workflow for data asset,
  topic coverage, exam/source-evidence, and candidate/runtime boundary questions.
- `luban-diagram-microlesson`: 图解微课卡 authoring / 确定性 renderer / 一屏一重点
  翻页 deck UX / 单一权威边界 / web-view 沙盒 / 零依赖 CDP 验收 workflow.
- `luban-case-answer-layer`: 案例题作答训练(采分点可写化、五维框架、AI 批改
  训练闭环),依附已 signed pack 加层,不造第二 authority.
- `luban-learning-pack-factory`: 鲁班"教研测一体"学习包批量生产总纲与质量闭环;
  造法细节调用 `luban-diagram-microlesson`,本 skill 不重复它.
- `external-tool-absorption-boundary`: adopting/upgrading a plugin, marketplace skill,
  gstack, CLI, MCP, or shared hook — audit + neutralize opinionated defaults
  (auto-commit, CLAUDE.md injection, blocking hooks, telemetry) so they never
  override single authority, branch discipline, or register-before-use.

Keep `AGENTS.md` as the hard-gate index. Put long procedures and reusable
checklists here so project entry files stay thin.

## Invocation Contract

These are repo-local workflow skills. In DeepTutor, normal invocation comes from
`AGENTS.md` routing plus direct reads of `agent-skills/<name>/SKILL.md`; they are
not product TutorBot runtime skills.

Expected trigger rate:

- near-always for non-trivial engineering work: implementation, repair, review,
  plan, docs, tests, release, Web/BI, WeChat, Aliyun, observability, security,
  or external-source adoption;
- optional for tiny self-contained answers, one-line shell checks, translations,
  or purely conversational clarification;
- never as a generic external authority that overrides `AGENTS.md`,
  `CONTRACT.md`, `contracts/index.yaml`, or `docs/plan/INDEX.md`.

Run this after adding, renaming, or editing skill routing:

```bash
python agent-skills/scripts/validate_agent_skills.py
```

`catalog.yaml` is the machine-checkable inventory for these workflow skills. It
is deliberately not a loader and not an authority for descriptions; `SKILL.md`
frontmatter remains the trigger source, while `AGENTS.md` remains the hard-gate
index.

To audit whether skills were actually invoked in recent Codex work, run:

```bash
python agent-skills/scripts/audit_skill_usage.py --hours 1
python agent-skills/scripts/audit_skill_usage.py --hours 1 --repo-only
```

The usage audit only proves that `SKILL.md` files were read through recorded
tool calls. It cannot prove that every instruction was followed; use review and
verification evidence for that stronger claim.

## Lifecycle Map

The upstream `addyosmani/agent-skills` lifecycle is absorbed as this local map:

- Define and plan: `deeptutor-spec-plan-gate`
- Ground in sources: `deeptutor-source-grounded-change`,
  `deeptutor-storm-source-inspection`
- Build: `deeptutor-incremental-implementation`,
  `deeptutor-api-contract-design`, `deeptutor-schema-authority-gate`,
  `deeptutor-resource-registry-gate`, `deeptutor-web-bi-frontend-gate`,
  `luban-okf-context`, `luban-diagram-microlesson`,
  `luban-case-answer-layer`, `luban-learning-pack-factory`
- Verify: `deeptutor-test-verification-gate`,
  `deeptutor-evidence-discipline`,
  `deeptutor-ci-runtime-fix-gate`,
  `tutorbot-student-army-eval-loop`,
  `wechat-tutorbot-real-entry-qa`, `compiled-knowledge-shadow-eval`,
  `luban-rich-leaf-compiler`
- Debug and repair: `deeptutor-authority-debugging`,
  `anti-overfit-repair-review`
- Review and simplify: `deeptutor-review-quality-gate`,
  `deeptutor-code-simplification`, `deeptutor-security-hardening-gate`
- Document and observe: `deeptutor-docs-adr-gate`,
  `deeptutor-observability-gate`
- Version and ship: `deeptutor-git-workflow-gate`,
  `deeptutor-release-launch-gate`
- Tooling and absorption: `external-tool-absorption-boundary`

## Evolution Protocol — 所有 skill 共用的分层与进化合同

**本节是 canonical。** 各 skill 只声明「我的哪些内容住哪一层」,不复制本协议正文。
(2026-07-26 owner 立:「让他们持续进化,而且要分层,哪些是核心层不变的内核,
哪些是事务性的可以不断优化的」。)

### 目标不是「预知一切」

任何方法论 skill 的目标**不是**在动手前预知全部问题。那个起点是错的:理论上不可能、
成本发散,而且**最危险的是它制造虚假安全感**——一个自称能预知的系统,比一个承认自己会漏的
系统更危险,因为前者让人停止建检测机制。

真实目标是**分层拦截**:嗅觉挡低级常识问题(~90%),算子挡结构性问题,
**体系负责定期识别剩下的**。**遇到问题不可怕,没有定期识别问题的体系才可怕。**

### 分层判据 = 失效条件(客观),不是重要性(主观)

写下任何一条知识时先问「**它什么时候会失效**」,答案决定它住哪层:

| 层 | 失效条件 | 尺度 | 改动纪律 |
|---|---|---|---|
| **L0 价值观** | 永不(三大原则,住 AGENTS.md) | — | 不在 skill 里改 |
| **L1 内核** | 领域的物理/结构本质改变 | 十年 | **改需论证**:给出一个现有内核答不出的真实案例 |
| **L2 嗅觉** | 语言/框架/平台惯用法改变 | 年 | **持续增长**,每次踩坑追加一条 |
| **L3 体系** | 团队规模/工具链改变 | 年 | 持续调 |
| **L4 实例** | 本 repo 代码改变 | 周/月 | **过期即删,不留墓碑** |

### 触发条件(按事件,不按时间——按时间会漂)

| 触发 | 更新哪层 | 动作 |
|---|---|---|
| 踩了一个「看一眼就该发现」的坑 | **L2** | 追加一行:形状 → 疑心 → 一句话验证 |
| 出现某个内核答不出的真实案例 | **L1** | 先论证,通过才可增/改 |
| 本仓代码变了,某条实例失效 | **L4** | 直接删 |
| 反向查表落空(见下) | **L3** | 该层重新侦察 |
| 同一条被引用超过 3 次仍被违反 | **L3** | 不是知识问题,是门缺失——考虑加 gate |

### 反向查表 — 唯一的健康度量

每次真 bug / 生产故障,**第一件事回查相关 skill 有没有这一条**:

- **有** → 不是知识缺口,是执行问题(考虑加门,或该条写得不够扎眼)
- **没有** → 知识缺口,按上表定位补哪层

**统计「没有」的出现频率 = 这套 skill 体系的健康度。** 它是唯一可证伪的指标——
比「我们有 30 个 skill」有意义得多。

### 防层错位

- 新条目**默认进 L2 或 L4**。升到 L1 需要证明它能解释**至少 2 个不同来源**的案例。
- **L1 被频繁修改 = 危险信号**,说明当初提炼错了层(把实例当成了内核)。
- 症状:如果一条知识的写法是「遇到 X 时要 Y」,它大概率是 L4 实例而非 L1 内核。
  内核的写法是**问句**,不是 if-then。

### 防膨胀

- **L4 只增不减 = 腐烂。** 每次战役后扫一遍,失效的直接删。
- L2 超过约 20 条时按命中频率排序,低频的下沉到 `references/`。
- 删掉的东西进 git 历史,不在文件里留「已废弃」注释。

### L3 体系层 · 怎么「定期识别问题」

体系不是"更多的门"。门是**预防**(挡已知形态),体系是**发现**(捞未知形态)。
两者的比例应该随系统成熟度倾斜向后者——因为已知形态会被门挡住,剩下的都是没见过的。

**三个动作,按触发条件跑,不按日历跑:**

| 动作 | 触发 | 产物 | 现状 |
|---|---|---|---|
| **层扫描** | 该层有新指纹表时 / 改动落在该层时 | 命中清单(下界,含已知误差) | `scripts/scan_asyncio_blocking.py`(asyncio 层) |
| **盲区侦察** | 引入新技术层 / 反向查表落空 / 连续 3 次交付无侦察 | 该层的「反模式 × 指纹 × 本仓命中」表 | `deeptutor-evidence-discipline/references/blindspot-*.md` |
| **反向查表** | **每次真 bug / 生产故障,第一件事** | 判定「知识缺口」还是「执行问题」 | 人工,见上文 |

**盲区侦察必须用异源模型。** 2026-07-26 实证:证伪主控方案的是异源实测;
同源模型与主控共享同一套盲区,扫不出来。这不是偏好,是这套机制能不能工作的前提。

**为什么现在不建「一键体检」聚合脚本**:目前只有 asyncio 一个层有指纹表。
聚合 1 个东西不产生价值,只产生一层间接。**等有 3 个层的扫描器时再聚合**——
在此之前建聚合器就是「为以后可能用预留抽象」,违反 less is more。

**下一层侦察候选**(按实际风险,已完成的划掉):
1. ~~asyncio / 并发~~ ✅ 2026-07-26(16 项)
2. **数据库事务与锁** ← 已部分展开,发现 10/11 库 `busy_timeout=0`、`bi_service` 吞 BUSY
3. 流式传输 / SSE(前科:200 OK 但流中断)
4. 缓存一致性
5. 时区与时间语义

## External Skill Absorption Boundary

External skill packs such as `addyosmani/agent-skills` are upstream workflow
material, not DeepTutor authority. Learn their process shape, then translate it
into local constraints:

- keep `AGENTS.md`, `CONTRACT.md`, `contracts/index.yaml`, and
  `contracts/schema_registry.yaml` / `docs/plan/INDEX.md` as the authority
  chain;
- do not install a generic slash-command lifecycle that can bypass DeepTutor
  release, WeChat, Aliyun, or memory guardrails;
- prefer one local dispatcher plus domain skills over copying a full external
  skill tree;
- preserve the useful mechanics: clear trigger descriptions, stepwise workflow,
  common rationalizations, red flags, and evidence-based verification.

When a future external skill looks useful, first run
`deeptutor-engineering-lifecycle-gate`, then either map it to an existing local
skill or create a DeepTutor-specific skill with an explicit authority boundary.
