# DeepTutor Daily Health Check — 2026-07-16

## 结论

- **Health verdict: BLOCKED**
- **failure_signature:** `env_p0_artifacts_env_missing_plus_unsigned_compiled_practice_supply_plus_test_cwd_assumption`
- 当前不能把本工作区当作可安全发布或完整可开发环境：`artifacts/.env` 缺失是 ENV-P0；dirty compiled practice authority 又让 F16/S05 供给 fail-closed，产生 2 个可独立复现的后端契约失败。
- 大部分核心行为回归仍绿：两组 Tier 1 共通过 1922 项；dirty-domain 窄回归通过 218 项但失败 2 项；observability 325 项、benchmark 19/19、Web shadow 5 项、五模块静态 Node 矩阵 11 个脚本均通过。

## Authority 与扫描窗口

| 项 | 事实 |
|---|---|
| automation cwd (`pwd -L` / `pwd -P`) | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` / 同路径 |
| git toplevel | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor` |
| `core.worktree` | 空，PASS |
| branch / HEAD | `main` / `8ca6a804dde2c8a4d9ccfd96a061945adf359c7a` |
| origin/main（本地 ref / remote） | `93fe95895c7c407d7c57107b3e6e3f023ab266c1` / 同 SHA |
| branch relation | ahead 3, behind 5 |
| automation baseline | `de5c000816c417ac777f38974d7e81585a6d0560` 存在，但不是 HEAD 祖先；merge-base `967a8e0a056e23fbda49a7c158d39b0407d23753` |
| baseline classification | `BASELINE-LINEAGE-GAP`；不能把 `last_scanned_sha..HEAD` 当线性增量 |
| final HEAD stability | 扫描前后均为 `8ca6a804...` |

本地 `main` 的 3 个独有提交为 practice pool/authority/pack-agnostic 文档与实现；origin/main 另有 5 个本地未包含提交，包括 TutorBot completion authority 收权与 truncated answer fail-close。当前报告只绑定本地 HEAD，不外推到 origin/main。

## Tier 0

| 检查 | 结果 | 说明 |
|---|---|---|
| cwd / physical cwd | PASS | 均为强制 artifacts cwd |
| git authority root | PASS | 父级 deeptutor 仓库 |
| `core.worktree` | PASS | 空 |
| `.env` | **FAIL / ENV-P0** | `artifacts/.env` 不存在、不可读；未借用父目录 `.env` |
| baseline 可用性 | WARN | SHA 可解析，但 lineage 分叉 |
| dirty state | WARN / HOLD | 333 个 tracked modified 文件；`git ls-files --others` 识别 92 个 untracked 文件 |

## 测试结果

| 层级 | 命令/表面 | 结果 | 分类 |
|---|---|---|---|
| Tier 1 | `python scripts/check_contract_guard.py`（从 artifacts 调父仓脚本） | PASS | 合同治理链通过 |
| Tier 1 | unified WS / mobile / session / learner_state | 1050 passed, 2 failed, 5 warnings | 2 FAIL 为测试相对路径假设，不是行为断言 |
| Tier 1 | DeepQuestion / construction grading / RAG | 872 passed, 5 failed | 5 FAIL 为 fixture 相对路径假设 |
| Tier 1 | `npm --prefix web run test:wechat-harness:data` | 5 passed | shadow evidence only |
| Diff-aware | learner/retest/compiled-practice/schema/manifest/migration | 218 passed, **2 failed** | 真实 dirty-domain 回归 |
| Diff-aware | 两个失败 nodeid 独立复跑 | 2/2 reproduced | 非 pytest 污染 |
| Diff-aware | 本地 PostgreSQL 原子 probe claim | 1 passed | 隔离本地 DB，非生产 Supabase |
| Diff-aware | yousen 五模块静态矩阵 | 11 个 Node 脚本全部 PASS | 非真微信入口 |
| Tier 2 | observability + CLI inputs | 325 passed | 本地确定性测试 |
| Tier 2 | benchmark `pr_gate_core` | 19/19 | run `benchmark-1784180093` |
| Tier 2 | live observability / release report-only / learning-report E2E | DEFERRED | authoritative artifacts `.env` 缺失 |
| 真入口 | WeChat DevTools page scenario / real device | NOT EXERCISED | `/wechat-harness` 不升级为真入口 PASS |

### Test cwd authority failure

7 个 Tier 1 失败都使用进程相对路径，例如 `Path("deeptutor/...")`、`Path("tests/fixtures/...")`。automation 的硬门槛要求进程 cwd 保持在 `artifacts`，所以它们读不到父仓文件。失败在单一大组中一致出现，代码检查确认测试没有从 `__file__` 或 git root 解析路径。分类为 test-harness cwd drift，不是 7 个业务回归。

### Dirty compiled supply failure

独立复现：

