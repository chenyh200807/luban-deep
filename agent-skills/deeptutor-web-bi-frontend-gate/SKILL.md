---
name: deeptutor-web-bi-frontend-gate
description: "Controls DeepTutor Web, BI, frontend, browser, screenshot, Playwright, and Next.js work. Use before running frontend commands, opening browser targets, checking UI, or changing web-facing code."
---

# DeepTutor Web BI Frontend Gate

Use this skill to do frontend work without repeating the Codex Desktop memory
incident.

## Required Preflight

Run the `AGENTS.md` memory guard commands before frontend, browser, screenshot,
or Playwright work:

```bash
/Users/yehongchen/.codex/bin/codex-memory-snapshot.sh
/Users/yehongchen/.codex/bin/agent-owned-next-guard.sh --check
pgrep -af 'SkyComputerUse|SkyComputerUseClient|SkyComputerUseService|next-server|/web/\.next/dev/build/postcss\.js|next/dist/bin/next dev' || true
```

If risky processes are found, clean them before proceeding.

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
