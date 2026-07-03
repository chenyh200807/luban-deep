# env / feature-flag / 凭据 盘点分类 (read-only inventory)

> Date: 2026-06-13  Scope: **Layer 2 · P1** of `RESOURCE_GOVERNANCE_FIX_PLAN.md` §5 (env/flag) + §3 (凭据).
> 本文件只**盘点分类**,不改任何行为。它是 `contracts/env_registry.yaml`(canonical 清单)+
> `scripts/check_env_registry.py`(scanner)的来料。判别口径:**机器能确认的不误报;拿不准的标
> `needs_verification`(线上是否真在用、是否拼写漂移)。**
>
> 参照系(blast radius 锚点):**拼错一个 feature flag → `env_flag()` 静默返回 default → 灰度看似生效
> 实则没生效**(本项目 KB v5 灰度、LUBAN_V1 灰度都靠这类 flag)。这与 learner 记忆库的"假绿"同构。

---

## 0. 实测计数(机器盘点,可复现)

| 维度 | 实测 | grep 口径 |
|---|---|---|
| **distinct env key 引用**(`deeptutor/` + `scripts/` 生产源,排除 tests) | **284** | `os.getenv` / `os.environ[...]` / `env_store.get("X")` / `env_flag("X")` 字面 key |
| `.env.example` 声明 | **52** | `^[A-Z_]+=` |
| **未出现在 .env.example 的引用**(裸 env) | **245** | `comm -23` |
| **feature flag(布尔灰度开关)** | **~35**(下表 A) | 经 `env_flag()` 读取 = 机器确定 ∪ flag-shaped 后缀 |
| **凭据(secret kind)** | **45** | 名含 `API_KEY/_SECRET/_TOKEN/ACCESS_KEY/PASSWORD/SIGNING_KEY` 且语义是密钥(TTL 类排除) |

> 注:284 > audit 文档的 230,因本次 grep 把 `env_store.get` / `env_flag` 入口也并入(audit 只统计
> `os.getenv`)。两者不矛盾——284 是更完整的引用面。

---

## A. Feature flag(最危险类——拼错=假灰度)

**机器判据**:凡经 `runtime_env.env_flag("NAME")` 读取的 NAME 一定是布尔 flag(无视命名后缀)。
这是 registry scanner 拦"裸 flag"的**确定性信号**,比名字后缀启发式可靠——下表里
`ASSESSMENT_PREWARM_FORMS` / `QUESTION_LIFECYCLE_DECISION_AUTHORITY` / `LANGFUSE_CAPTURE_*` /
`MEMBER_CONSOLE_USE_REAL_SMS` 都**没有** `_ENABLED` 后缀,只有"被 `env_flag()` 读"这一条能抓到它们。

