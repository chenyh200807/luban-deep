# gstack 在 DeepTutor 的使用权威

> 本文件是 gstack 在 DeepTutor 的**唯一使用权威**，由项目 CLAUDE.md 下沉而来（2026-07-12）。
> 使用任何 `/gstack-*` 命令前先读本文：命令↔工作流映射、越权风险清单、六条硬约束、团队模式禁用状态。

## 安装与升级

gstack 在 Claude Code 侧安装在 `~/.claude/skills/gstack/`（git repo + setup 生成的 gstack-* 转发目录）；Codex 侧是**另一份独立 clone**（`~/.gstack/repos/gstack/`，经 `~/.codex/skills/` 下的逐 skill 符号链接接入），两侧并非同一份源，升级需各自处理。

升级：`cd ~/.claude/skills/gstack && git pull && ./setup`

> **升级后必须重跑排除清单**：gstack `./setup`（含 `/gstack-upgrade`）会无条件重建全部 gstack-* 转发目录，没有原生排除机制。本机维护了排除清单 `~/.claude/skills/gstack-prune.list`（iOS/design/setup-deploy/skillify/sync-gbrain 等 12 个对本项目永不适用的 skill），每次升级或重跑 setup / `gstack-relink` / `gstack-config set skill_prefix` 后执行一次 `~/.claude/skills/gstack-prune.sh`（幂等）。Codex 侧同类不适用 skill 的符号链接已于 2026-07-12 移除。

## gstack 命令 ↔ AGENTS.md 工作流映射

按 AGENTS.md 的执行阶段组织，只列对本项目（Python/FastAPI 后端 + WebSocket + 小程序）真正有用的命令：

### 思考与规划（AGENTS Principles：Think before coding / First principles）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-office-hours` | 头脑风暴 + 产出设计文档 | 落实 Principles 的 Think before coding |
| `/gstack-plan-ceo-review` | 用 CEO 视角追问"是不是想得太小了" | 配合 Principles 的 First principles |
| `/gstack-plan-eng-review` | 锁定架构、数据流、边界、测试覆盖 | 在开始编码前落实 Think before coding + Single Authority Hard Gate |
| `/gstack-autoplan` | 一键跑完 CEO / Eng / Design / DevEx 全套审查 | 大改动前用，可避免反复来回 |

> ⚠️ 任何计划文件最后**必须**挂到 `docs/plan/INDEX.md`（AGENTS Hard Invariants：计划纪律）。gstack 默认不知道这个规则，要手动遵守。

### 调试与定位（AGENTS Principles：Fix root causes / Single Authority Hard Gate；细则见 deeptutor-authority-debugging）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-investigate` | 四阶段调试：investigate → analyze → hypothesize → implement，铁律 "no fixes without root cause" | 与 AGENTS 的 Fix root causes 原则及 deeptutor-authority-debugging 根因工作流完全同构，**优先用它** |

### 实现与测试（AGENTS Principles：Simplicity first / Surgical changes / Goal-driven）

| 命令 | 用途 | 与 AGENTS.md 的关系 |
|---|---|---|
| `/gstack-qa-only` | 仅产出 QA 报告，不动代码 | 配合 Goal-driven execution，先验收后实现 |
| `/gstack-qa` | QA + 自动修 bug（每个修复独立 commit + 验证） | 慎用：自动 commit 与 AGENTS Hard Invariants git 纪律的 narrow scope 要求可能冲突，**必须先确认当前分支干净且任务独立** |
| `/gstack-health` | 跑类型检查 / lint / 测试 / 死代码探测，给 0-10 健康分 | 配合 Goal-driven execution，提交前自检 |
| `/gstack-review` | 落地前 PR 审查（SQL 安全 / LLM trust boundary / 条件副作用） | 配合 Surgical changes，看本次改动是否只改了相关代码 |

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
| `/gstack-ship` | 默认会改/创建 `CHANGELOG.md` 和 `VERSION`，自动 bump 版本号、写 commit、push、开 PR | 本项目**没有** CHANGELOG.md / VERSION 文件，不要让 gstack 自动生成。如果用，**必须明确告诉它不要碰这两个文件**，并复核它的 commit 是否符合 AGENTS Main Merge Workflow |
| `/gstack-land-and-deploy` | 部署阶段会触发远端写操作 | 必须严守 AGENTS Aliyun SSH Write Boundary（原 §3.7）：只允许写 `/root/deeptutor` 内；任何远端 deploy 脚本必须先验证写入根路径 |
| `/gstack-document-release` | 会自动改 README / ARCHITECTURE / CONTRIBUTING / **CLAUDE.md** / CHANGELOG | 与 Surgical changes 原则直接冲突——它默认会做"顺手清理"。**禁止在本项目自动跑**；如需更新文档，单独手工处理，scope 收紧 |
| `/gstack-design-*` 系列（design-html / design-shotgun / design-review / design-consultation） | 主要面向 web 前端 UI 设计 | 本项目是后端 API + 小程序，**这些命令几乎都不适用**。小程序 UI 调整走 AGENTS 测试铁律的"微信开发者工具回归"路径，不要套 web 设计工具 |
| `/gstack-setup-deploy` | 写部署配置到 CLAUDE.md | **禁止**——会污染 CLAUDE.md，且本项目部署走自有 runbook |
| `/gstack-skillify` / `/gstack-sync-gbrain` | 生成 / 同步 gbrain skills，可能改 `.gbrain/` 和 `CLAUDE.md` | 仅在明确要建立 gbrain 索引时用；非 gbrain 任务**禁用** |

## gstack 不能违背的本项目硬约束

凡是用 gstack 命令，下面这几条**永远优先**：

1. **概念单一**（AGENTS Concept Discipline）：gstack 不知道本项目"`TutorBot` 是唯一执行身份"、"`rag` 是唯一知识召回工具"等约束，输出方案时必须人工对照检查。
2. **流式入口唯一**（AGENTS 硬约束）：`/api/v1/ws` 是唯一聊天 WebSocket，gstack 如果建议新增 `/api/v1/mobile/tutorbot/ws/...` 之类的专用路由，**立即拒绝**。
3. **Surgical Changes**（AGENTS Principles：Surgical changes）：gstack 喜欢"顺手清理 / 顺手重构"，必须人工把 diff 收窄到当前任务直接相关的文件。
4. **Branch & Worktree Discipline**（AGENTS Hard Invariants：git 纪律）：gstack 默认不会问要不要新建分支；按本项目规则，除非明确要求隔离，否则继续在当前分支干。
5. **Aliyun SSH 写边界**（AGENTS Aliyun Write Boundary，原 §3.7）：任何远端动作的目标路径都要先证明在 `/root/deeptutor` 内。
6. **测试不可跳过**（AGENTS Hard Invariants：测试不可跳过）：缺运行环境时先补齐，不许以"环境缺失"为由跳过验证。

## 团队模式 (gstack `--team`) 目前未启用

之所以没启用，是因为它会执行 `git add .claude/ CLAUDE.md && git commit`，会和 AGENTS git 纪律 / Main Merge Workflow 的 narrow-scope commit 原则冲突。

未来若要启用，必须先：

1. 当前分支干净（无未提交改动）
2. 在独立 PR 中完成启用，且 PR 只包含 gstack 启用相关变更
3. 由用户明确授权