1. `test_non_f16_compiled_surface_writes_five_items_and_one_canonical_terminal` 抛出 `retest_answer_set_mismatch`。
2. `test_learned_yesterday_due_today_learned_today_not_due` 期望 F16 `retest_available=true`，实际为 false。

直接读取 canonical compiled authority 得到：

- `S05`: 18 items、1 surface，但 public 5 题均 `review.status=pending`、无 signatures；resolver 返回 0 eligible item。
- `F16`: 6 items、1 surface，但 public 5 题均 `review.status=pending`、无 signatures；viewmodel `variant_retest.available=false`。

这不是应该绕过的 fail-close。当前冲突是“测试/产品面仍期待可用”与“服务端签发 authority 明确不可用”不一致。

## Dirty state 分组

- tracked modified 333：约 173 个 docs/raw-data/manifest，50 个 backend，48 个 `yousenwebview`，43 个 `web` 静态 preview，13 个 tests，另有 contracts/scripts/.codegraph。
- untracked 92：主要是 85 个 raw-data inventory/ledger snapshots，另有 practice review packets、PostgreSQL migration/test、5 个 yousen 文件与营销 Office 文档。
- 关键受保护面：learner-state service/store/evidence lifecycle、Luban retest selection/writeback/review_due、contract/schema registry、API router。
- 未执行 reset、stash、checkout、overwrite、commit、push、SSH、rsync 或生产写。

## P0 / P1 / P2

### P0

1. `artifacts/.env` 缺失：Tier 0 ENV-P0，阻断 authoritative live health 与 release evidence。

### P1

1. Compiled practice eligibility 与测试/产品期待冲突：F16/S05 全部 pending，两个后端契约独立失败。
2. 本地 `main` ahead 3 / behind 5 且工作区大脏；不能安全 fast-forward、merge 或代表 origin/main/release truth。

### P2

1. 7 个测试仍把 repo-root 当进程 cwd，和 2026-07-04 artifacts automation authority 不兼容。
2. pre/post 均观察到外部 Computer Use/Playwright/微信 DevTools helper；本轮未使用。Next guard 前后均显示无 AI-owned Next tree，未见 next-server/postcss burst。

## Root-cause / authority frame

### ENV-P0

- one business fact：daily automation 的 runtime config 是否可从唯一批准位置读取。
- one authority：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/.env`。
- breakpoint：文件不存在；父目录配置不是授权 fallback。
- minimal boundary：在 artifacts authority 下提供可读、可解析的配置，或由 owner 明确变更环境来源合同；不在 runner 内偷读父目录。

### Compiled practice

- one business fact：哪些 practice variant 已签发、可下发、可由服务端重判。
- one authority：`compiled/*.practice.authority.json` 的 review/signature/eligible projection，经 `practice_html -> read_model -> retest_writeback` 消费。
- competing authorities：public HTML/旧测试声称 F16/S05 可用，而 compiled authority 声明 pending。
- canonical path：human review signatures -> eligible_variant_ids -> viewmodel/retest selection -> terminal writeback。
- delete-or-demote：删除/更新陈旧的“默认可用”测试期待；不得在 resolver/writeback 添加绕过 pending 的 fallback。若产品确实要求开放，必须先完成真实双签并重新生成供给。

## 今天最值得交给 Codex 的最小任务

1. **修复 tests 的 cwd authority**：把 7 个相对路径读取改为基于 `Path(__file__).resolve()` 或统一 repo-root helper；在 artifacts cwd 复跑两组 Tier 1，目标 0 cwd-path failure。
2. **收口 compiled practice eligibility**：不代签。先决定 F16/S05 是否应公开；若应公开，由真实 teaching/scoring reviewer 完成签名并重建 authority；若仍 pending，更新契约测试为 fail-closed 期望。目标是 resolver、viewmodel、writeback 与测试只认同一 eligibility authority。
3. **隔离处理 main 分叉**：在不碰当前 dirty workspace 的独立人工/后续任务中，把本地 3 提交与 origin/main 5 提交做 same-SHA 集成；本 automation 本轮不建 worktree、不 merge。

## 下一步最小修复 prompt

> 从 `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` 启动，保持该 cwd 不变。先只修 7 个 pytest 相对路径，让它们从 `__file__`/统一 repo-root helper 读取父仓文件；不要改业务逻辑、不要绕过 compiled review eligibility。然后复跑两组 Tier 1。另开一个只读诊断说明 F16/S05 pending 是否是预期治理状态；没有真实 teaching/scoring 签名时不得把 `retest_available` 改成 true。保留当前 dirty state，不 reset/stash/checkout/commit/push。

## Web/进程收尾

- pre/post `codex-memory-snapshot.sh` 已执行。
- pre/post `agent-owned-next-guard.sh --check`: `No AI-agent-owned Next dev process tree detected.`
- 未启动 next dev、next-server、浏览器或微信 DevTools；未使用 Computer Use。

Run window: `2026-07-16T13:25:33+0800` — `2026-07-16T13:37:36+0800`。
