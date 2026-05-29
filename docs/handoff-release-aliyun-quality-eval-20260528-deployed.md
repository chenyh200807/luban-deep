# Handoff — `release/aliyun-quality-eval-20260528` 已上生产

**留言者:** Claude Code session(authz / event-payload backport 线)
**时间:** 2026-05-28 ~16:54 CST
**对象:** 在此工作树并发工作的另一个 agent(创建了本分支 + 留了 `luban-rag-assessment.md`)

## 你创建的 release 分支已经被部到阿里云生产

`release/aliyun-quality-eval-20260528` 当前 tip 是 `ef0f9904`(也是 `origin/main` 的 tip),包含:

- `73bbcd4c feat: closed-book quality eval on real exam ground-truth (9+ north-star B verified-transmit)` —— 你的工作
- `ef0f9904 feat: clamp oversized event payloads at /api/v1/ws public boundary` —— 我的工作(上游 v1.4.x backport 清单最后一项)

两个 commit 都是 Python-only,走 `redeploy_aliyun_fast.sh`,**已经在生产**:

- 公网验收(`https://test2.yousenjiaoyu.com/` + `/healthz` + `/readyz`)三条全绿
- Observability:`release_id=1.0.0+ef0f990464c70b740ccb38328804a925222591ea+production`,ready=True,langfuse 连通
- 远端容器 `deeptutor` Up + healthy(新镜像 sha256:952160f38d1c…)

## 我没动你的东西

- `luban-rag-assessment.md`(231 行 RAG 评估报告,78/100)仍在仓库根 untracked,**没动**。如果你想 commit 它请便。
- 部署没用主工作树脏状态下的 `ALLOW_DIRTY_DEPLOY=1` 兜底——按 runbook 硬规定从 `ef0f9904` 创建了临时 worktree `/tmp/deeptutor-deploy-clamp-20260528`(分支 `release/clamp-deploy-20260528`),部完已清理。
- `release/aliyun-quality-eval-20260528` 本身**没有新 commit**,还在你建好的 `ef0f9904`。

## 上下文(以防你接 backport 线)

本次会话把上游 v1.4.x 安全 backport 清单全部清空 + 把 memory 里那条「authz bypass 待办」纠正成「已由内部 SR 系列闭合」。完整链:

- `daa1b7a6` SSRF guard(WebFetchTool)
- `e0acabfd` fs/exec 默认限制 bot workspace
- `48c9d01f` ExecTool deny-list 边界重锚
- `485c645d` resume_from 跨用户回归测试
- `ef0f9904` 公开 WS event payload clamp

memory:`~/.claude/projects/-Users-yehongchen-Documents-CYH-2-Markzuo-deeptutor/memory/upstream-deeptutor-backport.md` 已更新。

—— 看完可以删此文件。
