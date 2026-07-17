# DeepTutor Daily Health Check — 2026-07-14

## 结论

**Health verdict: BLOCKED**

今天不应把本工作区当成可安全集成或发布的候选。核心回归套件本身为绿，但 Tier 0 的 `artifacts/.env` 缺失，按自动化合同属于 `ENV-P0`；同时发现一个与环境无关、可复现的 DevTools 默认启动入口漂移。

- failure_signature: `env_p0_artifacts_env_missing_plus_devtools_default_launch_authority_drift`
- 扫描时间: `2026-07-14T08:34:08+0800` 至 `2026-07-14T08:40:03+0800`
- automation baseline: `a600236051e6a0244a45604544f87c021e6f9101`（可用，且为当前 HEAD 祖先）
- scan window: `a600236051e6a0244a45604544f87c021e6f9101..de5c000816c417ac777f38974d7e81585a6d0560`，8 commits / 1305 changed paths

## Authority 与 Git 状态

| 项 | 结果 | 状态 |
| --- | --- | --- |
| `pwd -L` / `pwd -P` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` | PASS |
| git toplevel | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor` | PASS |
| `core.worktree` | 空 | PASS |
| branch | `codex/old-blue-workspace-snapshot-20260710` | WARN |
| HEAD | `de5c000816c417ac777f38974d7e81585a6d0560` | INFO |
| origin/main | `0308b0224b56ebd606e2e55ce9ea0e6695c6b745`（`ls-remote` 与本地 ref 一致） | INFO |
| 与 origin/main 分叉 | behind 315 / ahead 68 | WARN |
| branch tracking | ahead 3 of `origin/codex/old-blue-workspace-snapshot-20260710` | WARN |
| `artifacts/.env` | 不存在、不可读 | FAIL / ENV-P0 |
| 父级 `../.env` | 存在，但未作为 fallback 使用 | INFO |
| contract 双拷贝 | `contracts/index.yaml` 与 packaged copy 字节一致 | PASS |

### Dirty state（一等信号）

测试前后保持 9 个 tracked dirty entry、2 个 untracked group；本轮没有 reset、stash、checkout、overwrite、commit 或 push。

- 规则/skill 治理：`AGENTS.md`、`agent-skills/README.md`、`agent-skills/catalog.yaml` 修改；`agent-skills/luban-zip-practice-extractor/` 与 `tests/agent_skills/` 未跟踪。
- WeChat/yousen：`yousenwebview/app.json`、`project.private.config.json` 修改；internal `diagramWebviewTest` 四个页面文件删除。

## Gate 结果

| 层级 | 命令/证据 | 结果 |
| --- | --- | --- |
| Tier 0 | cwd / toplevel / core.worktree | PASS |
| Tier 0 | `artifacts/.env` readable/import contract | **FAIL: ENV-P0** |
| Tier 1 | `python ../scripts/check_contract_guard.py` | PASS |
| Tier 1 | unified WS + mobile + session + learner_state | PASS: 960 passed, 5 warnings |
| Tier 1 | DeepQuestion + construction grading + RAG | PASS: 873 passed |
| Tier 1 | `npm --prefix ../web run test:wechat-harness:data` | PASS: 5 passed（shadow） |
| Tier 2 | observability + CLI input tests | PASS: 327 passed |
| Diff-aware | `test_deeptutor_package_placement.js` | PASS: 29 assertions |
| Diff-aware | mini-program privacy compliance | PASS: 4 passed |
| Diff-aware | `test_index_launch_home.js` | **FAIL** |
| Web safety | pre/post memory snapshot + Next guard + independent pgrep | PASS: no Next/postcss residual |
| Live observability | `run_observability_daily.py` | DEFERRED: missing authoritative `artifacts/.env` |
| Release report-only | `run_release_gate.py --report-only` | DEFERRED: missing authoritative `artifacts/.env`; not deployment permission |
| Semantic/long-dialog/learning-report/benchmark | not selected by changed core domains | SKIP |
| Real WeChat package | DevTools page scenario | DEFERRED: daily gate未做真入口 closure |

## 严重度与根因

