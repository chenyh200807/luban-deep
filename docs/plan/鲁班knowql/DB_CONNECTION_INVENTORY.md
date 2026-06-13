# DB 连接拓扑盘点（只读，零行为改动）

> Step 1 of `RESOURCE_GOVERNANCE_FIX_PLAN.md` Layer 1 · P0。
> **本文档是只读盘点**：列出每个连库点连哪个库(env)、为哪个一等业务事实(fact)、读还是写、走不走 RLS。
> 不改任何连接行为。`needs_verification` 标记 = 存活性/职责未经运行时核实，靠静态阅读推断。
>
> 方法：`grep psycopg2.connect|psycopg.connect`（无 asyncpg / sqlalchemy / supabase-py 客户端）+ 逐处读连接上下文。
> 盘点时点的 HEAD：`feat/luban-arbitration-gold-panel`。

## 0. 一句话结论

- **两种连接模态并存**：
  1. **Supabase REST（PostgREST over HTTP）**——`SUPABASE_URL` + service-role key，**走 RLS**（PostgREST 以 JWT/role 执行，策略生效）。
  2. **直连 Postgres（raw psycopg/psycopg2）**——各种 `*_DATABASE_URL` / `DB_URL` / `DATABASE_URL` / `KBV5_DB_URL` / `QUESTIONS_BANK_DB_URL`，**以 DB role 直连，结构性绕过 RLS**（RLS 只对非 superuser、非 `BYPASSRLS` role 生效；直连用的 role 通常有写权且不带 RLS app-claims）。
- **同一份业务事实经常有两条写路径**（REST + 直连 fallback），它们指向的库由不同 env 解析 → 这正是「跨库静默写错 + 绕 RLS」的结构性根因，也是 Supabase 双项目意外的来源。
- **4+ 个 DB-URL env 命名空间**：`SUPABASE_URL`(+key)、`KBV5_DB_URL`、`QUESTIONS_BANK_DB_URL`、`DATABASE_URL`/`DB_URL`（被 3+ store 当作共享 fallback）。
- **没有任何统一 connection factory**：15 个文件各自 `import psycopg2; psycopg2.connect(...)`。

## 1. DB-URL env 命名空间（解析点 = 选库点）

