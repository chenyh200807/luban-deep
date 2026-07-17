# DeepTutor Docs Code Sync Check - 2026-07-08

运行时间: 2026-07-08T10:05:15+08:00

## 0. Tier 0 / Provenance

- `pwd -L`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- git toplevel: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- branch: `release/old-blue-frontend`
- HEAD: `5373b518a7944a9efdbb6f834ce45e44d8145e07`
- origin/main: `c7f57b74bbd4afdae413809e773551db2933e34f`
- branch state: `## release/old-blue-frontend...origin/release/old-blue-frontend [behind 3]`

本轮只读审计主仓源码；只写本报告和 automation memory。当前 workspace dirty 范围很大，结论只代表当前 workspace truth，不能直接写成 `origin/main`、production 或 release truth。

## 1. Guard / Verification

- `python3 ../scripts/ci/check_websocket_route_allowlist.py` -> PASS. 生产 WS 仍只有 `/api/v1/ws` 与非聊天 knowledge progress stream。
- `pytest ../tests/api/test_mobile_router.py -q` -> 143 passed. 这只证明当前移动 router 局部测试绿。
- `python3 ../scripts/check_env_registry.py` -> FAIL. `scripts/sync_to_aliyun.sh` 新增/使用的 `RELEASE_GIT_SHA`、`RELEASE_SERVICE_VERSION`、`RELEASE_GIT_DIRTY`、`RELEASE_DEPLOY_MANIFEST_HASH`、`RELEASE_EXCLUDES_JSON`、`RELEASE_BRANCH`、`RELEASE_COMMIT`、`RELEASE_KEEP` 未登记。
- `python3 ../scripts/check_contract_guard.py` -> FAIL. dirty 的 `deeptutor/api/routers/mobile.py` 触发 `turn` 与 `capability` contract-sensitive 变更，但没有同步 contract surfaces。
- docs/plan link scan: indexed links 217, missing links 0, unindexed files 45。
- contracts duplicate-key scan: `contracts/index.yaml` 与 `deeptutor/contracts/index.yaml` 均无 duplicate YAML keys。

## 2. 高风险需确认事项

### H1. 计费套餐 contract / code / packaged mirror 三方漂移

证据:
- 根 contract 有 `billing_package_catalog`，但 packaged mirror 缺失同一块: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/contracts/index.yaml:131` vs `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/contracts/index.yaml:131`。
- 根 contract 当前仍写 `light_99 99/220`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/contracts/index.yaml:134`。
- dirty code 已把套餐引用和 alias 改成 `light_98`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py:140`、`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py:156`。

建议状态: `Draft / high-risk confirmation required`.

不能只把 mirror 补齐。需要 owner 先拍板 launch catalog 到底是 `light_99` 还是 `light_98`，再同步:
- `contracts/index.yaml`
- `deeptutor/contracts/index.yaml`
- `MemberConsoleService._default_packages` / package source
- mobile billing tests
- `.env.example` / docs if package wording出现

### H2. 微信支付 native checkout 已进 dirty code，但 contract/env gate 未闭合

证据:
- dirty `mobile.py` 新增 WeChat Pay order/openid/notify membership purchase path: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py:1111`、`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py:3124`。
- `.env.example`/`contracts/env_registry.yaml` 新增 WeChat Pay 配置，但 env guard 仍失败在 release env，说明 env registry 当前不是 clean。
- `check_contract_guard.py` 因 `mobile.py` 失败，说明该支付/移动 HTTP 改动还没满足 contract surface 更新要求。

建议状态: `Implemented locally / contract gate failing`.

下一步不要写成 Done。至少补齐 `contracts/index.yaml` + packaged mirror 的 mobile billing/payment control 语义，或明确把 WeChat Pay notify 只登记为 wallet/member authority 的 HTTP adapter，不得写 learner-state / turn / capability truth。

### H3. citation authority 旧漂移仍未决

证据:
- `contracts/rag.md` 要求学生端 citation 唯一展示 authority 是结构化 `citation_bundle.refs/footer_text`，最终 `response` 正文不得内联 `〔1〕`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/contracts/rag.md:76`。
- 现有测试仍断言 response 内联 `〔1〕`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/tests/agents/chat/test_answer_citations.py:42`、`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/tests/capabilities/test_tutorbot_answer_citations.py:84`。
- `docs/plan/INDEX.md` citation row 仍描述正文 marker / 依据脚注: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/INDEX.md:173`。

建议状态: `Implemented locally / contract decision pending`.

这不是低风险文档 patch。要么 contract 正式改回允许 inline markers，要么实现/测试/renderer 改为 structured-only。当前只能保持 high-risk/manual。

### H4. release env registry 与 deploy snapshot 语义未同步

证据:
- `scripts/sync_to_aliyun.sh` 使用 `RELEASE_GIT_SHA` 等 release env: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh:256`、`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/sync_to_aliyun.sh:388`。
- `check_env_registry.py` 对 8 个 `RELEASE_*` 变量失败。

建议状态: `Draft / env registry required`.

低风险 patch 草案: 将这些 release-only runtime env 加入 `contracts/env_registry.yaml` 的合适分组，并同步 `.env.example` 是否需要示例。若它们仅为脚本内部 export，也应登记为 deploy-script internal env，避免裸 env 漂移。

