# LLM provider 登记拓扑盘点（只读，零行为改动）

> Step 1 of `RESOURCE_GOVERNANCE_FIX_PLAN.md` Layer 2 · P1（provider 收权）。
> **本文档是只读盘点**：列出三套 provider registry 各自声明的 `default_api_base`、逐条对照漂移，
> 并枚举所有绕过 registry 的硬编码 base_url 旁路点。**不改任何调用行为。**
> `needs_verification` 标记 = 存活性/职责未经运行时核实，靠静态阅读 + import 拓扑推断。
>
> 方法：解析三套 registry 的 `ProviderSpec(... default_api_base=...)` 块做逐 provider 对照；
> `grep -E '(base_url|api_base)\s*=\s*"https?://'` + provider 域名字面量定位旁路；
> `grep import` 还原 import 拓扑判断哪套真在生产路径上。
> 盘点时点的 HEAD：`feat/luban-arbitration-gold-panel`。

## 0. 一句话结论

- **三套 registry 并存 + 1 套 re-export shim**，各自声明同一批 provider 的 `default_api_base`：
  1. `deeptutor/services/provider_registry.py`（**真权威**：被 LLM config / settings router / benchmark / provider_runtime / tutorbot adapter 全部 import）
  2. `deeptutor/tutorbot/providers/registry.py`（**近重复副本**：仅被 `openai_compat_provider.py` 做 `ProviderSpec` 类型 import，运行时解析**不**经它）
  3. `deeptutor/services/config/provider_runtime.py` 的 `EMBEDDING_PROVIDER_DEFAULTS`（**第三份 base_url 表**：embedding 专用，自带 `dashscope/openai/ollama/cohere/jina` base_url）
  4. `deeptutor/services/llm/provider_registry.py`（`import *` re-export shim，**非独立来源**，指向 #1）
- **实测漂移**（详见 §2）：`openai`（services 钉 `https://api.openai.com/v1`，tutorbot 留空）、`llama_cpp`/`lm_studio`（仅 services 有，tutorbot 缺）、embedding 表的 `ollama`（`…:11434` 无 `/v1` 后缀，与 LLM 表 `…:11434/v1` 不一致）。
- **20+ 处硬编码 base_url 直接旁路 registry**（§3），改一个 provider 的端点要改 4+ 处，漏一处即打错端点 → 成本归错账（deepseek billing 对账偏差先例）。
- **canonical 选择**：`deeptutor/services/provider_registry.py`（理由见 §4，import 拓扑铁证）。

## 1. import 拓扑（哪套真在生产路径）

| registry 文件 | 谁 import 它（非 test） | 在运行时 LLM 解析链上？ |
|---|---|---|
| `services/provider_registry.py` | `services/llm/config.py`、`api/routers/settings.py`、`services/benchmark/exam_quality_eval.py`、`services/llm/provider_registry.py`(shim)、`services/config/provider_runtime.py`、`tutorbot/providers/deeptutor_adapter.py` | ✅ 是（`provider_runtime.resolve_llm_runtime_config` + `deeptutor_adapter` 都从这里取 `find_by_model/find_by_name/find_gateway`） |
| `tutorbot/providers/registry.py` | `tutorbot/providers/openai_compat_provider.py`（仅 `TYPE_CHECKING` 的 `ProviderSpec` 类型 import） | ❌ 否（只借类型；`spec` 实例由调用方从 #1 解析后传入） |
| `services/config/provider_runtime.py` `EMBEDDING_PROVIDER_DEFAULTS` | 自身 `resolve_embedding_runtime_config` 消费 | ✅ 是（embedding 专用解析，**不**走 #1 的 `PROVIDERS`） |
| `services/llm/provider_registry.py` | 历史兼容 import 点（`import *` 透传 #1） | ➖ 透传 #1，无独立数据 |

> **结论**：#1 是 LLM provider 元数据的事实权威。#2 是漂移温床（一份近重复副本，开发者可能误改它而运行时不生效——这正是"自报权威/第二权威"病灶）。#3 是 embedding 侧的**第三份 base_url 来源**，与 #1 的 LLM 侧 base_url 在 `dashscope/openai/ollama` 上重叠但格式可漂移。

## 2. base_url 逐 provider 漂移对照（#1 vs #2）

> `__ABSENT__` = 该 registry 完全没有这个 provider 条目（provider 集合漂移）。
> `(none)` = 有条目但 `default_api_base` 为空（依赖 SDK 默认或运行时填）。

