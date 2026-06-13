# 基础设施 / 资源层 "登记才能用" 缺口审计 (INFRA registration coverage)

> Date: 2026-06-13  Scope: **infra / 资源层**(数据库连接、外部 provider、凭据、长驻进程、env/flag、REST transport)。
> 刻意**不重复**另一并行 audit 的 schema / typed-object / truth-source / ID 那几类。本 audit 只看
> "共享 + 持久/跨 agent 的资源,一个没登记或重复 → 数据分裂 / 漂移 / 第二权威 / 凭据成本失控 / 进程事故"。
>
> 参照系(blast radius 锚点):**今天的 Supabase 双项目意外**——learner 表落 `zgup…` 项目、知识表落另一项目、
> 还有一个裸 `SUPABASE_URL`。这种"哪个 fact 落哪个库"没有机器登记,就是本 audit 反复出现的根因。

判别口径:**确认有机器闸门的不误报;拿不准的标 `needs_verification`。**

---

## 已存在的机器闸门(诚实基线,不要误报成缺口)

先把**已经有闸**的列清楚,缺口表只列这些闸**覆盖不到**的资源。

| 闸门 | 文件 | 守什么 | 在 CI? |
|---|---|---|---|
| WebSocket 单控制面 allowlist | `scripts/ci/check_websocket_route_allowlist.py` + `contracts/index.yaml:websocket_routes` | 反射 FastAPI app,新增 WS 路由必须登记;chat kind 只允许 1 条且必须 `/api/v1/ws` | ✅ blocking |
| Secure router(REST 鉴权) | `scripts/ci/check_secure_routers.sh` + `runtime_route_inventory.py` | 禁裸 `APIRouter(`;反射枚举匿名端点 | ✅(inventory 仅 report-only) |
| LLM SDK 工厂单一 | `scripts/ci/check_llm_client_factory.sh` | 禁在 `openai_http_client.py` 之外直接 `AsyncOpenAI()/AsyncAnthropic()`(为了统一 timeout) | ✅ |
| RLS-on-create-table | `scripts/ci/check_rls_on_create_table.sh` | `supabase/migrations/**` 里每个 `create table public.X` 必须同文件 enable RLS | ✅ FAIL_ON_NEW |
| Migration 唯一/单调 | `scripts/ci/check_migration_uniqueness.sh` | 迁移时间戳唯一 + 单调 | ✅ |
| Live RLS 回归 | `check_live_rls_regression.sh` / `live_rls_audit.sh` | 监控 PII 表不得 grant anon | ✅(有 secret 时) |
| Secret 扫描 | `detect-secrets` baseline `.secrets.baseline` + "no tracked .env" | 新增未登记明文 secret → fail | ✅ blocking |
| 生产 secret fail-closed | `scripts/check_secret_envs.py` | prod 下 `DEEPTUTOR_ATTEMPT_REF_SECRET` 必须设且 ≥32 | ✅(deploy gate) |
| Model **默认** 单一 | `scripts/check_model_authority.py` | 只守 `DEFAULT_LLM_MODEL/PROVIDER` 单点;**provider base_url / model literal scatter 自认 D5 债,未守** | guard 模式 |
| Rate-limit 单一 | `scripts/ci/check_rate_limit_single_authority.sh` | 限流逻辑单点 | ✅ |
| 运行环境 fail-closed | `deeptutor/services/runtime_env.py` | 非已知 dev 名 → 当 production(安全开关默认关) | runtime |
| 进程内存(仅 Next) | `agent-owned-next-guard.sh` | AI-agent 拥有的 `next dev` 进程树告警/kill | 本机脚本 |

**关键观察(这几个闸的盲区直接对应下面的缺口):**
- RLS/migration 闸**只认 `supabase/migrations/**` 这一个项目**——它根本不知道有 `KBV5_DB_URL` / `QUESTIONS_BANK_DB_URL` 等**别的 Supabase 项目**存在;别的库的建表它一行都看不到。
- `check_llm_client_factory.sh` 只管 **SDK 构造**,不管 `base_url=` 硬编码,也不管"新增一个 provider"。
- `runtime_route_inventory.py` 只为**鉴权**做基线(防匿名端点),**没有 REST 路由 allowlist**——新 REST 路由随便 `include_router`,不像 WS 那样必须登记。
- `check_secret_envs.py` 只校验 **1 个** 生产 secret;其余 80 个凭据 env 没有任何 "新增 secret 要登记" 的闸。

