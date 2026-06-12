# RAG 诊断优先 + 免费午餐 — 2 周执行计划(v3.2 implementation-corrected)

**日期**:2026-05-28(eng review 2026-05-29 / 实施修正 2026-05-29)
**Scope**:P0-1(RAG 评估能力)+ P0-2(~~开 2 个 FF~~ → **改为 staging env 灰度 + baseline 量化,不翻代码默认**,见 addendum)
**总投入**:**~2 周**(P0-1 1 周代码 + 3-5 天专家标注 / P0-2 代码 0,改走 staging env)
**目的**:**用最低成本买"信息增益"**,搞清 RAG 是不是产品当前瓶颈,然后决定要不要继续投
**依据**:[2026-05-28 RAG 评估报告](#)(70/100,代码证据级)
**Eng review**:`/gstack-plan-eng-review` 2026-05-29,scope reduce 到 pytest 一体化(5 文件),5 个 finding 全部解决并入此版

---

## ⚠️ v3.2 实施修正 addendum(2026-05-29,以本节为准)

> v3.1 正文是 eng-review 时的快照(保留作历史)。**实施中发现的偏差以本 addendum 为准**;凡正文与此冲突,信此节。

### 已完成(代码侧关键路径全闭环)

| 任务 | 状态 | commit | 备注 |
|---|---|---|---|
| T1 `SupabasePipeline.check_chunk_ids_exist` | ✅ | `fad5ac9f` | 只读 RPC,复用 `_select`,无后端 SQL function;分批 50 防 URL 超长 |
| T2 `tests/services/rag/test_retrieval_quality.py` | ✅ | `883d29ac` | 27 单测 + 1 e2e gate(无 golden 时 skip) |
| T4 `eval/gates.yaml::rag_retrieval_quality` | ✅ | `39738aff` | gate key 无 `_gate` 后缀(对齐现有风格) |

### 骨架修正(v3.1 §2 代码骨架有两处错)

1. **`content_blocks[].chunk_id` 是错的** → 实际 `RAGService.search` 返回里 `content_blocks` 是**渲染文本字符串列表**;ranked chunk_id 在顶层 **`sources[].chunk_id`**。T2 已按 `sources` 实现(`_extract_retrieved_chunk_ids`)。
2. **`@pytest.mark.rag_quality` 被拒** → 仓库开 `--strict-markers`,未注册 marker 直接报错。已去掉 marker,gate 按文件路径 / `-k baseline` 选择。

### P0-2 方向变更(最重要)

v3.1 §3「翻代码默认 False→True + prod .env override」**已撤销**。原因:`contracts/rag.md` 实为 **33 段**(v1.1 §8 误以为 15 段),其中:

- **§20**:compiled truth 默认只能进 `ranking_trace.shadow_sources`,不得影响排序
- **§22**:provenance boost 默认关闭,不得成为 exact-question pinning 的承重项

这两段已把「默认关闭」写成**硬契约**。翻代码默认 = 破契约,且在 P0-1 baseline 出数据前翻 = 违背本计划「数据驱动」原则。

**新方向**:代码默认保持 `False`(契约成立)→ **staging 用 `.env=true` 显式开启**跑 P0-1 baseline 对比 true vs false → 数据证明改善后,**再正式走契约变更(改 §20/§22 + 理由)**才落代码默认 ON。守护测试:`test_provenance_boost_rollout.py` / `test_compiled_truth_rollout.py`(锁默认 OFF + 验 env 开关)。

### 任务状态重整

| 原任务 | 新状态 |
|---|---|
| T5 翻默认 + regression | **改为** rollout guard(默认 OFF + env 开关);`9f3c34cf` 翻默认已被 `433e8eef` 回退 |
| T6 contracts 加 §16 §17 声明默认 on | **作废**(不翻默认,§20/§22 保持不动) |
| T7 prod `.env` override=false | **作废**(代码默认已 OFF,部署 main 不会启用) |
| T9 删 prod override | **作废**(从未加 override) |
| 新增:contract guard 合规 | `433e8eef` — supabase.py 是 contract-sensitive,改它须配套白名单 test(已加进 `contracts/index.yaml`)+ contract surface |

### 剩余(都需人/远端)

- **T3** golden set 60-100 条专家标注(CC=0,禁 LLM 生成)
- **baseline 真跑**:需 T3 golden + staging KB + `RAG_EVAL_KB_NAME` + staging `.env=true`
- **T8** baseline 报告 commit(依赖上两项)

---

## 0. 决定的前因(为什么是这个 scope)

70/100 评估 + 战略反思后:**不全押世界顶尖,不冻结 RAG,做诊断 + 免费午餐**。

1. 当前 RAG 已 70/100——核心检索能力世界一线(8 路并行 + db hybrid + RRF + rerank + exact authority + 5 种 query shape)
2. **RAG 是不是瓶颈我们不知道**——`retrieval_empty_rate` / per-shape Recall / 低评归因(RAG vs LLM)全无数据
3. **2 周买 P0-1 + P0-2 是最高 ROI**:P0-1 是任何后续 RAG / 模型 / prompt 优化的前置 gate
4. **2 周后基于数据决策**:不预先承诺 P1

**Eng review 2026-05-29 后的 scope reduction**:Step 0 complexity check 触发(12 文件 → reduce 到 **5 文件 pytest 一体化**)。

---

## 1. Karpathy Gate(eng-review-locked)

### Assumptions

1. P0-1 上 staging 1-2 周后能拿到**有意义的真实流量样本**(retrieval_empty_rate / per-shape Recall@5)。若流量 < 1000 queries / 周延后决策
2. 60-100 条 golden set **由内部建筑考试专家人工标注**,LLM 自动生成不算
3. P0-2 FF 默认改 True 但**生产 env override 保 False 直到 P0-1 baseline 证明不退化**(2A)
4. 不预先承诺 2 周后的 phase(P1/P2 等数据决定)
5. **统计学诚实**:60-100 样本 → 每 shape 12-20 条 → Wilson 95% CI 约 ±25% → 只能 detect ≥15pp 移动,不要假装能 detect +5pp(3A)

### Simplest path

- P0-1 单文件 `tests/services/rag/test_retrieval_quality.py`(~250 行)含 metrics + golden loader + preflight + e2e gate test
- P0-2 是 2 行 env 默认值 + 2 个 regression 测试 + 1 段 contract 声明 + **生产 env override**
- 不引外部依赖(无 Redis / GPU / 新 vector DB / 无 RAGAS / 无 DeepEval)

### Change boundary(eng-review-locked)

| 允许触碰 | 不许顺手改 |
|---|---|
| 新建 `tests/services/rag/test_retrieval_quality.py`(单文件 ~250 行) | `supabase.py::search` 主链路 |
| 新建 `tests/fixtures/rag_retrieval_golden_v1.json` 60-100 条 | `_AUTHORITY_ORDER` / `_AUTHORITY_RANK` 常量数值 |
| 改 `_load_search_config:1627, 1640` 两个 env 默认值(P0-2) | LlamaIndex pipeline |
| 新增 2 个 regression test 文件 | Supabase 端 SQL function |
| **加 1 段 `contracts/rag.md` 声明 provenance ranking 默认开**(1A) | 任何已有契约段落 |
| 改 `eval/gates.yaml` 加 `rag_retrieval_quality_gate`(1 行) | `RAGService` / `RAGTool` 对外契约 |

### Verification target

**P0-1 Done**:
- `pytest tests/services/rag/test_retrieval_quality.py -v` 跑出 baseline 报告(stdout + 落盘)
- 报告含 per-shape(concept/mcq/case/standard/calc)的 `recall@1/5/10 / mrr`,**每项带 Wilson 95% CI**(3A)
- preflight chunk_id staleness check 工作(1B)
- 测试覆盖 ≥ 80%
- 接入 `eval/gates.yaml::rag_retrieval_quality_gate`
- baseline 报告 commit 到 `docs/plan/2026-XX-XX-rag-baseline-report.md`
- contract guard 全绿

**P0-2 Done**:
- `_load_search_config:1627, 1640` 默认改 True + 2 个 regression test
- `contracts/rag.md` 加 1 段声明 provenance ranking 默认开(1A)
- **生产 `.env` 设 `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false` 和 `SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false` override 保护**,等 P0-1 baseline 验证(2A)
- 所有现有 RAG 测试无回归
- P0-1 baseline 上对比"override=false vs override=true":`standard_like` Recall@5 不下降。**期望命中**:+5pp(用 Wilson CI 看是否显著)

---

## 2. P0-1:RAG 评估能力(单文件 pytest 一体化)

### Why

`tests/services/rag/` 3886 行测试**零 IR 度量**(grep `recall_at|MRR|NDCG` 全空)。任何后续 RAG 改动无法用数据证明改善还是退化。先建度量。

### What(eng-review-reduced 后)

#### 单一新增文件结构

```
tests/services/rag/
├── test_retrieval_quality.py      # NEW ~250 行
│   ├── compute_recall_at_k()
│   ├── compute_mrr()
│   ├── compute_wilson_ci()        # 3A 诚实 CI 报告
│   ├── load_golden_set()
│   ├── preflight_check_stale()    # 1B 防 fixture 漂移
│   ├── _eval_fixture()            # 4A 关 rerank
│   └── test_rag_retrieval_quality_baseline()  # pytest 入口
└── (现有测试不动)

tests/fixtures/
└── rag_retrieval_golden_v1.json   # NEW 60-100 条

eval/
└── gates.yaml                     # MODIFY 加 rag_retrieval_quality_gate

contracts/
└── rag.md                          # MODIFY 加 1 段 provenance ranking 默认开
```

#### 单文件代码骨架

```python
# tests/services/rag/test_retrieval_quality.py
"""RAG retrieval quality eval — diagnostic baseline (P0-1).

Single-file harness: metrics + golden loader + preflight + pytest gate.
Run: pytest tests/services/rag/test_retrieval_quality.py -v
Output: baseline report stdout + per-shape Recall@K/MRR with Wilson 95% CI.
"""
from __future__ import annotations
import json, math, os, pytest
from contextlib import contextmanager
from dataclasses import dataclass

# ── Metrics ────────────────────────────────────────────────────────────

def compute_recall_at_k(retrieved: list[str], expected: list[str], k: int) -> float:
    if not expected: return 0.0
    top = set(retrieved[:k])
    return sum(1 for e in expected if e in top) / len(expected)

def compute_mrr(retrieved: list[str], expected: list[str]) -> float:
    exp = set(expected)
    for rank, cid in enumerate(retrieved, 1):
        if cid in exp:
            return 1.0 / rank
    return 0.0

def compute_wilson_ci(p_hat: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI. 3A: honest reporting of n=12-20 → ±25% width."""
    if n == 0: return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))

# ── Golden set ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GoldenItem:
    id: str
    query: str
    query_shape: str  # concept_like / mcq_like / case_like / standard_like / calc_like
    expected_chunk_ids: list[str]
    annotator: str
    notes: str = ""

def load_golden_set(path: str) -> list[GoldenItem]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    items = []
    for r in raw:
        for required in ("id", "query", "query_shape", "expected_chunk_ids"):
            if required not in r:
                raise ValueError(f"golden item missing {required}: {r.get('id', '?')}")
        if r["query_shape"] not in {"concept_like", "mcq_like", "case_like", "standard_like", "calc_like"}:
            raise ValueError(f"invalid query_shape: {r['query_shape']}")
        items.append(GoldenItem(**{k: r[k] for k in r if k in GoldenItem.__annotations__}))
    return items

# ── Preflight staleness check (1B) ─────────────────────────────────────

class StaleGoldenSetError(RuntimeError):
    pass

async def preflight_check_stale(items: list[GoldenItem], kb_name: str) -> None:
    """1B: verify all expected_chunk_ids exist in Supabase. Fail loudly."""
    from deeptutor.services.rag.pipelines.supabase import SupabasePipeline
    all_ids = {cid for item in items for cid in item.expected_chunk_ids}
    pipeline = SupabasePipeline()
    try:
        existing = await pipeline.check_chunk_ids_exist(list(all_ids), kb_name)
        missing = all_ids - existing
        if missing:
            raise StaleGoldenSetError(
                f"Golden set stale: {len(missing)}/{len(all_ids)} chunk_ids missing in KB. "
                f"First 5: {sorted(list(missing))[:5]}. "
                f"Re-annotate golden set or check KB reindex history."
            )
    except Exception as e:
        if isinstance(e, StaleGoldenSetError):
            raise
        pytest.skip(f"Supabase unreachable for preflight: {e}")  # infra skip, not RAG fail

# ── Eval fixture: deterministic mode (4A) ──────────────────────────────

@contextmanager
def _eval_fixture():
    """4A: turn rerank OFF during eval; pure RRF quality only.
    rerank is high-variance LLM-based; including it adds noise that
    swamps small move detection. Eval measures retrieval, not rerank."""
    overrides = {
        "SUPABASE_RAG_ENABLE_RERANK": "false",
    }
    old = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

# ── E2E pytest gate ────────────────────────────────────────────────────

@pytest.mark.rag_quality
@pytest.mark.asyncio
async def test_rag_retrieval_quality_baseline(rag_kb_name):
    """Pytest gate — emits baseline report to stdout + report file.
    Reports per-shape Recall@K/MRR with Wilson 95% CI (3A honest).
    Failure modes: golden set stale (1B fail-loud) / Supabase down (skip)."""
    from deeptutor.services.rag.service import RAGService
    items = load_golden_set("tests/fixtures/rag_retrieval_golden_v1.json")
    await preflight_check_stale(items, rag_kb_name)

    with _eval_fixture():
        svc = RAGService()
        results = []
        for item in items:
            out = await svc.search(query=item.query, kb_name=rag_kb_name)
            retrieved = [b.get("chunk_id") for b in
                         out.get("evidence_bundle", {}).get("content_blocks", [])
                         if b.get("chunk_id")]
            results.append((item, retrieved))

    # Per-shape aggregation
    by_shape: dict[str, list[tuple]] = {}
    for item, retr in results:
        by_shape.setdefault(item.query_shape, []).append((item, retr))

    report = ["", "═" * 60, "RAG Retrieval Quality Baseline", "═" * 60]
    for shape, group in sorted(by_shape.items()):
        n = len(group)
        recalls = [compute_recall_at_k(r, i.expected_chunk_ids, 5) for i, r in group]
        mrrs = [compute_mrr(r, i.expected_chunk_ids) for i, r in group]
        r5_mean = sum(recalls) / n
        mrr_mean = sum(mrrs) / n
        r5_lo, r5_hi = compute_wilson_ci(r5_mean, n)
        report.append(
            f"  {shape:14s} n={n:3d}  Recall@5={r5_mean:.3f} [CI {r5_lo:.2f}, {r5_hi:.2f}]  MRR={mrr_mean:.3f}"
        )
    report.append("═" * 60)
    report.append(f"NOTE: Wilson 95% CI. n={min(len(g) for g in by_shape.values())}-{max(len(g) for g in by_shape.values())} per shape — only detects ≥15pp moves reliably.")
    msg = "\n".join(report)
    print(msg)
    # Also dump to artifact for baseline commit
    os.makedirs("artifacts/rag_eval", exist_ok=True)
    with open(f"artifacts/rag_eval/baseline_{os.getenv('GIT_SHA', 'local')}.md", "w") as f:
        f.write(msg)
```

#### Golden set 标注规格

- **60-100 条**,5 query_shape 分层(每层 12-20 条)
- **每条 schema**:`id / query / query_shape / expected_chunk_ids / annotator / notes`
- **标注流程**:
  1. 从生产 Langfuse trace 抽 200 条真实 query,按 query_shape 分桶
  2. 内部建筑考试专家逐条标注 expected chunks(看实际 chunks 库)
  3. 双盲交叉验证(两位专家独立标注 → 不一致项讨论)
  4. v1 ship 60-100 条,后续可加到 200+
- **诚实标注**:`notes` 字段记录"为什么这几个 chunks 才是 expected"(为后续迭代留 trace)

### Done = acceptance test 清单

- [ ] `tests/services/rag/test_retrieval_quality.py` 250 行写完,**测试覆盖 ≥ 80%**(metrics + golden loader + preflight + Wilson CI 全有单元测试)
- [ ] `tests/fixtures/rag_retrieval_golden_v1.json` 60+ 条标注完成,双盲交叉验证过
- [ ] `pytest tests/services/rag/test_retrieval_quality.py -v` 跑出 baseline 报告,落 `artifacts/rag_eval/baseline_<sha>.md`
- [ ] `eval/gates.yaml` 加 `rag_retrieval_quality_gate`,PR 必跑
- [ ] baseline 报告 commit 到 `docs/plan/2026-XX-XX-rag-baseline-report.md`
- [ ] contract guard 全绿(本计划改 `contracts/rag.md` 1 段,见 P0-2)
- [ ] 现有 `tests/services/rag/` 全套无回归
- [ ] **`SupabasePipeline.check_chunk_ids_exist` 方法新增**(为 1B preflight 服务,纯只读 RPC)

### 估时分解

| 子任务 | 估时 |
|---|---|
| 单文件 ~250 行(metrics + golden loader + preflight + e2e gate) | 3-4 天 |
| `SupabasePipeline.check_chunk_ids_exist` 实现 + 测试 | 1 天 |
| `eval/gates.yaml` 接入 | 0.5 天 |
| baseline 数据 commit | 0.5 天 |
| **代码侧累计** | **~5-6 天** |
| Golden set 60+ 条专家标注 + 双盲 | **3-5 天**(可与代码并行) |
| **总计(并行后)** | **~1.5-2 周** |

### 风险登记(eng-review 后更新)

| 风险 | 级别 | 缓解 |
|---|---|---|
| Golden set 标注质量低 → eval 失真 | **高** | 内部专家强制参与;双盲交叉验证;v1 → v2 迭代;LLM 不允许自动生成标注 |
| **统计不足以 detect 小 move** | **中** | 3A: 报告 Wilson CI,文档明说"v1 只 detect ≥15pp",P1 按需扩到 200+ |
| **Golden set fixture 漂移**(KB 重灌后) | **中** | 1B: preflight check 失败 raise `StaleGoldenSetError` 列名 |
| **eval 跑时 rerank 噪声混入** | **中** | 4A: `_eval_fixture` 强制关 rerank |
| 60 条样本统计意义不足 | 已合并到上 | — |
| `SupabasePipeline.check_chunk_ids_exist` 未实现需要新增 RPC | 中 | 后端协作或临时用 `_select` 表查询兜底 |

---

## 3. P0-2:开 2 个已实现未开的 FF(代码先合,生产 env 保 override)

### Why

70/100 评估实证:**两项关键功能完整实现但默认 disabled**——免费午餐。

### What(eng-review 后 — 加 contract 段落 + override discipline)

#### 改动 1:env 默认值翻转(代码)

```python
# deeptutor/services/rag/pipelines/supabase.py

# 第 1627 行
- compiled_truth_enabled=_env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", False),
+ compiled_truth_enabled=_env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", True),

# 第 1640 行
- provenance_boost_enabled=_env_flag("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", False),
+ provenance_boost_enabled=_env_flag("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", True),
```

#### 改动 2:2 个 regression 测试

```python
# tests/services/rag/test_provenance_boost_default_on.py
def test_provenance_boost_default_enabled(monkeypatch):
    """P0-2 regression: default should be ON after this PR."""
    monkeypatch.delenv("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", raising=False)
    config = _load_minimal_config()
    assert config.provenance_boost_enabled is True

def test_provenance_boost_env_override_still_works(monkeypatch):
    """Critical for P0-2 rollout (2A): env=false must keep it off in prod."""
    monkeypatch.setenv("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", "false")
    config = _load_minimal_config()
    assert config.provenance_boost_enabled is False
```

`test_compiled_truth_default_on.py` 同款。

#### 改动 3:contracts/rag.md 加段(1A)

在 `contracts/rag.md` 现有 §15 之后追加 §16:

```markdown
16. `provenance ranking` 默认启用(`SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=true`,代码默认值在
    `deeptutor/services/rag/pipelines/supabase.py::_load_search_config`)。
    Authority rank 数值唯一来源是 `deeptutor/services/rag/provenance.py::_AUTHORITY_RANK`
    (8 层:exact_question 100 / question_exact_text 100 / question_exact_vector 95 /
    standard_code_exact 90 / standard_precision 88 / standard 80 / questions_bank 70 /
    compiled_learning_truth 55 / textbook 45 / exam 40)。
    `apply_provenance_ranking` 在 weighted_rrf_score 之上叠加 authority boost
    (+0.02 ~ +0.04 by source group)+ exact_question 命中时硬置顶。
    生产环境若需关闭只能通过 env override(`SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false`),
    不得在代码里硬编 False。
```

(`compiled_truth` 段类似补)

#### 改动 4:生产 env override(2A)

**代码合并 PR 之前**,先在生产 `.env` 加:

```bash
# Temporary override pending P0-1 baseline validation (2A)
SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false
SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false
```

P0-1 baseline 验证后,**单独 PR** 删除这两行 override,让代码默认生效。

### Done = acceptance test 清单

- [ ] 改 `_load_search_config:1627, 1640` 默认值 → True
- [ ] 2 个新 regression 测试 pass(默认开 + env override 仍 work)
- [ ] `contracts/rag.md` 加 §16 + §17(provenance + compiled_truth 默认 on 声明)
- [ ] 生产 `.env` 设 override=false(2A)
- [ ] `scripts/check_contract_guard.py` 全绿
- [ ] 现有 `tests/services/rag/` 全部测试无回归(已 grep 确认 — 测试构造 SupabaseSearchConfig 直接绕开 env)
- [ ] P0-1 baseline ready 后,跑"override=true vs override=false"对比:`standard_like` Recall@5 ≥ 不下降
- [ ] **期望命中**:`standard_like` Recall@5 +5pp(Wilson CI 看是否显著);`mcq_like` +3pp
- [ ] **后续 PR**:删 `.env` override 让代码默认生效(单独 PR,P0-1 baseline 通过后)

### 风险登记

| 风险 | 级别 | 缓解 |
|---|---|---|
| `provenance_boost` 让 exact_question 过强挤掉 standard 召回 | 中 | P0-1 eval 拦截;生产 env override 保 False 直到验证 |
| `compiled_truth_enabled=True` 但 KB 没数据 → 中性 | 低 | shadow 已跑,真开行为相同 |
| 现有测试假设旧默认 | **已验证低** | grep 实证:测试都直接构造 SupabaseSearchConfig 绕开 env |
| 与并发 agent 改 RAG 模块冲突 | 中 | RAG 单一权威;改前看 `docs/plan/INDEX.md` 有无并发计划 |
| **rollout 中误删 env override 让默认生效** | **中** | override PR 单独走,与代码默认 flip PR 解耦,P0-1 baseline 验证 sign-off 后才删 |

### 估时

- 代码改 + 2 个 regression 测试:**3 h**
- `contracts/rag.md` 加 §16 §17:**1 h**
- 生产 `.env` 加 override:**0.5 h**
- 等 P0-1 baseline:**~2 周(并行 P0-1 完工)**
- 删除 override 的后续 PR:**0.5 h**

---

## 4. 2 周后的决策点(用真实数据驱动)

```
看 P0-1 baseline 数据 + 用户反馈数据
│
├─ 加权 Recall@5 ≥ 0.85 且 retrieval_empty_rate < 10%
│   └─ 结论:RAG 不是当前瓶颈 → **冻结 RAG**,资源转去:
│         • 内容覆盖度(规范库 / 题库扩充)
│         • 模型升级(已在做的 cross-model eval 加深)
│         • mobile UX
│
├─ 加权 Recall@5 ∈ [0.70, 0.85) 或某 shape 明显拖
│   └─ 结论:**针对性优化**,只做最高 ROI 的 1-2 个 P1 item
│
└─ 加权 Recall@5 < 0.70
    └─ 结论:**RAG 是真瓶颈**,全做 P1(6-8 周)
```

这个决策点不在本计划承诺范围——P0-1 + P0-2 完成后单开 ADR。

---

## 5. NOT in scope(防 scope creep,eng-review-locked)

1. **不**做 P1 任何项目(LLM rewriter / 语义 cache / clause v2 / hallucination guard / hybrid grid search)——等 P0-1 数据决定
2. **不**改 LlamaIndex 本地管道——不用
3. **不**改 Supabase 端 `search_unified / search_questions_bank_text` SQL function——外部数据流程
4. **不**重写 `supabase.py::search` 主链路
5. **不**引外部依赖(Redis / GPU / RAGAS / DeepEval / TruLens / 新 vector DB)
6. **不**做 200+ 条 golden set(v2 看数据再扩)
7. **不**做 bootstrap CI(Wilson 已足)
8. **不**做 LLM-as-judge metrics(faithfulness / answer relevance)——P1 视情
9. **不**让 eval harness 跑生产 hot-path——只 offline / pytest gate
10. **不**让 LLM 自动生成 golden set 标注——专家人工
11. **不**预先承诺 2 周后 phase——基于数据决定
12. **不**做 rerank 质量评估——4A 决定 eval 关 rerank,rerank 视为正交模块未来单独评估
13. **不**做火箭灯 user-id rollout——2A 选择 env override 保护
14. **不**在 P0-2 PR 内删 `.env` override——单独 PR 在 P0-1 baseline 后

---

## 6. What already exists(避免重复造)

| 已有 | 位置 | 计划如何处理 |
|---|---|---|
| `eval/gates.yaml::rag_retrieval_contract` | 现有 gate 跑 unit/contract 测试 | **并列加** `rag_retrieval_quality_gate`,不替换 |
| `deeptutor/services/rag/maintenance.py`(225 行) | retrieval 质量审计 dry-run | **保留**,不替换;它做"维护期审计",我们做"per-PR 评估",正交 |
| `tests/fixtures/rag_grounding_eval_cases.json` | exact_authority 测试 fixture | **不复用**,schema 不同(它测 authority,我们测 recall);**学其命名约定** |
| `RAGService.smart_retrieve` LLM query 改写路径 | `service.py:291-349` | **不动**;生产主路径 `search()` 不走它,P1 再考虑 main-path fallback |
| `apply_provenance_ranking`(8 层 authority) | `provenance.py:66` | **P0-2 启用即生效**,不重写 |
| `compiled_truth_source.py` + shadow 模式 | 已默认 shadow on | **P0-2 启用从 shadow 升 real**,不重写 |
| `tests/services/rag/` 3886 行 unit/contract 测试 | 测试基线 | **不动**,我们补 IR 度量维度,与现有 unit 测试正交 |
| Langfuse trace(10+ start_observation in supabase.py) | observability | eval harness **复用** Langfuse,新 stage 名 `rag.eval.baseline` |

**确认无重复造**:本计划新增的是 IR 度量这个**全新维度**,与现有所有模块正交。

---

## 7. Failure modes(每条新代码路径,失败 + 是否兜)

| 新路径 | 失败模式 | 测试覆盖 | 用户/CI 看到什么 |
|---|---|---|---|
| `compute_recall_at_k` | empty retrieved → div?empty expected→div? | ✓ 边界单测 | 0.0(无声) |
| `compute_wilson_ci` | n=0 | ✓ 边界单测 | (0,0) 不 NaN |
| `load_golden_set` | missing field / invalid shape | ✓ raise ValueError | CI 红 + 列字段 |
| `preflight_check_stale` | chunk_id 缺失 | ✓ raise StaleGoldenSetError(列名) | CI 红 + missing 列表 |
| `preflight_check_stale` | Supabase 不可达 | ✓ pytest.skip + WARN | CI 黄(infra skip,非 RAG fail) |
| `_eval_fixture` | env restore 失败 | ✓ try/finally 单测 | 不影响后续 test 隔离 |
| `test_rag_retrieval_quality_baseline` | RAGService.search 抛 RAGError | 现有 typed-failure 兜底 | CI 红 + 错误类型 + provider |
| P0-2 默认 flip + env override 误删 | 静默全量启用 | **PR review 必须 catch** | 生产用户直接暴露 |

**critical gap**: P0-2 .env override 误删是 silent failure 风险,但通过 **rollout discipline(单独 PR + sign-off)+ eng review here**,治理在流程层面。

---

## 8. 单一权威 + 契约纪律

按 `AGENTS.md §5.7` Single Authority Hard Gate + `contracts/rag.md`:

- **`RAGService` 仍是唯一 grounding 入口** —— eval harness 通过 `RAGService.search` 调用
- **`evidence_bundle` schema 不动** —— eval 只读 `content_blocks[].chunk_id`
- **`_AUTHORITY_ORDER` / `_AUTHORITY_RANK` 数值不动** —— P0-2 启用既有 ranking 逻辑;1A 在契约中**显式声明**这两个常量是数值唯一来源
- **`contracts/rag.md` 改动**:加 §16 (provenance) + §17 (compiled_truth) 声明默认 on,不改既有 15 段
- 改前跑 `scripts/check_contract_guard.py`

---

## 9. 上 `docs/plan/INDEX.md`

✓ 已挂(2026-05-28 主线总览 + PRD 列表)

---

## 10. Implementation Tasks(eng-review 后,build-actionable)

- [ ] **T1 (P0, human: ~4h / CC: ~30min)** — supabase pipeline — 加 `check_chunk_ids_exist` 只读 RPC 方法
  - Surfaced by: 1B Architecture review — preflight 需要批量验证 chunk_id 存在
  - Files: `deeptutor/services/rag/pipelines/supabase.py`(新方法)+ `tests/services/rag/test_supabase_check_chunk_ids.py`(新)
  - Verify: `pytest tests/services/rag/test_supabase_check_chunk_ids.py -v`
- [ ] **T2 (P0, human: ~3-4 天 / CC: ~2h)** — eval — 写单文件 `test_retrieval_quality.py`
  - Surfaced by: Step 0 reduce + Section 3 — metrics + golden loader + preflight + Wilson CI + e2e gate
  - Files: `tests/services/rag/test_retrieval_quality.py`
  - Verify: 离线单测覆盖 ≥ 80% + 跑出 baseline 报告
- [ ] **T3 (P0, human: ~3-5 天 / CC: 0)** — golden set — 60-100 条专家标注
  - Surfaced by: P0-1 核心交付
  - Files: `tests/fixtures/rag_retrieval_golden_v1.json`
  - Verify: 双盲交叉验证;preflight check 全过
- [ ] **T4 (P0, human: ~30min / CC: ~5min)** — gates — 加 `rag_retrieval_quality_gate`
  - Surfaced by: Section 1
  - Files: `eval/gates.yaml`
  - Verify: CI 跑通
- [ ] **T5 (P0, human: ~3h / CC: ~15min)** — P0-2 默认 flip + regression test
  - Surfaced by: P0-2 核心
  - Files: `_load_search_config:1627, 1640` + 2 regression test 文件
  - Verify: 现有 RAG 套件无回归 + 2 regression test pass
- [ ] **T6 (P0, human: ~1h / CC: ~10min)** — contracts/rag.md 加 §16 §17 — 1A 决定
  - Surfaced by: 1A Architecture review
  - Files: `contracts/rag.md`
  - Verify: `scripts/check_contract_guard.py` 全绿
- [ ] **T7 (P0, human: ~30min)** — 生产 .env override(2A 决定)
  - Surfaced by: 2A Code Quality review
  - Files: 阿里云 `/root/deeptutor/.env`(走 §3.7 边界)
  - Verify: `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false` + `SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false` 生效 + 容器读到
- [ ] **T8 (P0, human: ~0.5h / CC: ~5min)** — baseline 报告 commit + 决策启动
  - Surfaced by: P0-1 Done 标准
  - Files: `docs/plan/2026-XX-XX-rag-baseline-report.md`
  - Verify: 报告含 per-shape Recall@5/MRR + Wilson CI;决策树启动
- [ ] **T9 (P1 follow-up, human: ~0.5h)** — 删 .env override(P0-1 baseline 验证 OK 后)
  - Surfaced by: 2A rollout discipline
  - Files: 阿里云 `.env`
  - Verify: 默认 True 生效,Recall@5 不退化
  - **Depends on T8 pass**

---

## 11. 序列与依赖

```
T1 (check_chunk_ids_exist)  ─┬─→ T2 (test_retrieval_quality.py)
                              │      │
                              │      └─→ T3 (golden set 标注)
                              │              │
                              │              └─→ T4 (gates.yaml)
                              │                       │
T5 (P0-2 默认 flip)           ─→ T6 (contracts/rag.md)│
                                       │              │
                              T7 (.env override) ──────┴─→ T8 (baseline 报告)
                                                                │
                                                          T9 (删 override)
```

**最短关键路径**:T1 → T2 → T3 → T4 → T8 → T9
**累计**:~2 周(T3 标注是大头,可与 T1/T2 并行)

---

## 12. Worktree parallelization

**Sequential, no parallelization opportunity**——所有 task 都在 `deeptutor/services/rag/` 或 `tests/services/rag/` 域内串行,没有独立 lane。单 worktree 顺序做完即可。

---

## 13. 待你决定(eng-review 后剩 1 件)

1. **执行启动节奏**:
   - A) 我直接开 T1(`SupabasePipeline.check_chunk_ids_exist` 新 RPC 方法 + 单测)
   - B) 先 `/gstack-plan-design-review` 走 UI 视角审查(本计划无 UI,N/A)
   - C) 先 `/gstack-plan-ceo-review` 走 scope 审查(scope 已 reduce,N/A)
   - D) 等专家标注资源 ready 再启动

