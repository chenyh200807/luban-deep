# CLAUDE.md — Claude Code 项目入口

> **Thin wrapper, fat skill 适用于本文件本身**：
> 本项目的工作哲学、概念约束、修改纪律、根因方法论、单一权威门槛，
> 全部沉淀在 [`AGENTS.md`](./AGENTS.md)（27KB）。
> 本文件只做两件事：(1) 把 Claude Code 引向 AGENTS.md；(2) 描述 Claude Code 专属工具链 gstack 怎么用、什么时候不要用。
> 任何与 AGENTS.md 重复的内容，都视为冗余 authority，应该删除。

## Single Source of Truth

**任何任务开始前，Claude Code 必须先读 AGENTS.md 的对应章节。** 不允许跳过。

快速索引（章节号对照 AGENTS.md）：

| 触发条件 | 必读章节 |
|---|---|
| 涉及 Web / BI / 前端 / 浏览器 / 截图 / `next dev` / Playwright | AGENTS §Claude / Codex Web Memory Guardrails |
| 涉及 turn / session / stream / replay / resume / 聊天入口 / TutorBot / trace | `CONTRACT.md` + `contracts/index.yaml` + AGENTS §Contract Discipline |
| 写 PRD / 审 PRD / 判断能力是否落地 / 理解模块方向 | `docs/plan/INDEX.md` + AGENTS §Plan Directory Discipline |
| 任何"新增字段 / router / classifier / interpreter / wrapper / fallback / state"的冲动 | AGENTS §0 Thin Wrappers Fat Skills + §5.6 + §5.7 Single Authority Hard Gate |
| 任何 bug 调查 | AGENTS §5 Fix Root Causes + §5.5 Root-Cause Thinking Method |
| 写代码前 | AGENTS §0.5 First Principles + §1 Think Before Coding + §2 Simplicity First + §2.5 Less Is More |
| 改完代码 | AGENTS §3 Surgical Changes + §4 Goal-Driven Execution |
| 合并到 main | AGENTS §3.5 Main Merge Workflow |
| 决定要不要新建分支 / worktree | AGENTS §3.6 Branch and Worktree Discipline |
| 在阿里云 SSH 上做任何写操作 | AGENTS §3.7 Aliyun SSH Write Boundary（`/root/deeptutor` 是唯一可写边界） |

**AGENTS.md 的硬约束在 Claude Code 上一字不动地生效。** 不要因为换了 agent 平台就放松。

## 与 Codex 的关系

本项目长期由 Codex 主导开发。Codex 沉淀的所有经验都已经写进 AGENTS.md。Claude Code 接手时：

- **不要从零思考**——AGENTS.md 已经回答了大部分"应该怎么做"。
- **不要绕过 AGENTS.md**——AGENTS.md 是单一权威，CLAUDE.md 只是入口。
- **遇到 AGENTS.md 与 CLAUDE.md 冲突，以 AGENTS.md 为准**——CLAUDE.md 出现冲突说明本文件需要删减，不是 AGENTS.md 需要让步。

## 原则的理论源头 (Karpathy Skills 谱系)

AGENTS.md §1-§4 并非凭空创造，**它们是 Andrej Karpathy 提出的四条 LLM 编码原则的本项目化扩展**。原始来源：

- 仓库: <https://github.com/multica-ai/andrej-karpathy-skills>
- 核心文件: `CLAUDE.md` (四原则正文) + `EXAMPLES.md` (对比案例)

谱系对照：

| Karpathy 原则 | 本项目对应章节 | 本项目扩展 |
|---|---|---|
| Think Before Coding | AGENTS §1 | + §0.5 First Principles |
| Simplicity First | AGENTS §2 | + §2.5 Less Is More |
| Surgical Changes | AGENTS §3 | + §3.5 / §3.6 / §3.7 工作流与边界 |
| Goal-Driven Execution | AGENTS §4 | + §5 / §5.5 / §5.6 / §5.7 根因方法论与单一权威门槛 |

**含义**：Claude Code 接到一项任务时，AGENTS.md 已经覆盖了**原则正文 + 自查 gate**（§0.0 Karpathy Gate 列了 4 件事 + 2 个执行中自检）。本节只保留 AGENTS.md §0.0 **没有**显式写的：Core Tradeoff、座右铭、效果度量。