---

## 1. 数据库 / 表 / 数据存储(最高优先,用户点名)

### 现状(实测)

**无任何 "数据库/表登记表"。** 不存在一份说明 "哪个 fact 落哪个库、哪个是 canonical、谁能写" 的机器或文档登记。
grep `zgup|bsaa|table.*registry|which database` 在 `contracts/` 和 `docs/plan/鲁班knowql/` 全空(命中的都是 schema/contract 文档,不是 DB→项目映射)。

**多项目/多连接 env 实测(45×SUPABASE_URL / 24×KBV5_DB_URL / 12×QUESTIONS_BANK_DB_URL / 37×DATABASE_URL / 18×SUPABASE_DB_URL):**

| 资源/store | 连接 env 解析顺序(各自 ad-hoc) | 落哪个 DB |
|---|---|---|
| `notebook_card/store.py` | `NOTEBOOK_CARD_DATABASE_URL → DB_URL → DATABASE_URL` | 不确定 |
| `luban_feedback_store.py` | `FEEDBACK_DATABASE_URL → SUPABASE_DB_URL → DB_URL` | 不确定 |
| `invite_test_applications.py` | `INVITE_TEST_DATABASE_URL → SUPABASE_DB_URL → DB_URL` | 不确定 |
| `objective_governed_registry_extractor.py` | `QUESTIONS_BANK_DB_URL` | 题库项目 |
| `rag/pipelines/kbv5.py` / `benchmark/kb_v5_readonly_adapter.py` | `KBV5_DB_URL` | 知识项目(bsaa 类) |
| `member_console/service.py` | `db_url`(传入/各路 fallback) | 主项目(zgup 类) |

**没有中央 DB 客户端工厂**——每个 store 各自 `psycopg2.connect(self._database_url, …)`(实测 17+ 处 ad-hoc 连接点)。
`scripts/check_local_env.py` 只认**一个** prod host `zgupgizexqpwtajvghno.supabase.co` 配 `SUPABASE_URL`;它**不知道**
KBV5/QUESTIONS_BANK/feedback 应该指向哪个项目——所以"知识表落了第二项目"这类事它检测不到。

### Blast radius

**这正是今天 Supabase 双项目意外的结构性根因。** 共享 fallback `DB_URL` 被 3 个 store(notebook_card / feedback / invite_test)共用:
同一个 `DB_URL` 改一次,3 张语义无关的表的落点同时漂移。`QUESTIONS_BANK_DB_URL` 与 `KBV5_DB_URL` 与裸 `SUPABASE_URL`
分属不同项目,但没有任何登记说明"learner/wallet 写主项目、knowledge 写知识项目"——
**一个 ad-hoc `psycopg2.connect(os.getenv("DB_URL"))` 就能把本该进 A 项目的写,静默写进 B 项目**(= 第二权威 / 数据分裂),
而且**绕过 `supabase/migrations/**` 的 RLS 闸**(别的项目的表根本不在那个目录,RLS 可能全开 anon 都没人查)。

### 该建的闸(registry / 不变量)

1. **DB 项目登记表**`contracts/db_registry.yaml`:每个逻辑库 = `{project_ref, env_var, canonical_for:[fact…], writers:[service…], rls_baseline}`。
   一份"哪个 fact 落哪个库、谁能写"的单一权威。
2. **连接收口 + 静态闸**:像 `check_llm_client_factory.sh` 那样,禁止在中央 DB 工厂之外直接 `psycopg2.connect(`,
   强制 `connect()` 的 url 必须来自登记表里声明的 env_var(消灭裸 `os.getenv("DB_URL")` fallback 链)。
3. **跨项目 DDL 闸延伸**:RLS/migration 闸目前盲区 = 非 `supabase/migrations/**` 的项目。登记表要标注每个项目的 migration 目录,
   闸按项目分别扫,堵住"在别的项目 ad-hoc 建表/改列绕过 RLS"。