| flag | env_flag default | 灰度语义(kind) | 在用 | 备注 |
|---|---|---|---|---|
| `DEEPTUTOR_CONTEXT_ORCHESTRATION_ENABLED` | True | killswitch | ✅ | 默认开,关=回退 |
| `DEEPTUTOR_SEMANTIC_ROUTER_ENABLED` | True | killswitch | ✅ | |
| `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE` | False | shadow | ✅ | |
| `QUESTION_LIFECYCLE_DECISION_AUTHORITY` | True | killswitch | ✅ | 无 `_ENABLED` 后缀,靠 env_flag 抓到 |
| `DEEPTUTOR_HOME_NEXT_STEP_ENABLED` | False | rollout | ✅ | 融合计划 §3 home_next_step_projection(跨模式「下一步」呈现仲裁),默认 off,已登记 env_registry.yaml |
| `KBV5_RAG_ENABLED` | (无显式 default) | rollout | ✅ | **KB v5 灰度核心**,拼错=假灰度 |
| `SUPABASE_RAG_ENABLED` | False | rollout | ✅ | |
| `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_QUERY_PLAN_TRACE_ENABLED` | (无) | shadow | ✅ | |
| `SUPABASE_RAG_ENABLE_EXACT_QUESTION` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_ENABLE_RERANK` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_EXACT_QUESTION_TEXT_FIRST` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_INCLUDE_QUESTIONS` | True | rollout | ✅ | |
| `SUPABASE_RAG_QUERY_EXPANSION` | (无) | rollout | ✅ | |
| `SUPABASE_RAG_SECOND_PASS` | (无) | rollout | ✅ | |
| `LUBAN_V1_CONTROLLED_RUNTIME_ENABLED` | — | rollout | ✅ | **LUBAN_V1 灰度核心** |
| `LUBAN_V1_BETA_SHADOW_ENABLED` | — | shadow | ✅ | |
| `LUBAN_V1_LLM_ADJUDICATOR_ENABLED` | — | rollout | ✅ | |
| `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED` | — | rollout | ✅ | |
| `LUBAN_V1_LLM_ADJUDICATOR_DEV_FORCE_ON` | — | dev-force | ✅ | 仅 dev 强开 |
| `LUBAN_CASE_RUBRIC_V1_ENABLED` | — | rollout | ✅ | |
| `LUBAN_M31_GOVERNED_OBJECTIVE_ENABLED` | — | rollout | ✅ | |
| `LUBAN_M35_ARTIFACT_SHADOW_ENABLED` | — | shadow | ✅ | |
| `LUBAN_TEXTBOOK_KNOWLEDGE_ENABLED` | — | rollout | ✅ | |
| `LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED` | — | rollout | ✅ | |
| `LUBAN_LEARNING_EVIDENCE_AUTO_SYNTHESIS_ENABLED` | False | rollout | ✅ | |
| `LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED` | — | killswitch | ✅ | 反向(disabled 语义) |
| `ASSESSMENT_PREWARM_FORMS` | False | rollout | ✅ | 无 `_ENABLED`,靠 env_flag 抓 |
| `ASSESSMENT_USE_SUPABASE` | False | rollout | ✅ | 无 `_ENABLED` |
| `MEMBER_CONSOLE_USE_REAL_SMS` | False | killswitch | ✅ | 无 `_ENABLED`,关=用 mock SMS |
| `MEMBER_CONSOLE_USE_SUPABASE_MEMBER_DIRECTORY` | False | rollout | ✅ | |
| `DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED` | False | dev | ✅ | |
| `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA` | False | dev/qa | ✅ | |
| `DEEPTUTOR_ENABLE_API_DOCS` | — | config | ✅ | |
| `DEEPTUTOR_EXTERNAL_AUTH_ALLOW_LEGACY_DEFAULT` | False | killswitch | ✅ | 安全相关 |
| `DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK` | False | fallback | ✅ | |
| `DEEPTUTOR_DEMO_TOKENS_ENABLED` | — | dev | ✅ | 受 runtime_env fail-closed 兜 |
| `DEEPTUTOR_MISTAKE_BOOK_ENABLED` | — | rollout | needs_verification | 可能旧 flag |
| `DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED` | — | rollout | needs_verification | 可能旧 flag |
| `FF_EMBEDDING_CACHE_ENABLED` | — | rollout | ✅ | |
| `LANGFUSE_ENABLED` | — | killswitch | ✅ | |
| `LANGFUSE_CAPTURE_INPUT` | — | config | ✅ | 无 `_ENABLED` |
| `LANGFUSE_CAPTURE_OUTPUT` | — | config | ✅ | 无 `_ENABLED` |
| `LANGFUSE_DEBUG` | — | config | ✅ | |
| `LANGFUSE_MASK_PII` | — | config | ✅ | PII 相关 |
| `LANGFUSE_HTTPX_TRUST_ENV` | — | config | ✅ | |
| `DISABLE_SSL_VERIFY` | False | killswitch | ✅ | **安全**:开=禁用 SSL 校验 |
| `DEEPTUTOR_BI_PUBLIC_ENABLED` | — | killswitch | ✅ | BI 公开面板开关 |

> **不确定项(needs_verification)**:`DEEPTUTOR_MISTAKE_BOOK_ENABLED` / `*_WRITE_ENABLED` 线上是否仍消费未核实;
> 可能是早期 flag。**处置:仍登记**(grandfather),sunset 由后续 work order 判定——登记本身零行为改动,不冒进删。

---

## B. 凭据 / secret(并入 env_registry,不另建凭据系统)

45 个 credential env(名含 `API_KEY/_SECRET/_TOKEN/ACCESS_KEY/PASSWORD/SIGNING_KEY` 且语义为密钥)。
按外部 provider 聚类:

- **LLM/检索/OCR provider key**:`DEEPSEEK_API_KEY` `DASHSCOPE_API_KEY` `OPENAI_API_KEY`
  `DEEPTUTOR_OPENAI_API_KEY` `ANTHROPIC_API_KEY` `GROQ_API_KEY` `COHERE_API_KEY`
  `BRAVE_API_KEY` `TAVILY_API_KEY` `JINA_API_KEY` `BAIDU_OCR_API_KEY` `BAIDU_OCR_SECRET_KEY`
  `LLM_API_KEY` `EMBEDDING_API_KEY` `SEARCH_API_KEY` `DEEPSEEK_BILLING_API_KEY`
- **阿里云 SDK(三套变体,见 §D 拼写可疑)**:`ALIYUN_SMS_ACCESS_KEY_ID/_SECRET`
  `ALIBABA_CLOUD_ACCESS_KEY_ID/_SECRET` `ALICLOUD_ACCESS_KEY_ID/_SECRET`
  `BAILIAN_BILLING_ACCESS_KEY_ID/_SECRET` `BAILIAN_TELEMETRY_ACCESS_KEY_ID/_SECRET`
- **WeChat**:`WECHAT_MP_APP_SECRET`(canonical)+ `WECHAT_MP_APPSECRET`(别名)`WECHAT_MP_TOKEN_SECRET`
- **Supabase**:`SUPABASE_KEY` `SUPABASE_ANON_KEY` `SUPABASE_SERVICE_KEY` `SUPABASE_SERVICE_ROLE_KEY`
- **DeepTutor 自有 secret**:`DEEPTUTOR_ATTEMPT_REF_SECRET`(已被 `check_secret_envs.py` 守)
  `DEEPTUTOR_AUTH_SECRET` `MEMBER_CONSOLE_AUTH_SECRET` `DEEPTUTOR_METRICS_TOKEN`
  `DEEPTUTOR_WS_SMOKE_TOKEN` `DEEPTUTOR_UNIFIED_WS_SMOKE_TOKEN` `DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN/PASSWORD`
  `DEEPTUTOR_INTERNAL_QA_TEST_PASSWORD` `GITHUB_TOKEN`
- **观测**:`LANGFUSE_PUBLIC_KEY` `LANGFUSE_SECRET_KEY`

> **注**:`DEEPTUTOR_AUTH_TOKEN_TTL_SECONDS` / `MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS` 名里含 `TOKEN`
> 但语义是 TTL **数字配置**,不是密钥 → 归 **config**,不归 secret。

---

## C. config(非 flag、非 secret 的普通配置)

剩余 ~200 个是普通 config:端口、URL、目录、模型名、超时、阈值、cohort 名单、版本号等。
代表:`BACKEND_PORT` `LLM_MODEL` `LLM_HOST` `EMBEDDING_MODEL` `KBV5_RAG_TOP_K` `KBV5_RAG_DATA_VERSION`
`LUBAN_V1_ADJUDICATOR_TIMEOUT_S` `LUBAN_*_COHORT`(灰度名单,**值是 config 不是布尔 flag**)
`CORS_ORIGINS` `DATABASE_URL`(DB url 已被 db_registry 守)等。
**这一类按"在用 grandfathered"整体登记,不逐条核实**(零行为改动,scanner 只拦新增未登记)。

---

## D. 拼写可疑 / 疑似重复(needs_verification)

| 簇 | 成员 | 判定 |
|---|---|---|
| WeChat appsecret | `WECHAT_MP_APP_SECRET` vs `WECHAT_MP_APPSECRET` | **不是 bug**:`service.py:2517-2518` `getenv(X) or getenv(Y)` 显式别名。canonical=`WECHAT_MP_APP_SECRET`,无下划线形为兼容别名。登记为 alias。 |
| WeChat appid | `WECHAT_MP_APP_ID` vs `WECHAT_MP_APPID` | 同上,显式别名(`service.py:2816-2817`)。 |
| 阿里云 access key | `ALIYUN_SMS_*` / `ALIBABA_CLOUD_*` / `ALICLOUD_*` | **三套并存**:`ALIBABA_CLOUD_*` `ALICLOUD_*` 是阿里云官方 SDK 两种约定名,`ALIYUN_SMS_*` 是本项目 SMS 专用。**needs_verification**:是否能收敛成一套。处置:先全登记(grandfather),收敛单列 work order。 |

> 这些**全部先登记、零删除**。registry 标 `alias_of` / `needs_verification`,scanner 不因别名报错。

---

## E. 与 .env.example 的关系(诚实说明,不造第二份竞争清单)

`contracts/env_registry.yaml` 是 **canonical**;`.env.example` 是它面向"本地起服务"的**投影/子集**
(只放本地跑得起来需要填的那几十个)。两者关系写进 registry 头注释:**registry 全集 ⊇ .env.example**。
不把 .env.example 升格成第二权威,也不要求二者逐行一致——`.env.example` 故意只列子集是合理的。

---

## F. 本盘点喂给 registry / scanner 的结论

1. **feature flag 的机器判据 = 经 `env_flag()` 读取**(确定性,胜过名字后缀)。scanner 据此拦"裸 flag"。
2. 全部 284 个引用 + 别名 + needs_verification → 作为 `grandfathered` 整体进 registry,**零行为改动**。
3. scanner 两条 fail 规则只**止血防新增**(见 `check_env_registry.py`):新增未登记 env / 新增裸 flag → fail;
   存量 245 不强制一次清掉。
4. 不确定项(`MISTAKE_BOOK_*` 存活性、阿里云三套收敛)→ 登记 + 标注,**分批核实**,不冒进删。
</content>
</invoke>