### Core Tradeoff (来自 Karpathy CLAUDE.md)

> **这套体系优先选择「谨慎」而非「速度」。** 琐碎任务可酌情简化，但默认偏 caution。

### 座右铭 (EXAMPLES.md)

> **"Good code is code that solves today's problem simply, not tomorrow's problem prematurely."**

直译：*好代码是简单解决今天的问题，而不是提前解决明天的问题。* 与 AGENTS §2 Simplicity First / §2.5 Less Is More 一致，可在 PR 描述或代码评审时直接引用。

### Success Indicators (Karpathy 原文的效果度量)

本项目工作流是否真正落地了这套原则，看三个长期信号：

1. **diff 多余改动变少**——单次 PR 的脏改动行数下降。
2. **因为过度设计而重写的次数下降**——一开始就走对，不再 "先写一版再砍"。
3. **澄清问题出现在编码之前，而不是之后**——`AskUserQuestion` / 显式假设清单出现的时机前移。

如果这三个指标没在改善，说明 CLAUDE.md / AGENTS.md 里的原则被"知道但没用"，需要在 retro 里复盘到底卡在哪个环节。

## gstack 工具链

gstack 已经安装到 `~/.claude/skills/gstack/`，同时 symlink 到 `~/.codex/skills/gstack/`——**Claude Code 和 Codex 共享同一套 skill 源**，所以两端工作流可以无缝衔接。

升级：`cd ~/.claude/skills/gstack && git pull && ./setup`

### gstack 命令 ↔ AGENTS.md 工作流映射

按 AGENTS.md 的执行阶段组织，只列对本项目（Python/FastAPI 后端 + WebSocket + 小程序）真正有用的命令：

#### 思考与规划（AGENTS §1 / §0.5）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-office-hours` | 头脑风暴 + 产出设计文档 | 落实 §1 Think Before Coding |
| `/gstack-plan-ceo-review` | 用 CEO 视角追问"是不是想得太小了" | 配合 §0.5 First Principles |
| `/gstack-plan-eng-review` | 锁定架构、数据流、边界、测试覆盖 | 在开始编码前落实 §1 + §5.7 |
| `/gstack-autoplan` | 一键跑完 CEO / Eng / Design / DevEx 全套审查 | 大改动前用，可避免反复来回 |

> ⚠️ 任何计划文件最后**必须**挂到 `docs/plan/INDEX.md`（AGENTS §Plan Directory Discipline）。gstack 默认不知道这个规则，要手动遵守。

#### 调试与定位（AGENTS §5 / §5.5 / §5.7）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-investigate` | 四阶段调试：investigate → analyze → hypothesize → implement，铁律 "no fixes without root cause" | 与 §5 Fix Root Causes / §5.5 Root-Cause Thinking Method 完全同构，**优先用它** |

#### 实现与测试（AGENTS §2 / §3 / §4）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-qa-only` | 仅产出 QA 报告，不动代码 | 配合 §4 Goal-Driven Execution，先验收后实现 |
| `/gstack-qa` | QA + 自动修 bug（每个修复独立 commit + 验证） | 慎用：自动 commit 与 §3.6 Branch and Worktree Discipline 的 narrow scope 要求可能冲突，**必须先确认当前分支干净且任务独立** |
| `/gstack-health` | 跑类型检查 / lint / 测试 / 死代码探测，给 0-10 健康分 | 配合 §4，提交前自检 |
| `/gstack-review` | 落地前 PR 审查（SQL 安全 / LLM trust boundary / 条件副作用） | 配合 §3 Surgical Changes，看本次改动是否只改了相关代码 |

#### 持续与续接

| 命令 | 用途 |
|---|---|
| `/gstack-context-save` | 保存当前 git 状态 + 决策 + 未完成工作 |
| `/gstack-context-restore` | 跨会话 / 跨 worktree 续接 |
| `/gstack-learn` | 查看 / 检索 gstack 历史沉淀的学习记录 |

#### 工具类

