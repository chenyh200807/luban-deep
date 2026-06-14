# 全项目 Schema 统一 + register-before-use 覆盖审计与收口计划

> 来源:31-agent 只读专家 workflow(`wf_e3612acc-a22`,15 专家 + 3 对抗 completeness critic + 12 gap-fill + 1 架构师综合,3.2M token)。**全程只读,无改动。** 完整结果(288KB)在 `/private/tmp/.../tasks/wrbrdpap0.output`。本文是收口执行的单一权威。
> 触发:用户指出"schema 不统一不只是判分;还有其他 schema;特意要求先注册才能用;schema 统一是基础设施里的基础"。

## 0. 一句话结论

**治理是"判分单族"的:register-before-use + 单一权威只对判分 schema-id 族(T1/T2/T3,closure CLOSED 177/0 orphan)机器强制。其余每一个 schema 族——turn/stream、learner-state、capability、RAG、learning-report、config-runtime、API 请求/响应、~376 个 Pydantic/TypedDict/dataclass、prompt+LLM-I/O、benchmark fixture、前后端契约——都是"文档或约定"级,没有字段级 register-before-use 闸。而且连判分闸的 per-PR 漂移/权威强制都是个没接线的 PENDING HUNK。**

更糟:中央 runner `check_contract_guard.py main()` 的返回值里**根本没有 `schema_ok`**;~90% 测试在 CI 是 dark 的(判分 registry 测试也 dark → stale 计数绿着 ship);还有一批"看着像治理、其实没人读"的假闸(orphan index key、dark guard、phantom registry 条目、dead schema)。

## 1. 覆盖图(逐族裁决)

