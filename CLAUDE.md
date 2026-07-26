# CLAUDE.md — Claude Code 项目入口

> **本文件是 thin wrapper**:项目的硬约束、启动门、原则、路由全部在
> [`AGENTS.md`](./AGENTS.md)。本文件只做一件事:把 Claude Code 引向 AGENTS.md。
> 任何与 AGENTS.md 重复的内容都是冗余 authority,应当删除。
> 遇到 CLAUDE.md 与 AGENTS.md 冲突,以 AGENTS.md 为准。

## Single Source of Truth

**任何任务开始前,先读 [AGENTS.md](./AGENTS.md) 的对应章节。** 快速索引:

| 触发条件 | 必读 |
|---|---|
| 任何非平凡任务(改代码/状态/路由/测试/发布/文档治理) | AGENTS §Start Gate(含 blind spots 必填)→ `deeptutor-engineering-lifecycle-gate` |
| 任何"完成/修好/已验证/已上线/查过了"的声明 | AGENTS §Stop Gate → `deeptutor-evidence-discipline` |
| 涉及 turn/session/stream/replay/resume/聊天入口/TutorBot/trace | AGENTS §Contract Discipline + `CONTRACT.md` + `contracts/index.yaml` |
| 任何 bug 调查、状态/路由/上下文承接问题 | AGENTS §Start Gate + `deeptutor-authority-debugging` |
| 任何"新增字段/router/classifier/wrapper/fallback"的冲动 | AGENTS §Principles(Thin wrappers / Single Authority Hard Gate) |
| 写 PRD/审计划/判断能力是否落地 | AGENTS §Hard Invariants(计划纪律)+ `docs/plan/INDEX.md` |
| 跑 eval/smoke/QA 且会创建账号或产生会员活跃 | AGENTS §Hard Invariants(Eval Runner Identity) |
| 阿里云 SSH 任何写操作 | AGENTS §Hard Invariants(Aliyun Write Boundary,原 §3.7) |
| commit/分支/worktree/合并 main | AGENTS §Hard Invariants(git 纪律)+ §Main Merge Workflow |
| Web/BI/前端/浏览器/截图/`next dev`/Playwright | AGENTS §Hard Invariants(Web/BI 内存护栏)→ `deeptutor-web-bi-frontend-gate` |
| 鲁班数据资产/教材/真题/讲义/考频 | `agent-skills/luban-okf-context/SKILL.md` |
| 查架构/CLI/Key Files | `docs/ARCHITECTURE.md`(或 CodeGraph) |

**AGENTS.md 的硬约束在 Claude Code 上一字不动地生效**,不因换 agent 平台而放松。

## gstack 工具链

使用任何 `/gstack-*` 命令前,必读
[`agent-skills/external-tool-absorption-boundary/references/gstack.md`](./agent-skills/external-tool-absorption-boundary/references/gstack.md)
(命令↔工作流映射、越权风险清单、六条硬约束、团队模式禁用状态)。
gstack 的默认行为(auto-commit / 改 CLAUDE.md / 自动开 PR)与本项目纪律冲突,以该文件的中和清单为准。

## 机器强制层

本项目 `.claude/settings.json` 配置了三个 hook(阿里云写边界、`git add -A` 拦截、
SKILL.md 改动自动跑 validator)。hook 是止血带,AGENTS.md 散文才是权威;hook 拦不住的
语义级绕过仍受 AGENTS.md 约束。注:`.claude/` 目前被 gitignore,hook 仅本机生效。

## 备忘

- 本项目默认权衡:**谨慎优先于速度**(琐碎任务可酌情简化)。
- 本文件保持薄。发现 CLAUDE.md 出现 AGENTS.md 已有的内容,删 CLAUDE.md 里的副本。
- 2026-07-12 指令栈收权重构:方法论下沉 agent-skills/、事实下沉 docs/ARCHITECTURE.md、
  gstack 下沉 references/gstack.md;历史全文见 git 历史。