---

## 14. 计划版本史

- v1(2026-05-28 上午):基于两份评估报告口述,基线多处错误。**已删除**。
- v2(2026-05-28 中午):基于 codegraph 实证,代码证据级基线。**已删除**。
- v3(2026-05-28 下午):基于 70/100 评估 + 战略反思(诊断优先 + 免费午餐)。
- **v3.1(2026-05-29)**:`/gstack-plan-eng-review` 后定稿,scope reduce 到 5 文件,5 个 finding 全部 resolved。
- **v3.2(本文件,2026-05-29 实施修正)**:T1/T2/T4 落地(`fad5ac9f`/`883d29ac`/`39738aff`)。实施中发现 v3.1 三处偏差并修正(见顶部 addendum):①§2 骨架 `content_blocks`→`sources`;②`--strict-markers` 去掉 `rag_quality` marker;③`contracts/rag.md` 实为 33 段且 §20/§22 已硬性规定两 FF 默认关闭 → **P0-2 撤销「翻代码默认」,改走 staging env 灰度**(T5 改 rollout guard / T6 T7 T9 作废);补 contract-guard 合规(`433e8eef`)。

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | (skipped: scope 已 reduce,user 已做战略反思决策) |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | (skipped: Codex 配额 2026-05-31 才恢复) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | **CLEAR** | Step 0 reduce 12→5 files;5 findings resolved (1A contract update / 1B preflight check / 2A env override discipline / 3A Wilson CI / 4A eval rerank off);0 critical gaps;0 unresolved decisions |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | (N/A: 无 UI 改动) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | (skipped) |

- **UNRESOLVED:** 0
- **CRITICAL GAPS:** 0(P0-2 .env override 误删是 silent risk 但治理在 rollout 流程层面 — T9 单独 PR + T8 sign-off gate)
- **VERDICT:** **ENG CLEARED — ready to implement** (执行启动按问题 13 选项 A 直接开 T1)

—— 完 ——