| schema 族 | 单一canonical | 谁治 | register-before-use | 裁决 |
|---|---|---|---|---|
| 判分 typed object(luban_grading_object.v1+8 deprecated) | yes | schema_registry --closure(独立 CI step) | **partial**(只抓 orphan ID;per-PR 漂移/权威是 PENDING HUNK,未接 main()) | STRONG 但 per-PR 闸 UNPOWERED;tier_counts stale(yaml 147/176 vs 实扫 148/177) |
| T2 runtime 契约(20,含 context_pack/rich_leaf_bundle/concept_registry) | ID yes / 字段 no | schema_registry(仅 ID) | partial(全部 needs_field_canonicalization=true;字段漂移只 warning 且 closure 路径不跑) | WEAK——ID 钉了,字段全没钉 |
| assessment report p0a-v1 | yes | **none**(dash 格式 fail `_FULLSET_VERSION_SUFFIX_RE`) | not-enforced(既没注册也不算 orphan,永久隐形) | GAP——达标该注册却结构上抓不到 |
| turn/stream 事件类型(13 值) | **no**(4-6 处独立定义) | index.yaml turn 域(文件co-change)+ WS 单入口 allowlist | not-enforced(加新事件类型无闸;sqlite turn_events.type 无约束 TEXT=durable replay 权威) | GAP——单入口强制了,但事件词表多权威无 parity 闸 |
| learner-state(PCP/training_intent/error_events) | partial | learner-state.md(prose)+ learner_state.py(无 closure)+ index.yaml(co-change) | not-enforced | GAP——error_events 同槽两形(evidence vs evidence_span 语义冲突)最致命 |
| capability request(6 模型/7 内置) | yes | index.yaml capability 域(co-change) | partial(改 schema 文件强制;**注册步骤 builtin→schema 映射无完整性闸**) | MODERATE |
| RAG 输出(evidence_bundle/retrieval_plan.v1) | partial(3 管线产不同 dict) | **none** | not-enforced(retrieval_plan 版本化跨消费却隐形) | GAP |
| learning-report read model(v1+v2 dual-emit) | yes | learning-report.md + index.yaml(co-change) | not-enforced(整数 schema_version 隐形) | GAP——达 T2 必注册门槛却 doc-only |
| config-runtime(LLM/Embedding/Search config) | yes | config-runtime.md + index.yaml(**schema_files:[] 空**) | not-enforced(无 schema_version) | GAP——code 里 typed 但零机器链 |
| API 路由 pydantic(86 模型/26 路由) | **no** | **none(只治 mount prefix)** | not-enforced(任意 inline 即用;13/276=4.7% 有 response_model;6 种 envelope key;5 个重名重复类) | GAP——按类数最大的未治面 |
| 全部 ~376 个类定义(134 BaseModel+23 TypedDict+219 dataclass) | partial(只 contracts/ 单权威) | **none** | not-enforced(类定义层完全无 register-before-use;竞争对:TutorResponse/LLMResponse、rag.SearchResult/search.SearchResult、dead config/schema.LLMConfig) | GAP |
| error codes(23) | partial(py vs md 双权威声明) | check_contract_guard `code_ok`(**已接 main()**) | partial(扫 4 模块;5 个 emit 点在扫描外;3 份本地 _ERROR_LABELS 副本;py-md 无机器同步) | MODERATE——唯一接了中央 runner 的 literal 扫 |
| knowledge_node_id(1A4 taxonomy) | partial(8 个 cluster 前缀是第二权威) | check_contract_guard `node_ok`(已接) | partial(扫 5 文件但**全 0 命中=空跑**;3 生产文件+83 fixture 未扫) | WEAK——正向强制从未被 CI 跑到 |
| DB 表 schema(Postgres) | partial(16 迁移;12+ 表无迁移;phantom concept_taxonomy_registry) | db_registry + check_db_registry --all | partial(治"哪张表写";不治列 schema;多行 INSERT/动态表名旁路) | MODERATE |
| DB 表 schema(SQLite,22 表 inline) | **no** | **none** | not-enforced(列改约定级;turn_events.type 是 durable 权威却无约束) | GAP——22 个 durable 存储零治理 |
| 前后端契约(WS 帧/REST 响应/脱敏 blocklist) | **no** | none 除 BI write-endpoints(唯一 codegen+drift 且在 CI) | not-enforced(脱敏 blocklist 4 份分歧副本——**安全相关**) | GAP——最高风险实例 |
| BI 指标 registry | yes(codegen) | **drift 守卫 DARK**(零 workflow 引用) | not-enforced(unknown id 静默 fallback) | GAP——单源但 drift 闸 CI 不跑 |
| harness/model 权威(SCENE_COMPOSITION/DEFAULT_LLM_MODEL) | partial(各单定义) | **eval/gates.yaml only(零 GHA 读)** | partial(AST 守卫真抓过 regression 但只本地跑) | GAP——PR-blind |
| prompt 模板输出 + LLM json_object I/O(21+22) | **no** | **none**(test_prompt_parity 指向 src/agents/=0 文件,空跑) | not-enforced | GAP——最大隐式 schema 面 |
| benchmark golden fixture(9+4 副本) | partial | partial(BenchmarkRegistry type-gate;golden --check 不在 CI) | not-enforced(版本串 fail closure 正则) | GAP |
| 两个 contract index(contracts/ vs deeptutor/contracts/) | partial(已漂移) | check_contract_guard 只读 root 的 domains | partial(4 个 orphan 顶层 key prose-only;duplicate YAML key 静默丢) | GAP |
| 跨 registry 元权威(5 registry+2 index) | **no** | **none**(无总账;gates.yaml 零 GHA 读) | partial(各族内强制;集合无元闸/无重叠检测/无反向漂移) | GAP——基础的基础无 roll-up |
| CI pytest 覆盖(治理单测) | n/a | 5 个 scanner step 部分补偿 | partial(**718/793=90% 测试 CI 不跑**;schema registry 测试+scanner regression pin 全 dark) | GAP——stale 计数绿 ship 的根因 |

## 2. 第二权威 / 假闸(看着像治理、其实没人读)

