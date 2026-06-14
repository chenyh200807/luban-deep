# 共享资源登记治理 · 修复计划(root-cause 框死版)

> 用 root-cause-debugging skill 框定。核心:**修法本身绝不能造出 N 套新治理系统**(那正是我们在修的第二权威病)。三大原则 thin wrappers fat skills / first principle / less is more 贯穿。

## 0. 根因(不是"缺 N 个 registry")

**症状(烟)**:230 env 只登记 52、17 处 ad-hoc 连库、3 套 provider registry、33 裸 flag、schema 闸没通电。
**一等业务事实(火)**:**每个共享资源在被任何 agent 使用前,必须能被机器确认它登记在唯一 canonical 清单里——不存在第二份清单、不存在自报权威、不存在 ad-hoc 创建。** 这个事实对"error code / WS 路由 / migration"被 contract-guard 强制了,对"DB / provider / flag / 凭据 / schema-runtime 契约"没被强制。
**shared failure shape**:`authority drift`(登记纪律覆盖面漂移) + `duplicate decision`(需要登记处各建一套,而非用同一套)。

## 1. 设计前强制输出(root-cause skill 五项)

1. **one business fact**:共享资源"登记了才能用",由机器在 CI 确认,唯一清单、唯一权威。
2. **one authority**:登记纪律的唯一 authority = **现有 contract-guard 机制**(`contracts/*.yaml` 同构 registry section + `check_*` 同构确定性扫描器 + 一个 CI 非零退出 runner)。**不新建 N 套治理系统**;每类资源 = 这一套机制下的一个 section + 一个 evaluate_,挂在同一 runner。
3. **concepts to delete/demote**(修法主体是**收权**不是新增):
   - 3 套 provider registry → **收成 1 套**
   - 17 处 ad-hoc `psycopg2.connect` → **收成 1 个 connection factory**(已有 llm-client-factory 先例)
   - 散落 `os.getenv` → **收进 1 份 env registry**
   - "自报 flag 当权威"(rich leaf install / bundle status)→ **降级,由 release gate 派生**
   - schema 闸"建好没通电" → **接进同一个 contract-guard runner**
4. **why not 老路**:文档约定对并行 AI 已证明无效(这一周);各资源各建一套 = 制造 N 套新 authority = 正是病灶,违反 less is more。
5. **why deterministic CI gate**:协调并行 AI 的唯一手段是确定性闸门,"做不到违反"才换得来"做到";必须 deterministic,不是 LLM/约定。

## 2. 有罪推定通过的条件(新增 registry/guard 不算第二权威,当且仅当)

- 它是**同一个 contract-guard runner 下的 section/scanner**,不是平行系统(一个 runner、一个 CI step)。
- 它把"是否登记"当**确定性结构问题**(在不在清单),不降级语义。
- 每道闸**同构**(registry section + scanner),不特例化 → 不成为未来 patch anchor。
- 旧层(文档/self-flag)确实拦不住并行 agent。
→ 满足则合法;**任何"为某资源单独造一套带自己 runner 的治理系统"的方案,直接否决。**

## 3. 分层执行(越核心越细心,逐层验证再进下一层)

### Layer 0 · 元权威(最核心,先钉死)
- 确立"ONE 治理 pattern,contract-guard 是其单一 runner"。
- **给 G1 schema 闸通电**(待 152 完整性 agent 定稿后,接 pending hunk,只重放自己一行)——它是后续每道闸的模板。

### Layer 1 · P0(最危险,加倍细心,专家进驻)
- **DB 登记 + 连接收口**:ONE connection factory + contract-guard 下一个 db_registry section(哪个 fact 落哪个库/谁能写),**收掉 17 处 ad-hoc 连接**,扫描器拦"未经 factory 的裸连接 / 未登记的库表写"。**不建 DB 治理新系统。** 今天 Supabase 双项目意外的结构性根因。
- **G2 官方-key-primary runtime 不变量**:5705 采分点 install 由 release gate 派生,官方 key 优先序写成 runtime 不变量,删掉自报 flag。
  - **[DONE 2026-06-13]** runtime 优先序不变量已落地(`rich_leaf_runtime.py`):
    - `RICH_LEAF_GRADING_AUTHORITY = AUTH_TEXTBOOK_CITED`(复用 `unified_grading_object` 的 canonical 词表,不新增 authority 名);官方优先序 `official_answer > textbook_cited` 由 unified_grading_object 单一权威继承,不另立。
    - `assert_supporting_only(record)`:fail-closed 不变量,rich-leaf 记录一旦自报 `official_score_allowed` / `llm_may_decide_correctness` / `authority_source=official_answer` / answer-key tier 即抛错。
    - `resolve_grading_point_authority(official_present, rich_leaf_points)`:单一优先序汇点——rich-leaf 点恒被打成 supporting(`textbook_cited` + `official_score_allowed=False`),恒不进 `scoring_points`(官方对错通道);官方缺失时**不提拔** rich-leaf 冒充,correctness 落回既有 open-world 官方路径。
    - 现状根因证实:判分主链路(`deep_question._grade_one_case_v1`)的 rubric points 唯一来源是 `load_rubric`(compiled exam-reference)→ on-the-fly reference → stem,全是 official-answer-backed;rich-leaf 点从不进入 `rubric_points`。`grading=True` 的采分点渲染在生产从未被调用。"官方优先于 5705"此前仅靠**调用点不存在**这一接线偶然维持——本不变量把它变成结构保证。
  - **[WORK ORDER 待办]** install 自报降级(env flag `LUBAN_RICH_LEAF_RUNTIME_ENABLED` → release-gate 派生):未做。理由:它改的是学生判分的**运行时消费开关**,把 flag 换成 release-gate attestation 需要改 `_load_index`/`rich_leaf_runtime_enabled` 的消费路径,改动面与风险超出本次"加不变量+收权"的最小 scope。替代(plan §2 允许):先以上述 runtime 优先序不变量+`assert_supporting_only` 断言锁死"官方缺失时 rich-leaf 不冒充",再单列 install 派生化 work order(把 release-gate attestation 接进消费开关、删 self-report flag)。