### 优先级:**P0**(用户点名 + 今天已真实发生双项目意外 + blast radius = 静默数据分裂/第二权威)

---

## 2. 外部服务 / LLM provider / 第三方集成

### 现状(实测)

**存在 provider registry,但有三套并存(= 第二/第三权威),且仍被硬编码 base_url 旁路。**

三个独立 provider registry,各自声明同一批 provider 的 `default_api_base`:
- `deeptutor/tutorbot/providers/registry.py`(deepseek `api.deepseek.com` / glm `open.bigmodel.cn` / dashscope)
- `deeptutor/services/provider_registry.py`(openai/deepseek/glm/dashscope 又一份 `default_api_base`)
- `deeptutor/services/config/provider_runtime.py`(dashscope/openai 又一份)

**硬编码 base_url 直接旁路 registry**(实测,非 test):
- `capabilities/deep_question.py:2020` `base_url="https://api.deepseek.com"`
- `construction_grading/runtime_llm_adjudicator.py:297` dashscope 硬编码
- `construction_grading/artifact_first_llm_judge.py:511` `https://api.deepseek.com`
- `services/llm/factory.py:754/767`、`cloud_provider.py:275/410`、`observability/deepseek_billing.py`、
  `rag/pipelines/kbv5.py:73`、`photo_answer/engines/qwen_vl_ocr.py:26` 等。

**新增 provider 没有登记闸**:`check_llm_client_factory.sh` 只禁 SDK 构造,不管 base_url 硬编码,也不强制走 registry。
凭据侧实测 **81 个** credential env 名,其中外部 LLM/搜索/OCR provider 的 key 散落:DEEPSEEK / DASHSCOPE / OPENAI /
ANTHROPIC / GEMINI / GROQ / MISTRAL / MOONSHOT / COHERE / BRAVE / TAVILY / JINA / PERPLEXITY / BAIDU_OCR / MINIMAX / STEPFUN / QIANFAN…

### Blast radius

三套 registry + 散落硬编码 → **改一个 provider 的 base_url 要改 4+ 处**,漏一处就半数调用打到旧/错端点(成本归错账、限流/billing 对不上;
今天 BI 已经踩过 deepseek billing 对账偏差)。任意脚本 ad-hoc 加一个新 provider + 硬编码 key,**没有任何登记/成本可见性**——
凭据 sprawl + 成本失控(与"哪个库写哪"同构:这里是"哪个 provider 花了多少钱"无人登记)。

### 该建的闸

1. **单一 provider registry**:合并三套到一处(选 `services/provider_registry.py` 为权威),其余两套降级为 import-only adapter。
2. **base_url 硬编码闸**:静态 grep 禁止 `base_url="https://…"` 字面量出现在 registry 之外(白名单 = registry 文件),逼所有调用 `provider_runtime` 取。
3. **新增 provider 登记闸**:registry 是唯一 `ProviderSpec` 来源;新 provider key env 必须同时登入凭据登记(见 §3),让成本可归集。

### 优先级:**P1**(第二/第三权威已成形 + 凭据/成本 sprawl + 已有对账偏差先例)

---

## 3. 密钥 / 凭据

### 现状(实测)

**无中央 secret 管理 / 无 "新增 secret 要登记" 闸。** 凭据通过散落 `os.getenv(...)` 直接读取(81 个 credential env 名)。
`env_store.py` 是读取层,但其 `ENV_KEY_ORDER` 只是**显示排序**的元组,**不是 allowlist / 不是登记表**——任何新 key 都能裸读。
唯一的 secret 闸是:`detect-secrets`(防明文 commit)+ `check_secret_envs.py`(只校验 **1 个** 生产 secret)。
**这两者都不构成 "凭据清单"**——没有一处声明"系统需要哪些 secret、各属哪个服务、谁负责轮换"。

`.env.example` 只声明 52 个 key,代码引用 230 个(见 §5),其中大量 secret(ALIYUN_SMS_*、BAILIAN_BILLING_*、
BAIDU_OCR_*、多个 *_API_KEY)**根本没出现在 .env.example**——即未登记。

