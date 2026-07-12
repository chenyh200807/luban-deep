---
name: deeptutor-web-bi-frontend-gate
description: "Controls DeepTutor Web, BI, frontend, browser, screenshot, Playwright, and Next.js work. Use before running frontend commands, opening browser targets, checking UI, or changing web-facing code."
---

# DeepTutor Web BI Frontend Gate

Use this skill to do frontend work without repeating the 2026-06-06 memory
incident: macOS showed Codex Desktop at 172.68 GB; later a Claude Code-hosted
BI `next dev` tree was recorded by Jetsam at ~201.6 GB resident with 3,927
`node` processes. 结论不是"机器内存不够",而是 Web/BI dev server 在 AI agent
进程树下会触发 Next/PostCSS/Node worker storm。本 skill 是该护栏的唯一权威
(原 AGENTS.md "Claude / Codex Web Memory Guardrails" 节已于 2026-07-12 下沉至此)。

## Grey-Release Policy(灰度,不是全封锁)

- 普通后端、文档、只读代码查询、轻量脚本任务,不需要每次跑完整内存 preflight。
- MCP / 浏览器 / Playwright / 微信开发者工具可以按需使用,但一次只恢复或使用
  一个能力;任务结束后关闭长时间 helper。
- Computer Use 仍默认禁用;只有用户明确要求临时验证时,才在新空线程里短时开启,
  并先做内存快照。
- AI agent 托管 `next dev` 仍是硬禁止;Web dev server 必须由明确的人工
  Terminal/tmux 会话托管。
- 一旦出现 stop condition,立即回到清理流程,不继续观察趋势。

## Boundaries That Stay Hard

- 默认不要用 Computer Use 处理 Web / BI / 前端 / 浏览器 / 截图任务;优先终端
  命令、Playwright CLI、浏览器 URL、截图文件。
- 不要让 Codex Desktop、Computer Use、Claude Code 或其他 AI agent 托管长时间
  `npm run dev` / `next dev` / `next-server` / 浏览器进程。
- 如果 `next dev` / `next-server` / `.next/dev/build/postcss.js` 的父链挂在任何
  AI agent 下,直接判为高风险,不要继续观察趋势。
- 不要把 `--max-old-space-size` 当成总内存上限;它只限制单个 Node 进程,拦不住
  几千个 child worker 累计爆内存。
- 不要把 `next dev --webpack` 当成已验证修复;事故中试过 `--webpack` 仍出现
  postcss.js worker。

## Required Preflight

开始任何 Web、BI、前端、浏览器、截图、Playwright、微信开发者工具任务前,先运行:

```bash
/Users/yehongchen/.codex/bin/codex-memory-snapshot.sh
/Users/yehongchen/.codex/bin/agent-owned-next-guard.sh --check
pgrep -af 'SkyComputerUse|SkyComputerUseClient|SkyComputerUseService|next-server|/web/\.next/dev/build/postcss\.js|next/dist/bin/next dev' || true
```

安全基线:

```text
No SkyComputerUse process
No AI-agent-owned Next dev process tree
No old next-server process
No postcss.js worker burst
Codex / Terminal / Claude memory stays in low single-digit GB range
```

## Stop Conditions

出现任一条件,立即停止当前 Web/BI 任务并清理,不要继续生成代码或等它"自己降下来":

```text
Codex matched memory > 8 GB and rising
Terminal / Claude coalition memory spikes with many node processes
other matched > 5 GB with many node processes
postcss.js workers > 50
SkyComputerUseService reappears unexpectedly
next-server remains alive after task end
next dev / next-server is parented by any AI agent
macOS memory pressure warning appears
```

第一响应:

```bash
/Users/yehongchen/.codex/bin/codex-memory-snapshot.sh
/Users/yehongchen/.codex/bin/agent-owned-next-guard.sh --kill
pkill -KILL -f 'next-server|/web/\.next/dev/build/postcss\.js|next/dist/bin/next dev'
/Users/yehongchen/.codex/bin/codex-emergency-cleanup.sh
```

本地事故记录:`/Users/yehongchen/.codex/reports/2026-06-06-codex-desktop-memory-incident.md`

## Workflow

1. Identify whether the surface is Web, BI, shadow harness, WeChat package, or
   static frontend contract.
2. Do not let Codex, Computer Use, Claude Code, or another AI agent host a
   long-lived `next dev` or browser process.
3. Prefer deterministic frontend contract tests and screenshots over GUI
   control. For WeChat, prefer DevTools CLI through
   `wechat-tutorbot-real-entry-qa`.
4. If a dev server is unavoidable, it must be explicitly user/terminal/tmux
   hosted and closed after the task.
5. End with process cleanup verification for `next-server` and postcss workers.

## Verification

- [ ] Memory preflight ran and result was reported.
- [ ] Evidence surface is correctly labeled.
- [ ] No AI-agent-owned long-lived Next/browser process remains.
- [ ] UI claims are backed by tests, screenshot, or scenario output.
