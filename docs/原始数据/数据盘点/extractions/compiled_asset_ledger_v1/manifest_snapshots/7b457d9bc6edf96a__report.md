# DeepTutor OA / OM / Observability 日报（2026-07-12）

## 结论

**Observability verdict：BLOCKED。** 控制面 artifact 按时间仍新鲜（除刚刷新 OM 外约 8.8h），但 release lineage 已失真：candidate 为 `91e01e57e3ac`，live `:8001` 为 `954c830c7bc5`，旧 daily/OA/gate/benchmark 为 `87599ea5a0cc`。因此“fresh by age”不能推导 release-ready。

本次 runner 已 fail-closed：live metrics provenance 为真实 endpoint、HTTP 200，但 runtime identity 不匹配，在线 WS/ARR/benchmark 没有继续执行。证据见 `control-plane/runtime_authority_preflight.json`。

## Tier 0 与 Git authority

- cwd / pwd -P：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- git toplevel：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- branch：`codex/old-blue-workspace-snapshot-20260710`
- candidate HEAD：`91e01e57e3ac7b6aa7fdb3a0c4deacca06db1b93`
- canonical config：repo-root `.env` 经 `EnvStore.resolve_source_path()` 可读；不要求 `artifacts/.env`
- dirty：本修复的 6 个显式文件；不含用户资产清理动作
- 并发事故：本轮外部进程创建 `f9e27fda`，将大量既有 dirty/untracked 资产卷入提交；随后 `91e01e57` 已出现在 origin。未在本轮回滚、重写或再次推送。

## Freshness

| 数据面 | 最新时间（Asia/Shanghai） | 年龄 | 时间判断 | lineage 判断 |
|---|---:|---:|---|---|
| daily_trends | 2026-07-13 09:21 | 8.8h | fresh | STALE (`87599ea5`) |
| oa_runs | 2026-07-13 09:21 | 8.8h | fresh | STALE (`87599ea5`) |
| om_runs | 2026-07-13 18:10 | <1h | fresh | BLOCKED (`954c830c`) |
| observer_snapshots | 2026-07-13 09:21 | 8.8h | fresh | STALE (`87599ea5`) |
| change_impact_runs | 2026-07-13 09:21 | 8.8h | fresh | STALE (`87599ea5`) |
| release_gate_runs | 2026-07-13 09:21 | 8.8h | fresh | FAIL / hold / STALE |
| benchmark_runs | 2026-07-13 09:21 | 8.8h | fresh | 26/26 PASS，但 STALE (`87599ea5`) |
| readiness_checks | 2026-07-13 09:21 | 8.8h | fresh | FAIL / STALE |

所有时间阈值目前未超限；问题是 lineage 而非年龄。release 相关 candidate 已前进但 gate 未同 SHA 更新，按规则为 **RELEASE-P0**。

## 昨日 commit / diff

2026-07-12 有 3 个提交：`e24f0084`（AGENTS/skills/architecture 收权）、`8cee2c31`（指令与 skill 冷读修复）、`87599ea5`（hooks 与 git/skill 强制层）。主要是工程治理面，不构成 Web/微信真实入口 readiness。

## OA / OM / Benchmark / Release Gate

- OA：旧 run 为 `STALE`，5 个 blind spots；无足够证据下真实根因结论不能升级为 closure。
- OM：当前 live runtime ready=true，但 release identity 为 `954c830c7bc5` 且 dirty；它是真实现场，不是 candidate release 证明。
- Benchmark：旧 lineage 26/26 PASS、pass_rate=1.0；只能证明 `87599ea5` 的离线/当时 evidence，不能覆盖 candidate drift。
- Release gate：`FAIL / hold / STALE`；blockers 为 `runtime_release_dirty`、`playwright_evidence_missing`、`wechat_devtools_true_entry_pending`、`artifact_release_stale_vs_head`。
- Surface：旧 Observer 读取到空 ACK；代码已修为优先消费 live metrics，并保持 product behavior 与 ACK 分离，但因 runtime mismatch 尚无同 SHA 新 payload。

## P0 / P1 / P2

- **RELEASE-P0**：candidate/runtime/gate 三条 lineage 分叉；禁止发布结论。
- **AUTOMATION-P1**：共享工作树被外部提交并出现未经本任务授权的 origin 前进，需审计 `f9e27fda` 范围与操作者。
- **OBS-P1**：5 个持续盲区——turn event、surface ACK、recent conversation、product behavior、Langfuse linkage。
- **P1**：Playwright 与真实微信 DevTools true-entry 缺失；Web harness 不可替代真实入口。
- **P2**：同 SHA runtime 恢复后，验证新的 Observer payload 不再包含 `daily_trend` 上游依赖，并确认 metrics surface ACK。

## 观测盲区与不能下的结论

- Langfuse 未启用且 trace_id=0，不能证明 chat/history/trace linkage 完整。
- current repo data root 与 demo runtime data root 不同，不能用当前 DB 的零事件否认 runtime 行为。
- public endpoint、DevTools、Web harness 是不同证据层；本轮未执行浏览器/微信检查，也未把 synthetic smoke 当 release truth。
- benchmark PASS 不能覆盖 dirty runtime、same-SHA drift 或 true-entry 缺口。

## 建议动作

1. Runtime owner 提供与 candidate 同 git SHA、ff snapshot、deploy manifest 的合规 runtime；不要让日报自动杀进程或部署。
2. 在目标 runtime 预置 `qa_eval_/eval_/qa_` eval-runner 身份及显式 smoke token，再重跑日报。
3. 重跑后要求 OM、Observer、OA、benchmark、release gate、daily trend 全部同 lineage；否则继续 hold。
4. 若 change impact 要求前端/微信，再分别补 Playwright 与真实微信 DevTools evidence；二者不可互相替代。
5. Repo owner 审计 `f9e27fda` 与 origin 前进，决定保留、拆分或另行修复；本任务不自动改写历史。

## 下一步最小 prompt

> 在不部署、不改写 Git 历史的前提下，只读确认 candidate 与 `:8001 /metrics` 的 git_sha、ff_snapshot_hash、deploy_manifest_hash；若三者完全一致且目标 runtime 已持久化合规 eval-runner token，则重跑 2026-07-12 observability daily，并只汇报同 lineage 的 OM/Observer/OA/benchmark/release gate 结果。