### Blast radius

凭据散落且无清单 → **没人知道系统到底依赖多少 secret、哪些过期了、泄露后要轮换哪些**。
一个静默失效的 key(如 ALIYUN_SMS)→ 注册/找回流程在生产无声降级。新增第三方集成时凭据随手 `os.getenv` 加,**绕过任何成本/安全审查**。
与 provider sprawl 叠加 = 凭据成本双失控。

### 该建的闸

1. **凭据登记表**`contracts/secrets_registry.yaml`:每个 secret = `{env_var, owner_service, external_provider, required_in:[prod/staging…], rotation_note}`。
2. **登记即校验**:把 `check_secret_envs.py` 从硬编码 1 个改为**读登记表**——prod 下所有 `required_in: [prod]` 的 secret 缺失即 fail-closed。
3. **新增 secret 闸**:代码引用一个名字含 `API_KEY/SECRET/ACCESS_KEY/TOKEN` 的 env 而登记表没有 → CI fail(与 §5 env 登记复用同一扫描)。

### 优先级:**P1**(安全 + 成本;与 §2 共用登记基础设施)

---

## 4. 后台进程 / 定时任务 / 长驻服务

### 现状(实测)

- **GitHub Actions cron(4 条,有版本可见)**:`wallet-consistency-cron.yml`、`hermes-upstream.yml`、`runtime-drill.yml`、`runtime-ops.yml`。这些在仓库内、可见、可审。
- **应用内 cron / 长驻**:`deeptutor/tutorbot/cron/service.py`(croniter 调度器,TutorBot agent 内部)、`heartbeat/service.py`(`asyncio.create_task` 心跳循环)、`channels/matrix.py` sync loop、`agent/team/__init__.py` worker、`agent/loop.py` self-restart `asyncio.create_task(_do_restart())`、`subagent.py` 后台任务。这些**没有统一登记表**说明"系统跑着哪些长驻 task、各自归谁、出事怎么停"。
- **docker-compose 长驻**:`deeptutor` / `searxng` / `valkey`(`restart: unless-stopped`)——这是受管的、可见的。
- **内存进程守护**:只有 `agent-owned-next-guard.sh` 守 Next。**别的长驻类型(python worker / heartbeat / agent cron / valkey)没有等价守护**。

### Blast radius

参照 2026-06-06 的 Next 事故(Claude 拥有的进程树被 Jetsam 记为 ~201.6 GB / 3927 node):**只有 Next 有守护,
其余长驻 task 一旦泄漏(heartbeat / cron / team worker 不断 create_task 不回收)同样能拖垮内存/句柄,且无闸提醒。**
应用内 `asyncio.create_task` 散落且无登记 → 难以审计"现在有多少后台 task 在跑、哪些是泄漏"。

### 该建的闸

1. **长驻进程/任务登记**:一份 `long_running_processes.md`/yaml 登记每个 daemon-shaped 资源(GHA cron / 应用内 task / compose 服务)= `{name, owner, lifecycle, stop_procedure}`。
2. **内存守护泛化**:把 `agent-owned-next-guard` 的思路扩到 "AI-agent-owned python/worker 进程树" 的 check(至少告警阈值)。
3. **`asyncio.create_task` 收口**:长驻 task 统一经一个 registry/supervisor 创建,便于枚举与回收(优先级低于 1/2)。

### 优先级:**P2**(已有一次真实进程事故先例,但 GHA cron 那部分已可见;盲区在应用内 task 与非 Next 长驻)

---

## 5. 环境变量 / feature flag / 配置开关

### 现状(实测)

- **代码引用 230 个 distinct env key,`.env.example` 只声明 52 个 → ~178 个未登记裸 env。**
- **feature flag 实测 33+ 个** `*_ENABLED / *_SHADOW / *_ROLLOUT / *_FORCE_ON`(LUBAN_V1_* 一族、SUPABASE_RAG_* 一族、DEEPTUTOR_*_ENABLED 一族…),**无中央 flag registry**。
- `runtime_env.py` 的 `env_flag()` 是统一**读取**入口(好),但它**不持有合法 flag 清单**——任何字符串都能当 flag 读。`env_store.ENV_KEY_ORDER` 只排序、不约束。
- 唯一接近"登记"的是 `runtime_only_keys`(任务里提到的)——但那是 fail-closed 安全开关的窄集合,**不覆盖一般 flag/env**。

