# 鲁班移动端 P0A Supergoal 调度 Prompt

> Status: `Ready for branch execution`
> Date: 2026-06-11
> Branch: `codex/supergoal-luban-mobile-p0a`
> Worktree: `/Users/yehongchen/.config/superpowers/worktrees/deeptutor/supergoal-luban-mobile-p0a`
> Supergoal run: `.supergoal/p0a-HPVyHt`

本文件是给后续 agent / Codex session 使用的 Supergoal 执行入口。它不替代 canonical PRD；产品与 contract authority 仍以本目录下当前 P0A 文档包为准。

## 1. 已安装工具

`robzilla1738/supergoal` 已安装到：

```text
/Users/yehongchen/.codex/skills/supergoal
```

Codex 重启后可直接使用 `/supergoal`。当前分支已经生成 Supergoal run artifacts，因此不重启也可以直接执行下面的 `/goal` prompt。

## 2. 本次执行目标

完成鲁班移动端 P0A 提分闭环的窄纵切：

```text
今日焦点 -> scoped practice -> 批改 -> task-scoped learning_evidence -> 错因读回 -> 错因复练 -> 复测 -> decision package
```

首个 spike 固定为 F16 防水，复用 M32 防水 Grading-to-Brain 证据链，不并行展开 5 个母题。

## 3. 不可破坏的 authority

- true-entry 验收：`yousenwebview` project root + `packageDeeptutor` target subpackage。
- `wx_miniprogram`：只算 shadow/source evidence，除非有同步/移植证据。
- 推荐：`training_intent` / `NextBestAction` 生成候选，`priority_score` 只做排序与解释。
- 半写/轻练：必须有 `task_scope`，范围外采分点只能 `not_evaluated`，不得写 `miss`。
- 错因：`mistake_tag` schema 未冻结前只能 display-only，不写长期 truth。
- 掌握：用户点“已掌握”只是主观 close intent，不是 canonical mastery；客观掌握需要复测/迁移题/遗忘曲线后的再验证。

## 4. 可直接粘贴的执行 prompt

```text
/goal "Execute the Supergoal run at .supergoal/p0a-HPVyHt for the Luban mobile P0A scoring-loop transformation. Start by reading .supergoal/p0a-HPVyHt/PROTOCOL.md, .supergoal/p0a-HPVyHt/STATE.md, and .supergoal/p0a-HPVyHt/ROADMAP.md. Then execute phases 1 through 6 in order by reading .supergoal/p0a-HPVyHt/phases/phase-N.md. For every phase, print SUPERGOAL_PHASE_START, run the mandatory commands, perform the work, print SUPERGOAL_PHASE_VERIFY with evidence for every acceptance criterion, update STATE.md, and print SUPERGOAL_PHASE_DONE. Preserve single authority: yousenwebview/packageDeeptutor is the true-entry target, training_intent/NextBestAction is recommendation authority, task_scope prevents partial-answer false misses, mistake_tag cannot become long-term truth before contract freeze, and user mastered actions cannot close canonical mastery without objective evidence. After phase 6, run the final audit in PROTOCOL.md and only print SUPERGOAL_RUN_COMPLETE after AUDIT_COMPLETE. Do not start long-running frontend dev servers, do not use wx_miniprogram evidence as true-entry pass, and do not write real-student canonical truth without authorization."
```

## 5. 分支使用方式

```bash
cd /Users/yehongchen/.config/superpowers/worktrees/deeptutor/supergoal-luban-mobile-p0a
git status --short --branch
```

该 worktree 与主仓脏改动隔离。执行时只在本分支内修改文件；不要把主仓未提交改动混入本分支。

## 6. 当前 Supergoal 文件

- `.supergoal/p0a-HPVyHt/ROADMAP.md`
- `.supergoal/p0a-HPVyHt/STATE.md`
- `.supergoal/p0a-HPVyHt/PROTOCOL.md`
- `.supergoal/p0a-HPVyHt/phases/phase-1.md`
- `.supergoal/p0a-HPVyHt/phases/phase-2.md`
- `.supergoal/p0a-HPVyHt/phases/phase-3.md`
- `.supergoal/p0a-HPVyHt/phases/phase-4.md`
- `.supergoal/p0a-HPVyHt/phases/phase-5.md`
- `.supergoal/p0a-HPVyHt/phases/phase-6.md`