| provider | #2 tutorbot | #1 services（canonical） | 漂移 |
|---|---|---|---|
| **openai** | `(none)` | `https://api.openai.com/v1` | ⚠️ **DRIFT**：tutorbot 留空依赖 SDK 默认，services 显式钉端点 |
| **llama_cpp** | `__ABSENT__` | `http://localhost:8080/v1` | ⚠️ **DRIFT**：provider 集合不一致 |
| **lm_studio** | `__ABSENT__` | `http://localhost:1234/v1` | ⚠️ **DRIFT**：provider 集合不一致 |
| anthropic | `https://api.anthropic.com/v1` | 同 | 一致 |
| deepseek | `https://api.deepseek.com` | 同 | 一致 |
| dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 同 | 一致 |
| zhipu | `https://open.bigmodel.cn/api/paas/v4` | 同 | 一致 |
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | 同 | 一致 |
| moonshot | `https://api.moonshot.ai/v1` | 同 | 一致 |
| minimax | `https://api.minimax.io/v1` | 同 | 一致 |
| mistral | `https://api.mistral.ai/v1` | 同 | 一致 |
| stepfun | `https://api.stepfun.com/v1` | 同 | 一致 |
| groq | `https://api.groq.com/openai/v1` | 同 | 一致 |
| qianfan | `https://qianfan.baidubce.com/v2` | 同 | 一致 |
| xiaomi_mimo | `https://api.xiaomimimo.com/v1` | 同 | 一致 |
| openrouter | `https://openrouter.ai/api/v1` | 同 | 一致 |
| aihubmix | `https://aihubmix.com/v1` | 同 | 一致 |
| siliconflow | `https://api.siliconflow.cn/v1` | 同 | 一致 |
| volcengine(+coding) | `https://ark.cn-beijing.volces.com/api/v3(/coding)` | 同 | 一致 |
| byteplus(+coding) | `https://ark.ap-southeast.bytepluses.com/api/v3(/coding)` | 同 | 一致 |
| github_copilot | `https://api.githubcopilot.com` | 同 | 一致 |
| openai_codex | `https://chatgpt.com/backend-api` | 同 | 一致 |
| ollama | `http://localhost:11434/v1` | 同 | 一致 |
| vllm / ovms | `http://localhost:8000/v1` / `:8000/v3` | 同 | 一致 |
| custom / azure_openai | `(none)` | 同 | 一致 |

### 2.1 embedding 表（#3）独有/漂移的 base_url

| provider | #3 `EMBEDDING_PROVIDER_DEFAULTS` | 对照 #1 LLM 表 | 备注 |
|---|---|---|---|
| dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 一致 | 同端点（embedding + chat 复用）|
| openai | `https://api.openai.com/v1` | 一致 | — |
| **ollama** | `http://localhost:11434` | `http://localhost:11434/v1` | ⚠️ **DRIFT**：无 `/v1` 后缀 |
| vllm | `http://localhost:8000/v1` | 一致 | — |
| cohere | `https://api.cohere.ai` | `__ABSENT__`（#1 无 cohere） | embedding 专属 provider，仅此一处声明 |
| jina | `https://api.jina.ai/v1` | `__ABSENT__`（#1 无 jina） | embedding/search 专属，仅此一处声明 |
| azure_openai / custom | `(空)` | 一致 | — |

> 真伪判断：`openai` 留空 vs 钉端点（#1 vs #2）= **真漂移但 blast radius 受限**——#2 不在运行时解析链上，所以此刻没造成线上错端点；但它是"开发者改错副本"的陷阱。`ollama` 的 `/v1` 后缀差异 = **真漂移**，影响 embedding vs chat 对 ollama 的 URL 拼装一致性（`needs_verification`：本机 ollama 是否两种都容忍取决于其路由）。其余 base_url **此刻一致**（非"无漂移"，而是"尚未漂移"——没有机器闸时迟早漂）。

## 3. 硬编码 base_url 旁路点（绕过 registry，20+ 处实测，非 test）

> 这些 call site 不从 registry 取 base_url，而是把端点字面量写死在调用处。改 provider 端点要逐处改，漏一处即旁路。
> 形态分三类：(A) 直接 `base_url="https://…"` 传给 SDK；(B) `or "https://…"` 默认兜底；(C) 模块级常量/dataclass 默认。

### 3.1 直接传 SDK 的 base_url（最直接的旁路）

| # | 文件:行 | provider | 端点 | 形态 |
|---|---|---|---|---|
| B1 | `capabilities/deep_question.py:2020` | deepseek | `https://api.deepseek.com` | A `base_url=` |
| B2 | `services/construction_grading/runtime_llm_adjudicator.py:297` | dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | A `base_url=` |
| B3 | `services/construction_grading/artifact_first_llm_judge.py:511` | deepseek | `https://api.deepseek.com` | A `base_url=` |

### 3.2 `or "https://…"` 默认兜底（fallback 旁路）

| # | 文件:行 | provider | 端点 |
|---|---|---|---|
| B4 | `services/llm/cloud_provider.py:275` | openai | `https://api.openai.com/v1` |
| B5 | `services/llm/cloud_provider.py:410` | openai | `https://api.openai.com/v1` |
| B6 | `services/llm/cloud_provider.py:615` | anthropic | `https://api.anthropic.com/v1` |
| B7 | `services/llm/cloud_provider.py:707` | anthropic | `https://api.anthropic.com/v1` |
| B8 | `services/observability/deepseek_billing.py:155` | deepseek | `https://api.deepseek.com` |
| B9 | `services/observability/deepseek_billing.py:277` | deepseek | `https://api.deepseek.com` |
| B10 | `services/search/providers/openrouter.py:39` | openrouter | `https://openrouter.ai/api/v1` |