### Layer 2 · P1(收权为主)
- provider:**3 套 registry → 1**,扫 base_url 硬编码旁路。
- env/flag:1 份 env registry,扫描器拦未登记 env 引用 + 裸 flag(178+33)。
- 凭据:并入 env registry(集中清单)。

### Layer 3 · P2(收尾)
- 长驻进程登记、REST 路由存在性 allowlist。

## 4. 不确定性与替代方案
- **DB 连接收口**触生产连接路径,风险最高:先只读盘点全部连接点→出 factory 适配方案→影子验证(不改连接行为只加登记)→再收口。替代:若全量收口风险大,先上"扫描器拦新增 ad-hoc 连接"(防新增)+ 存量分批迁移。
- **env 178 个未登记**:可能含已废弃 env;先盘点分类(在用/废弃/拼错),不一刀切登记。
- 每层落地前给:最小复现(未登记资源能溜进来)+ 修复后回归(溜不进来)+ flag-off/范围外不误伤。

## 5. 验收
每道闸:CI 非零退出真生效、对未登记资源 fail、对范围外不误报、与现有 contract-guard 同一 runner。全程 candidate/review-only,不碰生产数据,不夹带并行 WIP。

## 6. 对抗两轮裁决与 scanner 真实边界

**第一轮(Claude 对抗,`b6fe08ef0`)**:6 类假绿/绕过(C1 provider 多行 placebo / I1 `SCHEMA=` marker / I2 closure namespace+tier3 子串 / I3 db aliased-import+COPY+TRUNCATE / I4 env setdefault+pop+裸 getenv / M2 CI 未引号)全部 TDD 治本,28 条对抗回归测试。

**第二轮(Codex gpt-5.5 xhigh, read-only)**:确认 7 个 6 类之外的新绕过 + 3 个系统判断。按"治本子集"裁决落地:

**已治本(3 个"闸根本不生效/极常见写法"的真洞,均 TDD 复现红→修→绿):**
- **I3(c) db `from psycopg import connect`**:双重绕过——绑定 connect 为裸名(alias 匹配器看不到)+ 文件根本不匹配 `_PSYCOPG_FILE_RE` 导致整个 SQL 写扫描被跳过。修:`_psycopg_connect_bindings` 解析 from-import 绑定名(含 `as` 别名)+ 文件门加 `from psycopg2? import` 支路。
- **I4(b) env `from os import environ; environ['X']`/`.get`**:`_ENV_REF_RE` 加裸 environ 支路(同 `(?<![\w.])` lookbehind 防双计 `os.environ`)。
- **CI path filter**:`tests.yml` 只列旧 scanner,scanner-only PR 不触发守卫(改弱一道闸 CI 不跑)。修:加 `scripts/check_*.py` + `scripts/ci/**` glob(pattern 非枚举,未来 scanner 自动覆盖)——**闸必须能保护自己的 scanner**。

**诚实记为 scanner 边界(不打 regex 地鼠):**
- schema `"schema_id": ("...")` 括号字符串、provider `base_url=("a" "b")` 相邻字符串折叠(Python 常量折叠)、process daemon 字段名不含 `task`、process cron YAML flow `- { cron: ... }`、REST 已登记宽前缀下加叶子路由。
- 都属"稍懂 Python/YAML 语义即可绕"。**静态 regex scanner 的真实保证 = 常见 literal 直写的止血 + 漂移预防,不是语义闭包。**

**真闭环 = runtime fail-closed(scanner 是 CI tripwire,不是 authority):**
- DB 只走 `connect_for_fact(fact)`、env/flag 只走 canonical reader、provider client 只走 factory、REST 需 leaf-level inventory 或 router decorator 注册校验。scanner 挡 script-kiddie 直写,runtime fail-closed 挡语义级绕过——两层各司其职,与本计划 §1.5「why deterministic CI gate」一致。

**3 个系统判断(记账,非本轮修):**
- **registry 是"允许集合"非"双向一致性证明"**:grandfather/stale 条目会变"预批准的洞"(将来复用废弃名被当已登记)。→ work order:registry↔code 反向漂移检测(代码删了 registry 还留)。
- **[DONE 2026-06-13, fa5e6b3d4] G2 已接进生产判分** —— owner 授权后,经 §8-10 live A/B 实证(B 编译合约 MAE 0.013、over-credit 0、赢公平 A1、dominate RAG)解锁接线:`rubric_grader_v1.enforce_official_scoring_authority(points, provenance)` 在 `_grade_one_case_v1` 解析 points 后、调 `grade_with_batch_judge_async` 前执行——官方背书点进对错通道,任何 `authority_source==textbook_cited` 的 rich-leaf 点经 `resolve_grading_point_authority` 降级 supporting 并排除评分。**"官方 key > 5705 采分点"从"靠没有调用点偶然维持"变成结构保证。** 当前三源(compiled/reference/stem)无该标记→行为不变;TDD 4+1 条、contract-guard passed、review-only(`official_score_allowed=False` 不动)。
  - 残留:`assert_supporting_only` 仍 0 直接 caller(它由 `resolve_grading_point_authority` 内部调用,已 load-bearing);install 自报 flag→release-gate 派生仍未做(消费开关改造,与本接线解耦)。

工件:`artifacts/luban_grading_artifacts/governance_gate_codex_adversarial_20260613/codex_verdict_last_message.md`(Codex 原始裁决全文)。