- `contracts/index.yaml:480 learning_state_inference`、`:508 luban_grading_engine`、`mobile_http_read_models`、`mobile_http_billing_controls` —— 顶层 key 带 authority-chain/forbidden,**guard 只读 `domains`(line 125),这些零强制**;文件自己注释都承认"never consumed by any guard"。
- `mobile_http_auth_controls` —— **duplicate 顶层 YAML key**(index.yaml:106 & :132),PyYAML 静默留最后一个,第一块丢。
- `error_code_registry.md` vs `error_codes.py` —— 互相声称对方是 mirror,矛盾权威序,无机器同步;另有 3 份本地 `_ERROR_LABELS` 副本。
- `TurnEventType`(unified_turn.py) vs `StreamEventType`(core/stream.py) —— 同 13 值手维护副本,无 import 派生;Pydantic 只用于 export 不做运行时校验。
- `sqlite_store turn_events.type TEXT` —— turn.md 称的 durable replay 权威,却是最无约束的第四处定义,turn.md 自己没承认它。
- `config/schema.py LLMConfig`(0 importer,dead)与 live `services/llm/config.LLMConfig`(@dataclass,8+ importer)并存。
- `provider_registry` grandfather 的 tutorbot/providers/registry.py + provider_runtime EMBEDDING_DEFAULTS —— base_url 分歧仍在生产解析路径。
- `eval/gates.yaml` 的 harness/model authority gate、`test_bi_metrics`、`test_prompt_parity` —— 看着是覆盖,实则 CI 永不跑(dark/空跑)。
- `db_registry concept_taxonomy_registry` —— 注册了的表名,迁移和代码里都不存在(phantom);真表 luban_canonical_taxonomy 反而没注册。`run_luban_m26_live_closure` 注册成 write 实则 readonly(双标注错)。

## 3. 收口计划(P0→P3,全程复用同一套 contract-guard runner,不建第二套治理系统)

**P0(最高杠杆 + 最便宜,先做)** — 执行状态见每条末尾。
1. **接 PENDING HUNK**:把 `evaluate_schema_registry()` 接进 `check_contract_guard.py main()`,让 `schema_ok` 进返回布尔(line 416)——判分闸从"只抓 orphan ID"变成全 register-before-use(per-PR 漂移+权威完整性),**零新系统**。逻辑已写好已测,只差 3 行接线。**【DONE 2026-06-14, commit 46c9379e9】** 在并行线上游吸收守卫 WIP 落地后,独占基线接 schema_ok(同时纳入其 upstream 守卫),`schema-registry-guard` 现进中央 runner 返回布尔,per-PR in-scope 判分 schema 漂移/权威/register-before-use 全 PR-blocking。
2. ~~修 dash 盲点:`_FULLSET_VERSION_SUFFIX_RE` 加 `-v[0-9]`~~ **【CORRECTED 2026-06-14】blanket 加 `-vN` 不安全**:dash 也是 model 名写法(`deepseek-v4-flash`/`embed-v4`/`handwriting-v1`)+ 文件名(`bi-v2-*.generated.ts`),会把它们误收成 schema id → 大量假 orphan。p0a-v1 必须**targeted 注册**(只在 schema_version/schema_id 赋值上下文匹配,或显式 known-id),不能靠 blanket 正则。待 P0#1 接线时一并 targeted 处理。
3. **点亮治理测试**:把 register-before-use 闸自己的 regression 测试接进 CI。**【DONE 2026-06-14, commit 15e6492e5(部分)】** 修 stale 计数(schema_registry.yaml 176→177 / tier3 147→148,对齐 live)+ smoke allowlist 加 `test_schema_registry/db/env/provider/process_registry`(109 测试,含 I1/I2/I3/I4 pin + closure 计数测试)。**故意不加 `test_contract_guard.py`**(并行线改 check_contract_guard.py,WIP-coupled)——待 P0#1 时一并接。`tests/contracts/test_index_consistency` 仍待点亮(P1#5)。

**P1**
4. **【DONE 2026-06-14, commit 5dcc1c498】** tests.yml 接进 `check_harness_authority.py` + `check_model_authority.py`(两 guard 现 green,以前 PR-blind,现 PR-blocking)。
5. 一个手术 PR 修 index.yaml 结构 bug:删 duplicate `mobile_http_auth_controls`、把 package copy 补 http_routes+test_rbac、加 CI step(或点亮 test_index_consistency)断言两份一致。
6. **脱敏 blocklist 单源化**(安全相关):contracts/ 定义一次 frozenset,三处 import,JS 副本 codegen(复用 bi_v2_write_endpoints 模式),加 drift 测进 CI。