### 3.3 模块级常量 / dataclass 默认 / dict 字面量

| # | 文件:行 | provider | 端点 |
|---|---|---|---|
| B11 | `services/llm/factory.py:754` | openai | `https://api.openai.com/v1` |
| B12 | `services/llm/factory.py:760` | anthropic | `https://api.anthropic.com/v1` |
| B13 | `services/llm/factory.py:767` | deepseek | `https://api.deepseek.com` |
| B14 | `services/llm/factory.py:773` | openrouter | `https://openrouter.ai/api/v1` |
| B15 | `services/observability/deepseek_billing.py:142` | deepseek | `https://api.deepseek.com`（dataclass 默认） |
| B16 | `services/rag/pipelines/kbv5.py:73` | dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` |
| B17 | `services/benchmark/kb_v5_readonly_adapter.py:75` | dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` |
| B18 | `services/photo_answer/engines/qwen_vl_ocr.py:26` | dashscope | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` |
| B19 | `tutorbot/providers/transcription.py:19` | groq | `https://api.groq.com/openai/v1/audio/transcriptions` |
| B20 | `services/search/providers/baidu.py:31` | qianfan/baidu | `https://qianfan.baidubce.com/v2/ai_search/chat/completions` |

> **存量 grandfather 名单**：以上 B1–B20 全部是存量旁路，scanner 一律 grandfather（不回溯改写）。新增同类即 fail（止血）。
> 注：B16/B17/B18/B20 是 **full-path endpoint**（带 `/embeddings`、`/chat/completions`、`/audio/transcriptions` 后缀），不是裸 base_url；它们是 registry base_url + 路径的拼装存量，迁移时需保留路径段（见迁移 work order）。

## 4. canonical 选择 + 另两套定位

| registry | 定位 | 理由 |
|---|---|---|
| `services/provider_registry.py` | **canonical（权威）** | import 拓扑铁证：LLM config / settings / benchmark / provider_runtime / tutorbot adapter 全部从它取 spec；`ProviderSpec` 字段最全（含 `PROVIDER_ALIASES` / `strip_provider_prefix` / `NANOBOT_LLM_PROVIDERS`）。 |
| `tutorbot/providers/registry.py` | **deprecated → 指向 canonical** | 近重复副本，运行时**不**经它解析；只借 `ProviderSpec` 类型。降级登记，scanner 禁止在它里面**新增** provider（防再生第二权威）。真正删除/改为 `from services.provider_registry import ProviderSpec` 是分批 work order。 |
| `services/config/provider_runtime.py` `EMBEDDING_PROVIDER_DEFAULTS` | **deprecated（embedding 子集）→ 指向 canonical** | 第三份 base_url 表，embedding 专属。登记为 deprecated，scanner 禁止在它里面**新增** embedding provider base_url。收口到 canonical（让 embedding 也从 `PROVIDERS` 取，cohere/jina 补进 canonical）是分批 work order。 |
| `services/llm/provider_registry.py` | **shim（透传 canonical）** | `import *`，无独立数据，无需治理。 |

## 5. 不确定项 + 替代方案

- **哪套真权威**：✅ 已由 import 拓扑确证为 `services/provider_registry.py`（非推断）。
- **base_url 漂移真伪**：
  - `openai` 留空 vs 钉端点 = 真漂移，但 #2 不在运行时链 → 此刻无线上影响（`needs_verification`：是否有任何代码路径意外读到 #2 的 openai spec）。
  - `ollama` `/v1` 后缀差异 = 真漂移（`needs_verification`：本机 ollama 双端点是否都可用）。
  - 其余 base_url 此刻一致 = **尚未漂移**，非"安全"。无机器闸时三套迟早分叉（与 deepseek billing 对账偏差同构）。
- **替代方案（本次采用）**：**先拦新增，存量分批收口**。scanner 只拦 (a) 新增硬编码 base_url、(b) 新增第 4 套 registry / 在 deprecated 套加 provider；B1–B20 存量全 grandfather，三套并存现状全登记。真正"3→1 切代码"是分批 work order（§见 PROVIDER_REGISTRY_MIGRATION_WORK_ORDER.md），不在本次全量改。

## 6. 收敛目标（3→1，分批，不在本次）

```
现状:  services/provider_registry.py (权威)
       tutorbot/providers/registry.py (副本) ── 漂移温床
       provider_runtime.EMBEDDING_PROVIDER_DEFAULTS (embedding 第三份)
       20+ 硬编码 base_url 旁路

目标:  services/provider_registry.py (唯一 ProviderSpec 来源)
         ├─ tutorbot 只 import ProviderSpec 类型（删除副本数据）
         ├─ embedding 也从 PROVIDERS 取（cohere/jina 并入 canonical）
         └─ 所有 base_url 经 provider_runtime 解析（删除 20+ 硬编码）
```