### P0 — automation execution env 缺失

- one business fact: daily health 的 execution surface 必须有可读、可导入的 `artifacts/.env`。
- one authority: 本轮 Tier 0 合同指定的 `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/.env`。
- competing authority: 父级 `../.env` 存在，但若自动 fallback，会把错误 execution surface 伪装成通过。
- breakpoint: `ls -ld .env` 返回不存在，`ENV_READABLE=no`。
- 最小修复：从批准的 secret distribution 恢复 artifacts `.env`，只验证可读性与 `python-dotenv` parse，不在日志输出键值。

### P1 — DevTools normal compile 默认入口 authority 漂移

- failure sample: `FAIL: ../project.private.config.json should launch the host home directly for normal compile`。
- one business fact: DevTools normal compile 默认进入 host home `pages/freeCourse/freeCourse`。
- one authority: `yousenwebview/tests/test_index_launch_home.js` + host-home configuration。
- competing authorities: baseline/origin-main 默认 host home；当前 HEAD 默认 internal diagram page；dirty WIP 默认 first-run page。
- canonical path: `condition.miniprogram.list[current].pathName` 必须回到 host home。first-run/internal 场景可保留为命名条件，但不能争夺 normal compile 默认入口。
- 当前未修：`project.private.config.json` 属于 dirty 用户/并行 WIP，本轮不覆盖。

### P2 — 集成与发布风险

- 当前分支相对 origin/main behind 315 / ahead 68，且工作区 dirty；即使核心测试绿，也不是可发布候选。
- `/wechat-harness` 仅是 shadow evidence；本轮没有真实 `yousenwebview/packageDeeptutor` DevTools page-level closure。
- live observability/release payload 因 Tier 0 env 缺失未运行，不能引用旧 payload 代替当前 HEAD truth。

## 今天最值得交给 Codex 的最小任务

1. **恢复 artifacts env authority**：用批准的 secret distribution 恢复 `artifacts/.env`，验证 readable/non-loop/parse，然后只重跑 observability daily 与 report-only payload，并读取内层 verdict。
2. **收回 DevTools 默认入口**：在不覆盖其他 dirty WIP 的前提下，把 `project.private.config.json` normal compile `current` 指回 `pages/freeCourse/freeCourse`；保留 first-run/internal 为非默认命名场景；重跑 `node yousenwebview/tests/test_index_launch_home.js`。
3. **先对账再集成**：对 ahead 68 / behind 315 与当前 11 个 dirty entry 做归属分类；禁止 reset/stash，未形成 clean candidate 前不运行发布式 closure。

## 下一步最小修复 Prompt

> 从 `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` 执行，只修 `yousenwebview/project.private.config.json` 的 normal compile 默认入口 authority：先证明 `pages/freeCourse/freeCourse` 是 `test_index_launch_home.js` 的 canonical host home，再让 `condition.miniprogram.list[current]` 指向它；保留 first-run/internal 条件但不得默认。不要覆盖其他 dirty 文件，不 commit。验证 `node ../yousenwebview/tests/test_index_launch_home.js`、`node ../yousenwebview/tests/test_deeptutor_package_placement.js`，并报告修前/修后 current path。

## 精确验证命令

```text
python ../scripts/check_contract_guard.py
PYTHONPATH=.. python -m pytest ../tests/api/test_unified_ws_turn_runtime.py ../tests/api/test_mobile_router.py ../tests/services/session ../tests/services/learner_state -q
PYTHONPATH=.. python -m pytest ../tests/core/test_deep_question_submission_grading.py ../tests/services/construction_grading ../tests/services/rag/test_learning_fact_retrieval_pipeline.py ../tests/services/rag/test_retrieval_plan.py -q
npm --prefix ../web run test:wechat-harness:data
PYTHONPATH=.. python -m pytest ../tests/services/observability ../tests/scripts/test_observability_cli_inputs.py -q
node ../yousenwebview/tests/test_deeptutor_package_placement.js
node ../yousenwebview/tests/test_index_launch_home.js
PYTHONPATH=.. python -m pytest ../tests/wx/test_miniprogram_privacy_compliance.py -q
```