**P2** — 收口状态:P2#7 ✓ / P2#8 **6/6 ✓**(evidence_bundle consolidation 2026-06-14 完成)/ P2#9 ✓。**P2 全部落地。**
7. BI 指标 drift 守卫接 CI(一行)。**【DONE 2026-06-14, commit 41e47cddc】** `test_bi_metrics.py`(含 `test_metric_registry_ts_in_sync`: `gen_bi_metrics_ts --check` 检测 generated.ts 与 BI_METRICS 漂移 + 8 个 metric_id 契约测试)进 CI smoke allowlist,从 PR-blind 变 PR-blocking。smoke-safe(仅 import bi_metrics)。
8. 把真·跨消费非判分 schema 升进 schema_registry 的 T2/新 runtime_contract 段(复用同一 closure scanner):learning-report(v1+v2)、RAG retrieval_plan/evidence_bundle、learner-state PCP/training_intent/error_events——前置:先给每个一个 typed id 字面量让 scanner 看得到。**【6 个命名目标 5/6 DONE 2026-06-14】** 每个都用"加 module-level SCHEMA_ID 常量(行为保持,整数版本不动)+ namespace 正则 tight 分支(实测 delta 恰好新 id)+ T2 注册 needs_field_canonicalization:true + producer↔registry 域测试"的同一 recipe,闭包逐步 CLOSED 178→183(tier2 21→26):
   - learning_report_read_model.v2(commit 405121cfa)
   - rag_retrieval_plan.v1(commit 8cfe52bddbfd)
   - personalization_context_pack.v1(commit ab9244fda)
   - learning_training_intent.v2(commit 13ee7d64d)
   - grading_error_event.v1(commit 7a4745279;error_events 目标。注=可见性,evidence vs v1-rubric evidence_span 字段 reconciliation 是 P2#9 pinning,不在注册内改生产形状)
   - rag_evidence_bundle.v1(commit 8802f24ca + 967acf9ca)**【DONE 2026-06-14: consolidation 重构】** 此前 4 站点内联组装、形状各异(kbv5 14 / supabase 14+6后置 / fallback 10 / historical 16),无单一权威。治本(非治标):新建 `deeptutor/services/rag/evidence_bundle.py` 的 `EvidenceBundle` dataclass + `build_evidence_bundle()` 单一 builder,4 站点全改调它;跨消费者契约=顶层 14 字段,lane 专属诊断收进 1 个 `trace` 桶(非删除=零诊断损失);bundle_id 统一确定性算法;~10 死字段移 trace。注册 T2 **PINNED**(canonical_fields=15 dataclass 字段)+ robust 内省对账 + test_evidence_bundle.py 单元测试。**调查**:2 个独立专家穷举消费者×字段矩阵+控制流(lane 互斥/fallback 是 llamaindex 默认 builder)。**对抗审查**:2 专家证伪——无悄悄字段 break(每个移走字段从 trace/独立源读)、单一权威生产路径完整(全树 1 处 EvidenceBundle 构造、无 live 绕过 service.search);修 1 个 latent(B2:status/degraded 自卫,防未来 override 矛盾)。**不确定性**:bundle_id 外部 Langfuse/BI join(Python 树外未审计)。
9. 增量钉 T2 字段:高频契约(context_pack.v1/rich_leaf_context_bundle.v1)`needs_field_canonicalization=false` + canonical 字段表,字段漂移变 BLOCKING(在 schema_ok 接好后)。**【DONE 2026-06-14, commit 9cab6d5ac】** 两条 T2 加 canonical_fields + flip false:context_pack.v1=LubanContextPack 9 dataclass 字段、rich_leaf_context_bundle.v1=`_RECORD_FIELDS` 8 per-record 字段。加 **robust 内省对账测试**(producer `__dataclass_fields__`/`_RECORD_FIELDS` == registry canonical_fields,非脆弱 regex)进 test_schema_registry.py(smoke-allowlisted,CI BLOCKING;已验判别力非假绿)+ registry 一致性测试(PINNED 必列字段表/unpinned 不得列)。零新 guard 机制。

**P3**
10. 去重 5 个路由 pydantic 类 + 建统一响应 envelope,把 api/router schema 面纳入 contract-guard 域。
11. **【DONE 2026-06-14, commit 5dcc1c498】建了元 registry** `contracts/registries.yaml`(25 个治理 scanner 单一目录,按 enforcement 分类)+ `check_registries_meta.py` 元闸:CI 失败若(a)有治理 scanner 未登记(register-before-use 也管闸自己),或(b)pr_gate-class 没真接 CI(无 dark pr_gate)。复用同一 runner 不加第二套权威。TDD 4 条 + 进 CI。剩:AGENTS.md 写明判分-only scope 边界(待 P0#1 一并)。
12. 修 dead `test_prompt_parity`(重指 deeptutor/agents/)或加 prompt 输出字段 vs 消费 pydantic 的 diff scanner。

## 3b. 对抗审查暴露的闭包诚实化(2026-06-14, commit 7416a04d9)

放出 5 个独立对抗专家复审本会话工作。3 个视角证伪指控(行为保持 ✓ / 无第二权威 ✓ / 5 个 T2 真跨消费无 fig-leaf ✓ / 6 commit 零并行 WIP 污染 ✓)。**但闭包/计数专家打破了"CLOSED 183"前提**:全集靠字符串巧合省略了两类真持久化 schema id —
- **Leak A**: 11 个 `luban-`(连字符)`schema_version` 逃逸 namespace(首支 `luban[_.]` 不认连字符);
- **Leak B**: 1 个 `artifact_version=` 键不在 marker 集。

12 个全是 would-be orphan,因 dash vs underscore 字符串巧合静默逃逸 → 闭包测试(只对集内断言 orphans=[])抓不到这种"消失式"漏。**已治本修复**(纯治理工具,核心分类逻辑零改动):namespace `luban[-_.]`(tight,实测不误收 model 名) + marker 加 `artifact_version` + 8 个 tight 脚本族 T3 carve-out + 回归钉子测试。闭包重新诚实 CLOSED **195=9+26+160**。

**代码审查补修(2026-06-14, commit 后述)**:
- **[已修] grading-shaped 一票否决边界同步放宽**:闭包诚实化把 namespace 放宽到 `luban[-_.]`(认连字符),但 `_GRADING_SHAPED_RE` 的边界类 `[_.]` 当时没同步——导致 dash grading-shaped id(`luban-consensus-grading_object.v1`,⊃ `luban-consensus` T3 族)会绕过 veto 被吞进 T3(veto 的唯一职责"判分 typed 对象永不 ephemeral"被破)。已把边界改 `[-_.]` + 加回归测试。当前树无此 id,但放宽 namespace 必须同步放宽 veto(越核心越细心)。
- **[已修] 陈旧 docstring**:`check_schema_registry.py` 顶部"PENDING HUNK / NOT wired into main()"在 P0#1(46c9379e9)接线后已成活谎言,改为 WIRED 说明。

**残留弱点(对抗审查记录,诚实不提前解决)**:
- T3 carve-out 对**非判分** runtime 契约偏宽:一个未注册的 `luban_xxx_decision.v1`/`_report`/`_feedback` 假想契约会被通用词 pattern 静默判 T3 而非 orphan(grading-shaped 一票否决只护 `grading_object`/`scoring_point`;上面那条修复让它也护 dash 形,但仍只护判分 typed 对象,**非判分**契约无保护)。当前树上**无**此类 id 被误吞,故不提前加 T2-veto 机制(避免为明天的问题过度设计);若未来出现非判分 runtime 契约,需给它一个 namespace 分支或在 carve-out 前加 T2-shaped veto。
- `luban_grading_engine_v1_*` / `luban_case_rubric_v1` 是 **engine-authority 枚举**(非 schema-version),deep_question 写、beta_shadow_loader/adjudicator 读做 grading `authority`。**不是闭包 gap,不可注册**(否则误报洪水)。若要治理 engine-authority 词表,是独立 T2-style 决策。

## 4. 注意事项(执行时)

- 多个 P0/P1 目标文件正被并行 agent 改(`check_contract_guard.py`、`tests.yml`、`contracts/index.yaml` 当前 dirty WIP)——接线前必须查 `git status`,用 `--only`/path-limited 提交,别扫并行 WIP(AGENTS §3.6)。
- P0#1 改的是中央 guard,`check_contract_guard.py` 是 protected——改它要同步更新 domain test(AGENTS §3.5),合并前跑 `check_contract_guard.py`。
- 全程 review-only 不碰生产判分;这是治理基础设施,不是判分逻辑。
- **闭包"CLOSED"的诚实性取决于收集层无逃逸**:任何新 schema-id 命名方案(新 namespace 前缀 / 新承载 key)出现时,必须确认 `_FULLSET_NAMESPACE_RE` + `_FULLSET_LITERAL_RE` 收得到,否则 CLOSED 是省略出来的假象(见 §3b)。