| env 名 | 解析它的代码 | 指向的库（推断） | 存活性 |
|---|---|---|---|
| `SUPABASE_URL` (+ `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_KEY` / `SUPABASE_ANON_KEY`) | 全部 REST store（learner_state/*、member_console/*、wallet/*、assessment/*、notebook_card、invite、luban_feedback、rag/pipelines/supabase、feedback_service） | 主应用 Supabase 项目（REST + RLS） | 在用 |
| `DATABASE_URL` / `DB_URL` | member_console（phone identity）、notebook_card Postgres store、luban_feedback `FEEDBACK_DATABASE_URL` fallback、invite `SUPABASE_DB_URL`/`DB_URL` fallback、export_canonical_knowledge_to_supabase、run_luban_m26_live_closure | 主应用 Postgres（同一 Supabase 项目的直连 5432/pooler） | 在用（3+ store 共享 fallback） |
| `KBV5_DB_URL` | benchmark/kb_v5_readonly_adapter、rag/pipelines/kbv5、config/knowledge_base_config（仅探活） | KB v5 知识库（向量检索库 `search_chunks_v2`） | 在用 |
| `QUESTIONS_BANK_DB_URL` | construction_grading/objective_governed_registry_extractor、（compiler 用入参 db_url，常由调用方填同库） | 题库 `questions_bank` | `needs_verification`（线上 status 报 `live_blocker: QUESTIONS_BANK_DB_URL absent`，疑似尚未配置/仍走 fixture） |
| `INVITE_TEST_DATABASE_URL` / `SUPABASE_DB_URL` | invite_test_applications fallback | 同主应用 Postgres | `needs_verification`（多为 REST 路径在用，直连 fallback 是否触发未核实） |
| `FEEDBACK_DATABASE_URL` | luban_feedback_store fallback | 同主应用 Postgres | `needs_verification` |
| `NOTEBOOK_CARD_DATABASE_URL` | notebook_card PostgresStore fallback | 同主应用 Postgres | `needs_verification` |

> ⚠️ **歧义点**：`DATABASE_URL`、`SUPABASE_DB_URL`、`*_DATABASE_URL`、`DB_URL` 之间没有任何机器约束保证它们指向**同一个** Supabase 项目。三个 store 把 `DB_URL` 当共享 fallback，但 `KBV5_DB_URL`/`QUESTIONS_BANK_DB_URL` 是**另外的库**。一旦 .env 里某个 url 指错项目，写就静默落到错库——无机器闸拦截。

## 2. 连接点逐处（15 个文件，直连 psycopg）

> RLS 列：**bypass** = raw psycopg 直连，以 DB role 执行，不带 app-level RLS claims，结构性绕 RLS。
> **rest+rls** = 同 store 另有一条 PostgREST 路径走 RLS。

### 2.1 写路径（最危险 — 收口优先级最高）

| # | 文件:行 | env→库 | fact（一等业务事实） | 表 | 读/写 | RLS |
|---|---|---|---|---|---|---|
| W1 | `member_console/service.py:6621,6628,6632` | `DB_URL`/`DATABASE_URL` → 主应用 PG | 用户手机↔canonical UID 身份别名 | `public.user_identity_aliases`, `public.users` | **写** (UPSERT) | bypass |
| W2 | `notebook_card/store.py:188,213` | `NOTEBOOK_CARD_DATABASE_URL`/`DB_URL`/`DATABASE_URL` → 主应用 PG | 学习者笔记卡（learner brain 输入） | `public.learner_notebook_cards` | **写** (INSERT) | bypass（另有 REST+RLS 路径同表 :101-120） |
| W3 | `luban_feedback_store.py:417,442` | `FEEDBACK_DATABASE_URL`/`SUPABASE_DB_URL`/`DB_URL` → 主应用 PG | 鲁班用户反馈跟进状态 | `public.luban_feedback` | **写** (UPDATE) | bypass（另有 REST+RLS :394） |
| W4 | `invite_test_applications.py:745,762,830` | `INVITE_TEST_DATABASE_URL`/`SUPABASE_DB_URL`/`DB_URL` → 主应用 PG | 内测申请记录 | `public.invite_test_applications` | **写** (INSERT/UPDATE) | bypass（另有 REST+RLS :608-665） |
| W5 | `scripts/export_canonical_knowledge_to_supabase.py:123` | `DATABASE_URL`/`DB_URL` → 主应用 PG | canonical 知识图谱（taxonomy/catalog/edges） | `concept_taxonomy_*`, catalog 表（DDL+全刷+UPSERT） | **写** (DDL+DELETE+INSERT) | bypass（运维脚本） |
| W6 | `scripts/run_luban_m26_live_closure.py:148` | `DATABASE_URL`/`DB_URL` → 主应用 PG | 鲁班 M26 闭环 | `needs_verification` | **写** `needs_verification` | bypass（运维脚本） |
| W7 | `scripts/backfill_phone_identity.py:173,178` | `DB_URL`/`DATABASE_URL` → 主应用 PG | 手机身份回填 | `user_identity_aliases` | **写** (backfill) | bypass（运维脚本） |
| W8 | `scripts/backfill_2026_textbook_chunk_metadata.py:233` | `db_url`(入参) → `needs_verification` | 教材 chunk 元数据回填 | `needs_verification` | **写** | bypass（运维脚本） |

### 2.2 只读路径（风险次之；多数已 `set_session(readonly=True)`）

| # | 文件:行 | env→库 | fact | 表/函数 | 读/写 | RLS |
|---|---|---|---|---|---|---|
| R1 | `benchmark/kb_v5_readonly_adapter.py:127` | `KBV5_DB_URL` → KB v5 | KB v5 向量检索 | `public.search_chunks_v2()` | 读（硬 readonly） | bypass |
| R2 | `rag/pipelines/kbv5.py:168` | `KBV5_DB_URL` → KB v5 | KB v5 RAG 检索 | `search_chunks_v2` 等 | 读 | bypass |
| R3 | `construction_grading/objective_governed_registry_extractor.py:131` | `QUESTIONS_BANK_DB_URL` → 题库 | 客观题 governed 抽取 | `questions_bank` | 读（硬 readonly） | bypass |
| R4 | `construction_grading/full_knowledge_compiler.py:640` | `db_url`(入参，常=题库) | 全量客观题编译 | `public.questions_bank` | 读（硬 readonly） | bypass |
| R5 | `luban_feedback_store.py:350,375` | 同 W3 env | 反馈列表读取 | `public.luban_feedback` | 读 | bypass（另有 REST :324） |
| R6 | `invite_test_applications.py:697,722,783` | 同 W4 env | 内测申请读取 | `public.invite_test_applications` | 读 | bypass（另有 REST） |
| R7 | `scripts/export_kb_v5_full_to_runtime_supply.py:67` | `db_url`(入参) → KB v5 | KB v5 导出 runtime supply | KB v5 表 | 读（运维脚本） | bypass |
| R8 | `scripts/smoke_construction_grading_supabase.py:82` | url(入参/env) → 主应用 PG | 评分 smoke | smoke 表 | 读（运维脚本） | bypass |
| R9 | `scripts/audit_construction_grading_supabase_fields.py:93` | url → 主应用 PG | 字段审计 | 多表 | 读（运维脚本） | bypass |

## 3. RLS 覆盖结论

- **REST 路径（`SUPABASE_URL` + service key）**：走 PostgREST，RLS 策略生效。但 service-role key 本身在多数 store 里是 `SERVICE_ROLE_KEY`（service role 在 Supabase 默认 `BYPASSRLS`）——所以"走 RLS"对 service-role 调用**实际也被 bypass**，RLS 真正生效的是 anon/authenticated key 路径。`needs_verification`：各 store 实际注入的是 service-role 还是 anon。
- **直连路径（raw psycopg）**：**全部 bypass RLS**。15/15 直连点没有任何 RLS app-claims 注入，以 DB role 直接写。
- 因此 plan 所述「RLS 闸只看单一项目目录 → 跨库静默写错 + 绕 RLS」属实：**直连写是结构性绕 RLS 的，且选哪个库完全由 env 字符串决定，无机器校验。**

## 4. 不确定项（needs_verification）汇总

1. `QUESTIONS_BANK_DB_URL` 线上是否已配置（status 报 absent → 可能仍走 fixture，R3/R4 实际未连真库）。
2. 各 store 直连 fallback（W2/W3/W4 的 `*_DATABASE_URL`）线上是否真触发——还是 REST 路径恒在用、直连只是 cold path。需运行时确认。
3. W6/W8 的目标表与写语义（脚本，未逐字读全）。
4. REST store 实际注入 service-role（BYPASSRLS）还是 anon（RLS 生效）——影响"REST 走 RLS"的真伪。
5. `DATABASE_URL` vs `SUPABASE_DB_URL` vs `DB_URL` 是否保证同库——当前无机器约束，是双项目意外的高危面。

## 5. 收口候选（Step 4 详述）

- **最安全的样例迁移点**：R1 `kb_v5_readonly_adapter` —— 纯只读、已 `set_session(readonly=True)`、已有 `db_url` 注入口、独立库（KB v5），迁到 factory 行为最易证明不变。
- **最危险、最后迁**：W1/W5（身份别名 UPSERT、canonical 知识全刷）——触生产写，留 work order 分批。

## 6. 连接收口方案（Step 4）

### 6.1 connection factory（已建，thin wrapper）

`deeptutor/services/db/connection_factory.py`：`connect_for_fact(fact, *, db_url=None, readonly=False, timeout_s=20)`。
- **fact→库** 解析读 `contracts/db_registry.yaml`（与 CI 闸同一份清单），保留各站点现有 `db_url override → url_envs → fallback_url_envs` 的 env 优先序。
- **thin**：只做 url 解析 + 原 `psycopg.connect(url, connect_timeout=...)` + 可选 `set_session(readonly=True, autocommit=True)`。无连接池、无 ORM、无 retry。仿 `deeptutor/services/llm/factory.py`。
- **fail-closed**：未登记 fact / env 未设 → `DbResolutionError`，绝不静默连错库。

### 6.2 样例迁移（已做，1 处，行为不变）

R1 `kb_v5_readonly_adapter.retrieve` 的 `psycopg2.connect(url, 20)` + `set_session(readonly=True)` → `connect_for_fact("kb_v5_chunk_retrieval", db_url=db_url, readonly=True, timeout_s=20)`。
- 保留 `KBV5_DB_URL absent`→`KbV5Unavailable`、`psycopg2 unavailable`→`KbV5Unavailable` 两条错误语义（factory 的 `DbResolutionError`/`ImportError` 各自翻译回原异常）。
- 回归：`tests/scripts/test_luban_v0_vs_v1_ab_benchmark_m24.py` 等 14 个 kb_v5 测试全绿，含「pop KBV5_DB_URL → 必抛 KbV5Unavailable」。

### 6.3 存量分批迁移 work order（其余 14 处，**不一次性碰生产连接**）

| 批次 | 站点 | fact | 风险 | 迁移动作 |
|---|---|---|---|---|
| **B1 只读，低风险** | R2 `rag/pipelines/kbv5.py`、R3 objective extractor、R4 full_knowledge_compiler、R7 export_kb_v5、R8/R9 smoke/audit 脚本 | kb_v5 / governed_objective_question | 低（已 readonly） | 同 R1：`connect_for_fact(fact, db_url=…, readonly=True)`，逐个迁、逐个跑该模块测试 |
| **B2 写，中风险** | W2 notebook_card、W3 luban_feedback、W4 invite | learner_notebook_card / luban_feedback / invite_test_application | 中（有 REST fallback，直连是 cold path） | `connect_for_fact(fact, db_url=…)`（写不传 readonly）；先在 staging 触发直连 fallback 验证 |
| **B3 写，高风险（最后）** | W1 member_console 身份别名、W5 export_canonical 知识全刷、W6/W7/W8 运维脚本 | user_identity_alias / canonical_knowledge_catalog | 高（生产写、DDL、全刷） | 单独 PR、单独迁一处、影子验证；W5 全刷脚本需运维窗口 |

**铁律**：每批 = 独立小 PR，迁一处即跑该模块测试 + `python scripts/check_db_registry.py <file>`，绝不批量改所有生产连接。每迁完一处把它从 `databases[].raw_connection_sites[].status: grandfathered` 翻成 `migrated`（或挪进 `connection_factory.migrated_sites`），扫描器的 grandfathered 豁免随之收紧，防回潮。

## 7. 扫描器 + CI 接法

- `scripts/check_db_registry.py`，三条确定性 fail 规则：(a) 未登记的裸 `psycopg.connect`（非 factory、非 grandfathered）；(b) 写未登记表；(c) 引用未登记的 `*_DATABASE_URL`/`DB_URL` env。
- **接现有 contract-guard runner**：`check_contract_guard.py` 当前有并行 WIP（脏文件），故按 `check_schema_registry.py` 同样的 **pending hunk** 纪律——hunk 写在 `check_db_registry.py` 顶部 docstring，待该文件干净时接入 `main()` 的 `evaluate_db_registry(changed_files)`，**不夹带、不碰并行 WIP**。
- **已知扫描器局限（诚实标注）**：rule (b) 只能静态识别**字面表名**的写；用 f-string/`sql.Identifier` 动态拼表名的 4 处 writer（luban_feedback/notebook_card/invite 的 `update {_TABLE} set`、export 的 `sql.Identifier`）其表名不暴露给正则，rule (b) 漏；但这些 writer **全部开裸 psycopg 连接**，故被 rule (a) 覆盖——**新增的此类 writer 在新文件里仍会被 rule (a) 拦住**，止血价值成立。rule (b) 的价值是拦「字面 `insert into 新表`」这类最常见的新增写。
</content>
