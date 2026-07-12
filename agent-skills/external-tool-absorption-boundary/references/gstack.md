# gstack 在 DeepTutor 的使用权威

> 本文件是 gstack 在 DeepTutor 的**唯一使用权威**，由项目 CLAUDE.md 下沉而来（2026-07-12）。
> 使用任何 `/gstack-*` 命令前先读本文：命令↔工作流映射、越权风险清单、六条硬约束、团队模式禁用状态。

## 安装与升级

gstack 安装在 `~/.claude/skills/gstack/`，同时 symlink 到 `~/.codex/skills/gstack/`——**Claude Code 和 Codex 共享同一套 skill 源**，所以两端工作流可以无缝衔接。

升级：`cd ~/.claude/skills/gstack && git pull && ./setup`

## gstack 命令 ↔ AGENTS.md 工作流映射

按 AGENTS.md 的执行阶段组织，只列对本项目（Python/FastAPI 后端 + WebSocket + 小程序）真正有用的命令：

### 思考与规划（AGENTS §1 / §0.5）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-office-hours` | 头脑风暴 + 产出设计文档 | 落实 §1 Think Before Coding |
| `/gstack-plan-ceo-review` | 用 CEO 视角追问"是不是想得太小了" | 配合 §0.5 First Principles |
| `/gstack-plan-eng-review` | 锁定架构、数据流、边界、测试覆盖 | 在开始编码前落实 §1 + §5.7 |
| `/gstack-autoplan` | 一键跑完 CEO / Eng / Design / DevEx 全套审查 | 大改动前用，可避免反复来回 |

> ⚠️ 任何计划文件最后**必须**挂到 `docs/plan/INDEX.md`（AGENTS §Plan Directory Discipline）。gstack 默认不知道这个规则，要手动遵守。

### 调试与定位（AGENTS §5 / §5.5 / §5.7）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-investigate` | 四阶段调试：investigate → analyze → hypothesize → implement，铁律 "no fixes without root cause" | 与 §5 Fix Root Causes / §5.5 Root-Cause Thinking Method 完全同构，**优先用它** |

### 实现与测试（AGENTS §2 / §3 / §4）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-qa-only` | 仅产出 QA 报告，不动代码 | 配合 §4 Goal-Driven Execution，先验收后实现 |
| `/gstack-qa` | QA + 自动修 bug（每个修复独立 commit + 验证） | 慎用：自动 commit 与 §3.6 Branch and Worktree Discipline 的 narrow scope 要求可能冲突，**必须先确认当前分支干净且任务独立** |
| `/gstack-health` | 跑类型检查 / lint / 测试 / 死代码探测，给 0-10 健康分 | 配合 §4，提交前自检 |
| `/gstack-review` | 落地前 PR 审查（SQL 安全 / LLM trust boundary / 条件副作用） | 配合 §3 Surgical Changes，看本次改动是否只改了相关代码 |

### 持续与续接

| 命令 | 用途 |
|---|---|
| `/gstack-context-save` | 保存当前 git 状态 + 决策 + 未完成工作 |
| `/gstack-context-restore` | 跨会话 / 跨 worktree 续接 |
| `/gstack-learn` | 查看 / 检索 gstack 历史沉淀的学习记录 |

### 工具类

| 命令 | 用途 |
|---|---|
| `/gstack-codex` | 调 OpenAI Codex CLI 做第二意见 / 对抗审查 / 咨询 |
| `/gstack-make-pdf` | 把 markdown 文档导出成印刷级 PDF |
| `/gstack-upgrade` | 升级 gstack 本身 |

## 必须警惕的 gstack 越权风险

gstack 的某些命令**有默认行为，会与 AGENTS.md 的硬约束冲突**。下列命令使用前必须先确认或避免：

| 命令 | 风险 | 处置 |
|---|---|---|
| `/gstack-ship` | 默认会改/创建 `CHANGELOG.md` 和 `VERSION`，自动 bump 版本号、写 commit、push、开 PR | 本项目**没有** CHANGELOG.md / VERSION 文件，不要让 gstack 自动生成。如果用，**必须明确告诉它不要碰这两个文件**，并复核它的 commit 是否符合 §3.5 Main Merge Workflow |
| `/gstack-land-and-deploy` | 部署阶段会触发远端写操作 | 必须严守 AGENTS §3.7 Aliyun SSH Write Boundary：只允许写 `/root/deeptutor` 内；任何远端 deploy 脚本必须先验证写入根路径 |
| `/gstack-document-release` | 会自动改 README / ARCHITECTURE / CONTRIBUTING / **CLAUDE.md** / CHANGELOG | 与 §3 Surgical Changes 直接冲突——它默认会做"顺手清理"。**禁止在本项目自动跑**；如需更新文档，单独手工处理，scope 收紧 |
| `/gstack-design-*` 系列（design-html / design-shotgun / design-review / design-consultation） | 主要面向 web 前端 UI 设计 | 本项目是后端 API + 小程序，**这些命令几乎都不适用**。小程序 UI 调整走 §4 末段的"微信开发者工具回归"路径，不要套 web 设计工具 |
| `/gstack-setup-deploy` | 写部署配置到 CLAUDE.md | **禁止**——会污染 CLAUDE.md，且本项目部署走自有 runbook |
| `/gstack-skillify` / `/gstack-sync-gbrain` | 生成 / 同步 gbrain skills，可能改 `.gbrain/` 和 `CLAUDE.md` | 仅在明确要建立 gbrain 索引时用；非 gbrain 任务**禁用** |

## gstack 不能违背的本项目硬约束

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
