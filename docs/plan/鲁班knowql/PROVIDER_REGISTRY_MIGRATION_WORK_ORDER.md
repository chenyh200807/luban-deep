# Provider 3→1 收口迁移 work order（分批，行为不变）

> Step 5 of `RESOURCE_GOVERNANCE_FIX_PLAN.md` Layer 2 · P1。
> **本文档是迁移工单**：把"三套 registry + 20+ 硬编码 base_url"分批收口到唯一 canonical
> （`deeptutor/services/provider_registry.py`），**每批行为不变 + 独立验证**。
> 止血闸（`scripts/check_provider_registry.py`）已上线，**新增旁路/新增第二权威已被拦**；
> 本工单处理的是**存量收口**，全部 grandfather，逐批迁移、逐批从 grandfather 名单移除。
>
> 铁律：**绝不一次性碰所有 provider 调用**。每批一个独立 PR，行为对照通过才进下一批。
> 盘点依据：`PROVIDER_INVENTORY.md`（B1–B20 旁路 + 三套 registry 漂移）。

## 0. 收口顺序原则（越核心越后）

1. **先迁只读/旁路、off-hot-path 的**（billing / search / OCR），错了不影响判分主链路。
2. **再迁 LLM 主链路硬编码**（deep_question / construction_grading 判分调用），加倍验证。
3. **最后做 registry 合并**（删 tutorbot 副本数据 / embedding 表并入 canonical），改动面最大放最后。
4. 每批迁完，**把对应 path 从 `contracts/provider_registry.yaml` grandfathered_base_url_sites 移除**——
   闸随即对该 path 的任何新硬编码 base_url fail（收口闭环：迁一处、锁一处）。

## 1. 批次划分

| 批 | 范围 | 迁移内容 | 风险 | 验证 |
|---|---|---|---|---|
| **R1（样例，本工单详述）** | `deepseek_billing.py` (B8/B9/B15) | dataclass 默认 + `or` 兜底 `https://api.deepseek.com` → 从 canonical 取 `find_by_name("deepseek").default_api_base` | 最低（observability，非判分；env override 优先级不变） | 单测：env 缺失时 base_url 仍 = `https://api.deepseek.com`；env 设置时仍优先 env |
| R2 | `tutorbot/providers/registry.py` 副本 | 删除副本的 `PROVIDERS` 数据，`openai_compat_provider` 改 `from services.provider_registry import ProviderSpec` | 中（删一套 registry，但运行时本就不经它解析） | import 拓扑回归：`deeptutor_adapter` / `openai_compat_provider` 解析结果逐 provider 对照不变；删除前后 `find_by_*` 输出 diff = 空 |
| R3 | `provider_runtime.EMBEDDING_PROVIDER_DEFAULTS` | embedding 也从 canonical `PROVIDERS` 取 base_url；cohere/jina 并入 canonical（补 `ProviderSpec`）；修 ollama `/v1` 漂移 | 中（embedding 解析路径在运行时） | `resolve_embedding_runtime_config` 对每个 provider 的 base_url 迁移前后逐一对照；ollama `/v1` 变更单列确认本机容忍 |
| R4 | `cloud_provider.py` (B4–B7) + `factory.py` (B11–B14) | `or "https://…"` / dict 默认 → canonical 取 | 中（LLM 主链路） | 工厂构造的 client base_url 迁移前后对照 |
| R5 | `deep_question.py` (B1) + `construction_grading/*` (B2/B3) | 判分调用的硬编码 base_url → canonical 取 | **最高（判分主链路）** | 判分回归：同一答卷迁移前后判分结果一致；对抗 workflow 跑通 |
| R6 | full-path 旁路 (B16–B20: kbv5/qwen_ocr/baidu/transcription) | base_url 取 canonical，**保留路径段**（`/embeddings`/`/chat/completions`/`/audio/transcriptions`） | 中（需保留 path，易错） | 拼装后完整 URL 迁移前后逐字对照 |

## 2. 样例迁移 R1 — `deepseek_billing.py`（最安全，详述）

### 2.1 现状（旁路三处，B8/B9/B15）

```python
# deeptutor/services/observability/deepseek_billing.py
@dataclass(slots=True)
class DeepSeekBillingConfig:
    base_url: str = "https://api.deepseek.com"          # B15 dataclass 默认
    ...
    @classmethod
    def from_env(cls) -> "DeepSeekBillingConfig":
        return cls(
            base_url=_as_str(os.getenv("DEEPSEEK_BILLING_BASE_URL"))
            or "https://api.deepseek.com",               # B8 or-兜底
            ...
        )

    async def _fetch_balance(self):
        base_url = self._config.base_url.rstrip("/") or "https://api.deepseek.com"  # B9 or-兜底
```

三处都硬编码 `https://api.deepseek.com`。这正是 deepseek billing 对账偏差的同源风险：
canonical 的 deepseek base_url 一旦改（例如换区域端点），billing 仍打旧端点 → 余额/用量对账错库。

### 2.2 迁移后（从 canonical 取，行为不变）