### Blast radius

178 个未登记 env + 33 个裸 flag → **flag 泛滥实测严重**。没有清单 → 没人知道哪些 flag 还活着、哪些 shadow/rollout 早该收。
一个拼错的 flag 名静默走 default(`env_flag` 返回 default)→ 灰度看似生效实则没生效(本项目 KB v5 灰度、LUBAN_V1 灰度都靠这类 flag,
拼错 = 假灰度,与 learner 记忆库的"假绿"同构)。env 落点漂移(§1 的 DB_URL)也是这类无登记 env 的子集。

### 该建的闸

1. **flag/config 登记表**`contracts/runtime_flags.yaml`:每个 flag = `{name, default, owner, kind:[killswitch/rollout/shadow], sunset}`;
   `env_flag(name)` 调用时断言 name 在登记表(像 schema_registry 那样 "registered-or-can't-use")。
2. **env 引用扫描闸**:CI 扫 `os.getenv/env_store.get/env_flag` 的字面 key,不在 `.env.example`∪登记表 → fail(同时关掉 §3 secret 缺口)。
3. **sunset 治理**:shadow/rollout flag 必须带 sunset 日期,过期 CI 提醒(治 flag 泛滥)。

### 优先级:**P1**(泛滥规模最大 178+33;假灰度直接威胁灰度发布正确性)

---

## 6. API 端点 / 路由 / transport

### 现状(实测)

- **WebSocket**:有登记闸(`contracts/index.yaml:websocket_routes` + allowlist 脚本),覆盖良好——✅ **不是缺口**。
- **REST 路由**:**有鉴权闸(secure_router 静态 + runtime_route_inventory 反射基线),但没有 "新 REST 路由必须登记" 的 allowlist。** `deeptutor/api/main.py` 里 ~30 条 `include_router(...)` 自由增减,只要不裸 `APIRouter(`、挂上鉴权 dep 即通过。`runtime_route_inventory.py` 自述 **report-only**(只防匿名端点回归,不防"新增了一条没人登记的端点")。
- **其它 transport**:`channels/`(matrix/telegram/slack)、`agent/tools/web.py`(SEARXNG)、photo_answer 外呼——这些 egress/channel 没有统一 transport 登记。

### Blast radius

REST 端点能静默增多 → API surface 蔓延、契约/文档漂移(新端点没进任何 manifest,前端/小程序/BI 各自对接,
形成第二事实来源)。比 WS 的 blast radius 小(WS 是聊天单控制面,REST 多为读模型),但"端点该不该存在"无登记 = 治理盲区。

### 该建的闸

1. **REST 路由 allowlist**:把 `runtime_route_inventory.py` 从 report-only 升级为闸 —— 新出现的 `app.routes` 路径必须登记进
   `contracts/index.yaml` 的一个 `http_routes` 段(复用 WS allowlist 的反射+登记模式)。
2. **channel/egress 登记**:matrix/telegram/slack/searxng 等出站 transport 登记 `{name, direction, credential_ref}`,与 §3 凭据登记关联。

### 优先级:**P2**(WS 已守住主面;REST 有鉴权兜底,缺的是"存在性登记",blast radius 中等)

---

## 缺口总表