| 命令 | 用途 |
|---|---|
| `/gstack-codex` | 调 OpenAI Codex CLI 做第二意见 / 对抗审查 / 咨询 |
| `/gstack-make-pdf` | 把 markdown 文档导出成印刷级 PDF |
| `/gstack-upgrade` | 升级 gstack 本身 |

### 必须警惕的 gstack 越权风险

gstack 的某些命令**有默认行为，会与 AGENTS.md 的硬约束冲突**。下列命令使用前必须先确认或避免：

| 命令 | 风险 | 处置 |
|---|---|---|
| `/gstack-ship` | 默认会改/创建 `CHANGELOG.md` 和 `VERSION`，自动 bump 版本号、写 commit、push、开 PR | 本项目**没有** CHANGELOG.md / VERSION 文件，不要让 gstack 自动生成。如果用，**必须明确告诉它不要碰这两个文件**，并复核它的 commit 是否符合 §3.5 Main Merge Workflow |
| `/gstack-land-and-deploy` | 部署阶段会触发远端写操作 | 必须严守 AGENTS §3.7 Aliyun SSH Write Boundary：只允许写 `/root/deeptutor` 内；任何远端 deploy 脚本必须先验证写入根路径 |
| `/gstack-document-release` | 会自动改 README / ARCHITECTURE / CONTRIBUTING / **CLAUDE.md** / CHANGELOG | 与 §3 Surgical Changes 直接冲突——它默认会做"顺手清理"。**禁止在本项目自动跑**；如需更新文档，单独手工处理，scope 收紧 |
| `/gstack-design-*` 系列（design-html / design-shotgun / design-review / design-consultation） | 主要面向 web 前端 UI 设计 | 本项目是后端 API + 小程序，**这些命令几乎都不适用**。小程序 UI 调整走 §4 末段的"微信开发者工具回归"路径，不要套 web 设计工具 |
| `/gstack-setup-deploy` | 写部署配置到 CLAUDE.md | **禁止**——会污染本文件，且本项目部署走自有 runbook |
| `/gstack-skillify` / `/gstack-sync-gbrain` | 生成 / 同步 gbrain skills，可能改 `.gbrain/` 和 `CLAUDE.md` | 仅在明确要建立 gbrain 索引时用；非 gbrain 任务**禁用** |

### gstack 不能违背的本项目硬约束

凡是用 gstack 命令，下面这几条**永远优先**：

1. **概念单一**（AGENTS §Concept Discipline）：gstack 不知道本项目"`TutorBot` 是唯一执行身份"、"`rag` 是唯一知识召回工具"等约束，输出方案时必须人工对照检查。
2. **流式入口唯一**（AGENTS 硬约束）：`/api/v1/ws` 是唯一聊天 WebSocket，gstack 如果建议新增 `/api/v1/mobile/tutorbot/ws/...` 之类的专用路由，**立即拒绝**。
3. **Surgical Changes**（AGENTS §3）：gstack 喜欢"顺手清理 / 顺手重构"，必须人工把 diff 收窄到当前任务直接相关的文件。
4. **Branch & Worktree Discipline**（AGENTS §3.6）：gstack 默认不会问要不要新建分支；按本项目规则，除非明确要求隔离，否则继续在当前分支干。
5. **Aliyun SSH 写边界**（AGENTS §3.7）：任何远端动作的目标路径都要先证明在 `/root/deeptutor` 内。
6. **测试不可跳过**（AGENTS §4）：缺运行环境时先补齐，不许以"环境缺失"为由跳过验证。

## 团队模式 (gstack `--team`) 目前未启用

之所以没启用，是因为它会执行 `git add .claude/ CLAUDE.md && git commit`，会和 AGENTS §3.6 / §3.5 的 narrow-scope commit 原则冲突。

未来若要启用，必须先：
1. 当前分支干净（无未提交改动）
2. 在独立 PR 中完成启用，且 PR 只包含 gstack 启用相关变更
3. 由用户明确授权

## 备忘

- 本文件应该**保持薄**。AGENTS.md 才是项目知识的家。
- 如果发现 CLAUDE.md 出现 AGENTS.md 已有的内容，立即删除 CLAUDE.md 里的副本，不要反过来。
- 如果发现 gstack 的某个命令在本项目长期不可用，更新本文的"越权风险"表格，把它列入禁用清单。