```python
from deeptutor.services.provider_registry import find_by_name

def _deepseek_canonical_base_url() -> str:
    """Single source: the canonical registry's deepseek default_api_base."""
    spec = find_by_name("deepseek")
    # find_by_name always resolves deepseek (registered); fall back defensively.
    return (spec.default_api_base if spec else "") or "https://api.deepseek.com"

@dataclass(slots=True)
class DeepSeekBillingConfig:
    base_url: str = field(default_factory=_deepseek_canonical_base_url)   # was hardcoded
    ...
    @classmethod
    def from_env(cls) -> "DeepSeekBillingConfig":
        return cls(
            base_url=_as_str(os.getenv("DEEPSEEK_BILLING_BASE_URL"))
            or _deepseek_canonical_base_url(),            # env override 优先级不变
            ...
        )

    async def _fetch_balance(self):
        base_url = self._config.base_url.rstrip("/") or _deepseek_canonical_base_url()
```

**为何行为不变**：canonical 的 `deepseek.default_api_base` 当前 = `https://api.deepseek.com`（与硬编码字面量逐字相同，见 PROVIDER_INVENTORY §2）。
env override（`DEEPSEEK_BILLING_BASE_URL`）的优先级**完全不变**——仍是 env > canonical default。
唯一区别：default 不再是散落字面量，而是从唯一权威派生——以后改 deepseek 端点只改 canonical 一处。

> 注：保留 `or "https://api.deepseek.com"` 防御兜底是**故意的**——`find_by_name` 理论上恒命中，
> 但保留字面量兜底确保 import 失败/registry 损坏时 billing 不崩（fail-open 到已知端点）。
> 这个兜底字面量**就地登记在 helper 里**，仍在 grandfather 名单（path 不从名单移除直到全三处迁完）。

### 2.3 R1 验证（单测，行为对照）

```python
def test_billing_base_url_derives_from_canonical_when_env_absent(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_BILLING_BASE_URL", raising=False)
    cfg = DeepSeekBillingConfig.from_env()
    # 迁移前后都必须 = canonical deepseek base_url
    from deeptutor.services.provider_registry import find_by_name
    assert cfg.base_url == find_by_name("deepseek").default_api_base

def test_billing_env_override_still_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_BILLING_BASE_URL", "https://billing.internal/v1")
    cfg = DeepSeekBillingConfig.from_env()
    assert cfg.base_url == "https://billing.internal/v1"   # env 优先级不变
```

### 2.4 R1 收口闭环

R1 迁完三处后，从 `contracts/provider_registry.yaml grandfathered_base_url_sites` 移除：
```yaml
  - {path: deeptutor/services/observability/deepseek_billing.py, provider: deepseek, kind: bare_base_url, status: existing}
```
移除后，闸对该文件任何**新**硬编码 `https://api.deepseek.com` 立即 fail——
但本迁移保留的 helper 兜底字面量怎么办？两个合法选择：
- (i) 把 helper 兜底也去掉（依赖 `find_by_name` 恒命中），则可安全移除 grandfather；或
- (ii) 保留兜底字面量 + 保留该 path 在 grandfather 名单（承认仍有一处合法字面量）。
R1 采 **(i)**：registry 是必加载依赖，`find_by_name("deepseek")` 恒命中，去掉兜底后该 path 可干净出名单。

## 3. 不确定项 + 替代方案

- **R2 删 tutorbot 副本**：需先证明无任何代码路径读到副本的 `PROVIDERS` 数据（只读 `ProviderSpec` 类型是安全的）。
  替代：若发现有意外读取点，先把副本 `PROVIDERS` 改为 `from services.provider_registry import PROVIDERS` re-export（同 `services/llm/provider_registry.py` shim 思路），再删数据。
- **R3 ollama `/v1` 漂移**：embedding 表的 `http://localhost:11434`（无 `/v1`）改成 `…/v1` 前，
  必须 `needs_verification` 本机 ollama embedding 端点是否要 `/v1`——**不要假设**，先实测，否则改坏本地 embedding。
  替代：若两端点语义不同（embedding root vs chat `/v1`），则**不合并**，在 canonical 给 ollama 增加 `embedding_api_base` 字段显式区分，而非强行统一。
- **R5 判分主链路**：风险最高。替代：先影子比对（新旧 base_url 解析路径并行算，断言相等）再切换，不直接替换。
- **全量替代（已采用本批）**：止血闸已上线，**新增旁路进不来**；存量按上表分批、逐 PR、逐验证收口，
  任何一批失败只回滚那一批，不影响已上线的闸和其余批次。

## 4. 完成定义（3→1 收敛达成）

- [ ] R1–R6 全部迁完，`grandfathered_base_url_sites` 清空（或仅剩明确登记的合法字面量）。
- [ ] `tutorbot/providers/registry.py` 不再持有 `PROVIDERS` 数据（只 import 类型）。
- [ ] `EMBEDDING_PROVIDER_DEFAULTS` 的 base_url 全部从 canonical `PROVIDERS` 派生。
- [ ] `deprecated_sources` 标注从 `kind: …copy` 升级为 `kind: type_only_import` / 删除。
- [ ] 全仓 `grep -E '(base_url|api_base)\s*=\s*"https?://(api\.|dashscope|open\.bigmodel|…)'` 命中数 = 0（除 canonical + registry YAML）。
```