## 3. 中低风险 docs/plan 同步缺口

### M1. 新计划文件未全部挂入 docs/plan/INDEX.md

证据:
- docs/plan link scan: missing links 0，但 unindexed files 45。
- 新增活跃计划中，`2026-07-08-luban-compiled-asset-grading-wiring-map.md` 已在 dirty `INDEX.md` 添加: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/INDEX.md:74`，但该文件本身仍 untracked。
- `2026-07-05-luban-grading-revenue-gate-reconciled-milestone-plan.md` 未挂入 index，且正文标 `Proposed / reconciled`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/评分引擎与金标工件/2026-07-05-luban-grading-revenue-gate-reconciled-milestone-plan.md:3`。
- `2026-07-05-luban-r8-r6-content-bank-production-plan.md` 未挂入 index，且正文标待 owner/教研批准: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/鲁班移动端提分闭环/2026-07-05-luban-r8-r6-content-bank-production-plan.md:3`。

建议状态:
- compiled asset wiring map: `Reference / Draft in dirty workspace`.
- grading revenue gate plan: `Proposed / reconciled`.
- R8/R6 bank plan: `Draft / owner approval pending`.

低风险 patch 草案:
- 在 `docs/plan/INDEX.md` 评分引擎段新增 revenue gate plan row。
- 在 `docs/plan/INDEX.md` 鲁班移动端提分闭环段新增 R8/R6 content bank row。
- 若 `INDEX.md` 引入 07-08 wiring map，必须同一变更纳入该 untracked 文件，避免 committed index 指向未提交文件。

### M2. 计划目录里存在大量附件/设计资产未索引

证据: link scan 列出 45 个 unindexed 文件，其中包含增长运营宣传片脚本、设计资产 HTML、鲁班 knowql inventory 等。

建议状态: `Historical / Attachment` 或 `Reference`，不要全部当 active plan。

低风险 patch 草案: 在 `docs/plan/INDEX.md` 的 `附件与原型资源/` 或各主线下加一段“未作为执行计划的附件包”，只索引目录级入口，不逐个把宣传片脚本升级为计划 authority。

## 4. Dirty State 分组

当前 dirty 不是噪音，必须作为一等信号:

- Contract/env/release: `.env.example`, `contracts/env_registry.yaml`, `scripts/sync_to_aliyun.sh`, root/package contract mirror drift。
- Mobile billing/payment: `deeptutor/api/routers/mobile.py`, `deeptutor/services/wechat_pay.py`, `tests/api/test_mobile_router.py`, `tests/services/test_wechat_pay.py`。
- Member/wallet/Luban read model: `member_console`, `wallet`, `luban_lesson` 相关 service/test。
- WeChat/yousen billing/profile UI: `wx_miniprogram/*`, `yousenwebview/*`。
- Docs/plan/raw data: `docs/plan/INDEX.md`, two 2026-07-05 plan docs, 2026-07-08 wiring map, `docs/marketing/`, concept-card bank JSON。

本轮没有 reset/stash/checkout/overwrite。

## 5. 建议状态清单

| 对象 | 建议状态 | 理由 |
|---|---|---|
| `/api/v1/ws` single-control-plane | `Implemented` | WS allowlist guard passed。 |
| WeChat Pay mobile billing path | `Implemented locally / contract gate failing` | 局部测试绿，但 contract guard/env guard 未闭合。 |
| billing package catalog | `Draft / needs owner decision` | `light_99` contract 与 `light_98` code drift，packaged mirror缺块。 |
| answer citation | `Implemented locally / contract decision pending` | contract structured-only vs tests inline marker。 |
| 07-08 compiled asset wiring map | `Reference / thin-index` | 文档自身声明不是新 authority，且已在 dirty INDEX row。 |
| 07-05 grading revenue gate plan | `Proposed / reconciled` | 纯规划，不改 runtime。 |
| 07-05 R8/R6 bank plan | `Draft / owner approval pending` | 正文写待 owner/教研批准。 |
| unindexed design/script assets | `Historical/Attachment` | 不应全部升级为 active plan。 |

## 6. 下一步 Codex Prompt

```
从 /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts 启动，读取 AGENTS.md、CONTRACT.md、contracts/index.yaml、docs/plan/INDEX.md 和 automation report 2026-07-08。不要创建 worktree，不要 reset/stash。请按 dirty workspace 精确分组修同步门：
1. 先让 owner 决策 billing catalog 是 light_98 还是 light_99；
2. 按决策同步 contracts/index.yaml 与 deeptutor/contracts/index.yaml，并补 mobile billing/payment contract surface；
3. 登记 scripts/sync_to_aliyun.sh 使用的 RELEASE_* env，使 check_env_registry.py 通过；
4. 把两个 2026-07-05 活跃计划挂入 docs/plan/INDEX.md，确保 2026-07-08 wiring map 和 INDEX 同提交；
5. 不要处理 citation inline vs structured 的实现，除非 owner 明确拍板 contract 方向。
验证至少跑 python3 scripts/check_env_registry.py、python3 scripts/check_contract_guard.py、python3 scripts/ci/check_websocket_route_allowlist.py、pytest tests/api/test_mobile_router.py tests/services/test_wechat_pay.py -q。
```
