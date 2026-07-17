# DeepTutor Docs / Code Sync 周审计报告

- 执行时间：2026-07-15 10:07 +0800
- Automation ID：`deeptutor-docs-code-sync-check`
- 总裁决：`BLOCK — docs / contract / code / tests 尚未形成同一 release truth`
- 执行姿态：只读审计；未 reset / stash / checkout / overwrite；未创建 worktree；未修改仓库 authority 文件。

## 1. Provenance / Tier 0

| 项 | 取证值 | 裁决 |
|---|---|---|
| `pwd -L` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` | PASS |
| `pwd -P` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` | PASS |
| git toplevel | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor` | PASS |
| branch | `codex/old-blue-workspace-snapshot-20260710` | 非 main |
| HEAD | `de5c000816c417ac777f38974d7e81585a6d0560` | 当前 checkout truth |
| `origin/main` | `416c59d813abc3c614007b03925f9af13c791ca8` | main 对照 truth |
| merge-base | `967a8e0a056e23fbda49a7c158d39b0407d23753` | 当前 checkout 与 main 已显著分叉 |
| 7 月 8 日当前分支基线 | `5373b518a7944a9efdbb6f834ce45e44d8145e07` | 用于本分支 contract guard |

必须区分三类事实：

1. 当前 dirty checkout 的本地自洽性；
2. `origin/main` 的静态文件事实；
3. 生产部署 / observability truth。

本轮只完成前两类取证，没有 fresh production probe，因此任何旧部署日志只能标 `Historical`，不能作为本周 production closure。

## 2. Dirty state（一等信号）

当前 dirty / untracked 共分为：

- `luban_assets`：54 项；含 P40_N03 修改/删除与 P40_B02、P40_D14、P40_N02 新资产及截图/音频。
- `entry_surfaces`：6 项；`yousenwebview/app.json`、`project.private.config.json` 与 internal diagram WebView test page 删除。
- `governance_docs_skills`：4 项；`AGENTS.md`、skill README/catalog 与未跟踪 `luban-zip-practice-extractor`。
- `other`：1 项；未跟踪 `tests/agent_skills/`。

这些变更均未被清理或覆盖。skill/catalog 当前组合通过 validator，但仍是未提交工作面，状态只能是 `Draft / uncommitted`。

## 3. 差距清单

### D1 — first-run 内容签发 authority 冲突（高风险）

**事实：**

- `origin/main` 的 `deeptutor/services/first_run/script_manifest.v1.json` 已写 `release_status=signed`，四题均 `review_status=signed`。
- 每题 reviewer 是 `owner_cainkyking` 与 `claude_fable_owner_delegate`。
- 签发包 `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/鲁班移动端提分闭环/2026-07-11-first-run-four-question-dual-teacher-review-packet.md` 仍明确要求“两位不同的真实 reviewer identity”且“agent 不代签”，文件状态仍为 `Ready for human review / 未签发`。
- main 的 `_require_signed_manifest()` 只检查两个不同 reviewer ID 与 content hash，不验证 reviewer 是否为真实独立教研；对应测试也只用 `teacher-one / teacher-two` 验证去重与 hash 绑定。
- `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/INDEX.md` 与 first-run implementation plan 仍写 unsigned / release blocked；implementation-notes 又记录签发执行和历史部署四门。

**判定：** 同一业务事实“内容是否获得两个独立真人教研签发”存在三套互斥 truth：签发包、manifest 机械状态、implementation notes。机械 `signed` 不能自动证明教研 authority 成立。

**建议状态：** `Implemented / mechanically signed / independent-human-review authority disputed`。历史部署记录标 `Historical`；在 owner 明确授权 AI delegate 等价于第二独立教研，或补真实第二教研签字前，不得写 `Done`。

### D2 — origin/main 缺 billing package catalog contract（高风险 commerce boundary）

**事实：**

- 当前 checkout 的 `contracts/index.yaml` 与 `deeptutor/contracts/index.yaml` SHA-256 均为 `a0a692...`，byte-identical，并明确 `light_98 98/220`，legacy `light_99/lite_99/99 -> light_98`。
- `origin/main` 两份 registry SHA-256 均为 `03e366...`，彼此 byte-identical，但没有 `mobile_http_read_models.billing_package_catalog`。
- `origin/main` 代码已在 `MemberConsoleService` 使用 `starter_19 / light_98 / vip / svip / supreme_svip`，并将 `light_99` 等 alias 归一到 `light_98`；main tests 同样断言 `light_98`。

**判定：** 上次的“双拷贝 mirror drift”在当前分支已收口，但 main 变成“mirror 一致、稳定 commerce contract 整块缺席”。代码/测试已 `Implemented`，contract surface 仍 `Draft / missing`。

**建议状态：** `Implemented in code/tests; contract backfill required`。不得用“两个 registry 一样”冒充 contract 已同步。

### D3 — RELEASE_* env drift 未关闭，guard 存在两层假绿（中高风险）

**事实：**

- 显式运行 `python3 ../scripts/check_env_registry.py scripts/sync_to_aliyun.sh` 仍失败，8 个未注册 env：`RELEASE_GIT_SHA`、`RELEASE_SERVICE_VERSION`、`RELEASE_GIT_DIRTY`、`RELEASE_DEPLOY_MANIFEST_HASH`、`RELEASE_EXCLUDES_JSON`、`RELEASE_BRANCH`、`RELEASE_COMMIT`、`RELEASE_KEEP`。
- `--all` 的 `_SCAN_ALL_GLOBS` 只有 `deeptutor/**/*.py` 与 `scripts/**/*.py`，不会扫描 `scripts/sync_to_aliyun.sh`。
- 从 automation 强制 cwd `artifacts` 运行 `--all` 时，scanner 内部相对 `git ls-files` pathspec 扫到 0 个 in-scope 文件，却返回 `no in-scope production source changed`。
- 用 repo-root-aware Python wrapper 显式列出 737 个 tracked Python 文件后，得到 `env_refs=418 feature_flags=17` 全注册；这只证明 Python 面，不覆盖 release shell。

**判定：** 上次 `RELEASE_*` blocker 原样存在；默认/`--all` 绿灯均不足以证明关闭。

**建议状态：** release env 使用 `Implemented`；registry `Draft / missing`；guard coverage fix `Proposed`。

### D4 — citation display authority 仍互斥（高风险 contract decision）

**事实：**

- `origin/main:contracts/rag.md:76` 与当前 checkout 都规定：唯一展示 authority 是结构化 `citation_bundle.refs/footer_text`；最终 response 不得内联 `〔1〕` 或追加 prose `依据`。
- `origin/main:docs/plan/INDEX.md` 两处 citation plan 摘要仍承诺正文 `〔n〕` 与末尾 `依据`。
- citation implementation plan 明知此 drift，并保留 inline marker 设计、示例与未勾选 WeChat renderer 验收。
- tests 主要验证结构化 bundle/footer 与 redaction；不能据此证明 canonical response 已符合 structured-only contract。

**判定：** 这是 owner/contract 方向选择，不是低风险文案问题。当前状态应保持 `Implemented locally / shadow / contract decision blocked`，不得升 `Done`。

### D5 — authority docs 仍含被禁用旧绝对路径（低风险文档差距）

当前 checkout 与 `origin/main` 都仍在 authority docs 中引用：

`/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor`

- `CONTRACT.md`：10 处。
- `contracts/learner-state.md`：1 处。

这与本 automation 明令禁止的旧路径冲突，也让本地 Markdown 链接失效。

**建议状态：** `Draft / hygiene fix ready`。应改为仓库相对链接，不要换成另一套机器绝对路径。

### D6 — plan index 完整性：无 broken indexed link，但 attachment / plan 状态仍混杂（中低风险）

| snapshot | plan markdown | unique linked | unindexed | missing linked target |
|---|---:|---:|---:|---:|
| 2026-07-08 branch baseline | 234 | 194 | 40 | 0 |
| current checkout | 258 | 207 | 51 | 0 |
| origin/main | 262 | 213 | 49 | 0 |

- 当前 checkout 相对 7 月 8 日新增的未索引项主要是 2 个真实计划、案例题轻练实现账本附件，以及一个文件名含括号的“怎么测”文档；后者实际已在 INDEX 尾部链接，简单 regex 会误报。
- `origin/main` 新增但未索引的 10 项主要是 battle implementation notes / paired-batch summaries / artifacts 与 methodology log；更适合作为 `Historical / Evidence / Attachment`，不应全部晋升成新主线。
- main 已把 7 月 5 日 revenue gate、R8/R6 production plan 挂入索引；当前 checkout 的 INDEX 落后于 main。

**建议状态：** 活跃 plan 必须 `Proposed/Draft/Implemented` 登记；operations log、run summary、artifact summary 应标 `Historical/Evidence` 并由一个主条目汇总，不逐份制造 authority。

### D7 — Web harness 与真实微信入口：没有直接冒充，但标签仍不够机械（中风险）

- INDEX 仍有 `/wechat-harness` + `Web live verified` 表述，尚未直接写成真微信 PASS；因此不是 outright false claim。
- 但它未使用统一证据类 `wechat_harness_shadow`，容易被后续读者误合并。
- QA matrix 已能区分 `real_wechat_package` 与 `DevTools pending`，这才是正确分层。
- 当前 dirty `yousenwebview` 删除 internal diagram WebView test page 与 DevTools launch conditions；本轮没有运行 DevTools/真机，因此不能据此给 `real_wechat_package` PASS。

**建议状态：** `/wechat-harness` 相关条目改 `Implemented locally + wechat_harness_shadow verified; real_wechat_package pending`。真实页面级 PASS、auth-chain PASS、内容签发 PASS 分开写。

### D8 — WebSocket 单入口与概念 authority（当前 checkout 通过，main 仅静态核证）

- 当前 checkout `check_websocket_route_allowlist.py` PASS：production allowlist 为 `/api/v1/ws` 与非聊天 knowledge progress stream。
- `origin/main` 源码仍含 legacy `guide/question/solve` websocket decorators，但 contract/production mounting 规则保留单聊天入口；本轮未在 main snapshot 运行 FastAPI reflection，故只标静态一致，不标 main runtime PASS。
- `origin/main` 的 `requested_response_mode`、`teaching_mode` alias、`bot_runtime_defaults`、`rag` 与 TutorBot 唯一身份文字边界总体一致，未发现新平行业务身份。

**建议状态：** 当前 checkout `Implemented / verified locally`；origin/main `Implemented / static evidence only`。

## 4. 验证记录

| 命令 / 检查 | 结果 | 证据边界 |
|---|---|---|
| `python3 ../scripts/ci/check_websocket_route_allowlist.py` | PASS | 当前 checkout runtime reflection |
| `python3 ../scripts/check_contract_guard.py --base 5373... --head HEAD` | PASS | 当前分支 7 月 8 日后 committed 增量；不覆盖 origin/main 新提交 |
| `python3 ../agent-skills/scripts/validate_agent_skills.py` | PASS，30 skills | 当前 dirty skill/catalog 组合 |
| `pytest -q ../tests/api/test_mobile_router.py` | 143 passed / 27.71s | 当前 checkout；不是 origin/main |
| `check_env_registry.py --all` | 假绿 | artifacts cwd pathspec 为空且只扫 Python |
| repo-root-aware 737 Python full scan | PASS，418 env refs / 17 flags | 不覆盖 shell |
| `check_env_registry.py scripts/sync_to_aliyun.sh` | FAIL，8 `RELEASE_*` | 真 blocker |
| current registry mirror SHA | identical | 当前 checkout only |
| origin/main registry mirror SHA | identical | 但缺 billing catalog |
| first-run focused pytest | 无法运行 | 当前 checkout 不含 main 新增 `services/first_run` 与 tests；未建 worktree是本轮硬边界 |

CodeGraph：repo 有 `.codegraph/`，但当前环境无 CodeGraph MCP，shell `codegraph` 也不存在；本轮按规则降级为 git object / `rg` / 原文件核证。未声称完成动态调用图审计。

## 5. 低风险 patch 草案（本轮未落盘）

### P1 — 修 authority docs 旧路径

将 `CONTRACT.md` 与 `contracts/learner-state.md` 的机器绝对路径改为相对链接，例如：

```md
[contracts/index.yaml](contracts/index.yaml)
[contracts/turn.md](contracts/turn.md)
[统一 turn 指南](docs/zh/guide/unified-turn-contract.md)
[contract guard](scripts/check_contract_guard.py)
```

### P2 — 给 harness 使用机械证据标签

```md
Implemented locally + `wechat_harness_shadow` verified;
`real_wechat_package` / DevTools / auth-chain pending unless separately evidenced.
```

### P3 — INDEX 只汇总附件，不把日志升格为主计划

在对应 active battle / plan 条目下增加一条 `Historical evidence bundle` 链接，汇总 implementation notes、pre/post summary 与 methodology log；不为每个 run artifact 新造主线。

## 6. 高风险需 owner 确认

1. **first-run 双教研：** `claude_fable_owner_delegate` 是否被 owner 明确授权为“第二位独立真实教研”等价身份？若否，manifest 必须回到 fail-closed 或补真人第二签，且同步 INDEX/签发包/implementation plan。
2. **citation：** 选择 A（遵守当前 contract，canonical response structured-only）还是 B（正式升级 contract 允许 inline marker + footer）。推荐 A，前端独立引用区更符合 single authority。
3. **billing：** 是否确认 main 的公开 catalog canonical 为 `light_98 98/220` 且 legacy `light_99/lite_99/99` 仅入口 alias？确认后把当前分支 registry block 以双拷贝 contract patch 回填 main。
4. **release env：** 8 个 `RELEASE_*` 是受治理的内部 transient env，还是应改成普通 Python 变量/JSON payload？推荐先登记为 `internal_release_context`，同时让 full-scan 覆盖 `.sh` 并固定 `cwd=REPO_ROOT`。

## 7. 推荐下一步 Codex prompt

```text
在 DeepTutor 做一次 authority-first docs/contract 修复，但先停在 owner 决策门：
1) 读取 2026-07-15 docs-code-sync report；
2) 让 owner 依次确认 first-run 第二教研、citation structured-only、billing light_98、RELEASE_* 治理形态；
3) 决策后以 origin/main 为代码 authority，禁止覆盖当前 dirty checkout；
4) 第一批只做低风险 docs patch：CONTRACT/learner-state 相对链接、INDEX harness evidence-class 标签、Historical attachment 汇总；
5) 第二批独立做 contract/code patch：billing 双 registry、env registry + scanner cwd/.sh coverage、first-run reviewer authority gate；
6) 逐批跑 contract guard、env full scan（必须从 artifacts cwd 也实际扫描非零文件）、WS allowlist、相关 focused tests；
7) 最终分开报告 current checkout、origin/main、real_wechat_package、production/observability truth，不把历史 deployment note 当 fresh closure。
```

## 8. 最小结论

本周不是 clean sync。上次 mobile contract guard 的分支增量已转绿，billing 命名也在当前分支收敛到 `light_98`；但 main 缺 commerce contract、`RELEASE_*` 与 scanner 假绿仍在、citation contract 冲突未决，并新增 first-run 双教研 authority 争议。最先该拍板的是 first-run reviewer 身份，其次是 citation；否则继续补测试只会验证当前机械规则，而不会解决业务 authority。