| # | 资源类 | 现状靠什么守 | Blast radius(以双项目意外为参照) | 该建的闸 | 优先级 |
|---|---|---|---|---|---|
| 1 | **DB / 表 / 数据存储** | **无登记表;无中央连接工厂**;RLS/migration 闸只认单一项目目录 | **= 双项目意外本身**:共享 `DB_URL` fallback 3 store 共用、跨项目 ad-hoc 连接静默写错库 → 数据分裂/第二权威,且绕过 RLS 闸 | DB 项目登记表 + 连接收口静态闸 + 跨项目 DDL/RLS 闸 | **P0** |
| 2 | **外部 provider / LLM** | 有 registry 但**三套并存** + 硬编码 base_url 旁路;工厂闸只管 SDK 构造 | 改 base_url 要改 4+ 处,漏一处打错端点 → 成本归错账(已有 deepseek 对账偏差);ad-hoc 新 provider 无成本可见性 | 合并为单一 registry + base_url 硬编码闸 + 新 provider 登记闸 | P1 |
| 3 | **密钥 / 凭据** | 无中央管理;`detect-secrets`(防明文)+ 仅校验 1 个 prod secret | 81 个凭据散落、无清单 → 不知依赖多少 secret/哪些失效/泄露轮换哪些;新集成随手加 key 绕审查 | 凭据登记表 + 登记驱动的 fail-closed 校验 + 新 secret 闸 | P1 |
| 4 | **后台进程 / 长驻** | GHA cron 可见;**应用内 cron/heartbeat/team-worker/create_task 无登记**;内存守护只覆盖 Next | 参照 Next 201.6GB 事故:非 Next 长驻泄漏同样拖垮内存且无闸;散落 create_task 难审计 | 长驻进程登记 + 内存守护泛化到 python worker + create_task 收口 | P2 |
| 5 | **env / feature flag** | `env_flag/env_store` 统一读取但**不持合法清单**;`runtime_only_keys` 仅窄安全集 | 178 未登记 env + 33 裸 flag;拼错 flag 静默走 default → **假灰度**(威胁 KB v5 / LUBAN_V1 灰度正确性) | flag/config 登记表 + env 引用扫描闸 + shadow/rollout sunset 治理 | P1 |
| 6 | **REST / transport** | WS 有 allowlist(✅);REST 有鉴权闸但**无存在性 allowlist**(inventory report-only);channel/egress 无登记 | REST 端点静默蔓延 → 契约漂移、前端/小程序/BI 各自对接形成第二事实来源(blast radius 中) | REST 路由 allowlist(升级 inventory 为闸)+ channel/egress 登记 | P2 |

---

## Top 3 最该先堵

1. **DB 项目/表登记表 + 连接收口(§1, P0)** —— 用户点名,且**今天已真实发生**双项目意外。
   没有这道闸,"哪个 fact 落哪个库 / 谁能写"永远是口口相传,下一次跨项目误写只是时间问题,
   且会**绕过现有 RLS 闸**(别的项目根本不在 `supabase/migrations/**` 视野内)。建登记表 + 禁裸 `psycopg2.connect`,一并把 RLS 闸延伸到所有登记项目。

2. **env / flag 登记 + 引用扫描闸(§5, P1)** —— 规模最大(178 未登记 env + 33 裸 flag),
   且直接威胁**灰度发布正确性**(拼错 flag = 假灰度,与 learner "假绿" 同构)。这一道闸**顺带关掉 §3 的 secret 未登记缺口**(secret 是 env 的子集),性价比最高。

3. **Provider registry 合并 + base_url 硬编码闸(§2, P1)** —— 第二/第三权威**已经成形**(三套 registry 并存),
   不是预防而是**止血**;且已有 deepseek billing 对账偏差先例,成本归集依赖它收口。

---

## 一句话总结

> **Infra 层还差 4 道闸**:DB 项目/表登记(P0,最痛、已出事)、env/flag 登记(P1,规模最大、致假灰度)、
> provider 单一权威收口(P1,三套已并存、成本归错账)、凭据登记(P1,可与 env 闸合并)。
> 长驻进程登记与 REST 存在性 allowlist 是 P2 收尾。
> 当前 infra 的机器闸门只覆盖了 **WS 单控制面、SDK 工厂、单一项目的 RLS/migration、明文 secret 扫描** ——
> 凡是 **"哪个库 / 哪个 provider / 哪个 secret / 哪个 flag / 哪个长驻 task"** 这类"共享资源归属"问题,**几乎都没有登记闸**,
> 与 schema/typed-object 层已建的 `schema_registry.yaml`(注:该 schema 闸自身还**未 wire 进 contract_guard**)形成对照——资源层的登记基础设施整体落后于数据层。
