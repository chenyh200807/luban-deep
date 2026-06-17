---
name: external-tool-absorption-boundary
description: Use this whenever adopting, upgrading, installing, or enabling an external dev tool in this repo — a Claude Code plugin or marketplace skill, gstack, a CLI, an MCP server, a shared hook/formatter. Also trigger it the moment one of those tools' DEFAULT behaviors surprises you: auto-commit, CLAUDE.md/AGENTS/README injection, a PreToolUse/PostToolUse hook that blocks or rewrites a legitimate action (e.g. blocking SKILL.md creation), onboarding that edits config, version bumps, telemetry. Use it before running gstack-ship/land/document, before `git commit` right after a tool ran, and before trusting any tool-generated commit. Absorb the tool's rigor; neutralize its defaults so they never override DeepTutor single authority, branch discipline, or register-before-use.
---

# 外部工具吸收边界

采纳外部工具（gstack / Claude Code 插件 / marketplace skill / CLI / MCP / 共享 hook）时：
**吸收它的严谨流程，中和它的 opinionated 默认行为。** 外部工具的默认是为通用场景设计的，
会悄悄越过本项目的单一权威、分支纪律、register-before-use。工具越"帮你自动做"，越容易绕过 gate。

## 为什么（已踩两次，会再踩）

- **gstack**：`ship`/`land`/`document` 默认 auto-commit、bump 版本、改 CLAUDE.md/README、push、开 PR —— 越过 AGENTS §3.5 Main Merge / §3.6 Branch discipline。
- **everything-claude-code 插件**：一条 PreToolUse doc-guard hook 直接拦掉合法的 `agent-skills/**/SKILL.md` 创建。

## 采纳前审计清单（逐项问）

1. **会自动 commit / push / 开 PR 吗？** → 关掉自动提交；若用，确认它只动当前任务相关文件，绝不 `git add -A`。
2. **会改 CLAUDE.md / AGENTS.md / README / VERSION 吗？** → 禁止自动改这些 authority 文件；要改单独人工、scope 收紧。
3. **装了 hook 吗（Pre/PostToolUse、Stop、SessionStart…）？** → 列出它的 hook，判断是否会拦/改你的合法操作或自动 commit。
4. **onboarding / setup 会注入配置吗？** → 审查注入内容，别污染单一权威。
5. **发 telemetry / 联网 / 远端写吗？** → 敏感动作（部署、远端写）必须落在既有授权边界内（如 Aliyun 只写 `/root/deeptutor`）。

## hook 是叠加的，不是覆盖（关键陷阱）

多来源的同事件 hook 是 **union**：任一 hook `exit 2` 就 block。
所以**在你自己的 settings 里加一条"宽松版"无法覆盖插件里的"严格版"**。要真正解除：

- 从**源头移除/禁用**那条插件 hook（编辑插件 hooks.json 删除该块，或固定/禁用插件），**并**把你要保留的策略搬进自己的 `~/.claude/settings.json`（插件更新不覆盖你的）。
- 注意：插件**重装/更新会从源拉回**它的 hook → 更新后必须重新审计、重新中和。
- hook 改动在**下个会话**才生效（启动时加载）；本会话仍受旧 hook 约束，必要时用 Bash 落盘合规文件。

## 不可越过的硬边界（工具再方便也不让）

- **单一权威**：不新增第二套 schema/router/authority；工具建议的"新增字段/兜底/wrapper/特例"先对照既有 authority（见 AGENTS §0/§5.6/§5.7）。
- **分支纪律**：默认不新建分支、不 auto-commit；提交只含当前任务相关文件，脏树/并行场景尤其只重放自己的 hunk。
- **register-before-use**：工具生成的 schema/skill/资源先登记再消费。
- **远端写边界**：部署类工具的目标路径先证明在授权根内。

## 处置流程

1. **审计**（上面清单）。2. **中和默认**（关 auto-commit、移除越权 hook、scope 收紧）。3. **迁移**要保留的策略进你自己的 settings/配置（防工具更新覆盖）。4. 工具**更新后重新审计**。
