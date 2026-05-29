# RAG 诊断优先 + 免费午餐 — 2 周执行计划

**日期**:2026-05-28
**Scope**:仅 P0-1(RAG 评估 harness)+ P0-2(开 2 个已实现未开的 FF)。
**总投入**:**2 周**(P0-1 1.5-2 周 + P0-2 1-2 天 并行/嵌入)。
**目的**:**用最低成本买"信息增益"**,搞清 RAG 是不是产品当前瓶颈,然后决定要不要继续投。
**依据**:[2026-05-28 RAG 评估报告](#)(70/100),证据级代码审计 + codegraph 实证。

---

## 0. 决定的前因(为什么是这个 scope)

70/100 评估 + 战略反思后,scope 决策:**不全押世界顶尖,不冻结 RAG,做诊断 + 免费午餐**。

理由(简版,完整反思见 chat 历史):

1. **当前 RAG 已经在 70/100**——核心检索能力世界一线水平(8 路并行 + db hybrid + RRF + rerank + exact authority + 5 种 query shape)。再投 20 分(8-12 周)边际效用大概率小于把同样精力投到内容覆盖 / 模型升级 / mobile UX。
2. **RAG 是不是瓶颈我们不知道**——`retrieval_empty_rate`、per-shape Recall、低评回答归因(RAG vs LLM)全部无数据。在不知道瓶颈位置时全押 RAG = 直觉配资。
3. **2 周买 P0-1 + P0-2 是最高 ROI**:P0-1 是任何后续 RAG / 模型 / prompt 优化的前置 gate,本身高价值;P0-2 是 1-2 天 0 风险的免费收益。
4. **2 周后基于数据决定**:走完 P0-1 + P0-2,数据出来再选 P1 是否做、要不要冻结 RAG、要不要 redirect 到内容/UX。

**不承诺 P1/P2**——本计划只覆盖 2 周。后续 phase 用真实数据驱动。

---

## 1. Karpathy Gate

### Assumptions(开始前先暴露)

1. P0-1 评估 harness 上生产 1-2 周后能拿到**有意义的真实流量样本**(retrieval_empty_rate / per-shape Recall@5 / 低评 retrieval pattern)。若流量太小(< 1000 queries / 周),数据可能没统计意义,会延后决策。
2. 60-100 条 golden set 标注质量决定一切。**内部建筑考试专家参与是硬要求**,LLM 自动生成不算。
3. 开 `provenance_boost_enabled` 和 `compiled_truth_enabled` 不会引发 contract guard / 现有测试失败(代码已实现,只默认关——但要验)。
4. 后续 phase(P1/P2)**等 P0-1 数据出来再决定**,本计划不预先承诺。

### Simplest path

- P0-1 评估 harness 本质是 `(query, expected_chunk_ids)` → `pipeline.search` → Recall/MRR/NDCG。**不重写主链路,不动 contract**,只在外面套一层 evaluator。
- P0-2 是 2 行 env 默认值 + 测试 + eval baseline 对比。**0 代码改动**。
- 不引外部依赖(无 Redis / GPU / 新 vector DB)。

### Change boundary

| 允许触碰 | 不许顺手改 |
|---|---|
| 新建 `deeptutor/services/rag/eval/`(metrics + golden_set + harness) | `supabase.py::search` 主链路 |
| 新建 `eval/datasets/rag_golden_v1.json`(60-100 条人工标注) | `contracts/rag.md`(契约不动) |
| 新建 `scripts/run_rag_eval.py` CLI | `RAGService` / `RAGTool` 对外契约 |
| 改 `_load_search_config:1627, 1640` 两个 env 默认值 | `_AUTHORITY_ORDER` / `_AUTHORITY_RANK` 常量 |
| 新建 `tests/services/rag/eval/*`(测试) | 任何 Supabase 端 SQL function |
| 改 `eval/gates.yaml`(新增 `rag_retrieval_quality_gate`) | LlamaIndex pipeline |

### Verification target

**P0-1 Done 标准**:
- `python -m scripts.run_rag_eval --baseline <commit>` 跑出完整 baseline 报告:per-shape(concept/mcq/case/standard/calc)的 `recall@1/5/10`、`mrr`、`ndcg@5`
- 离线测试 ≥ 80% 覆盖(metrics + golden_set 加载 + harness 跑一遍)
- 接入 `eval/gates.yaml` 作为 `rag_retrieval_quality_gate`,PR 必跑
- baseline 报告 commit 到 `docs/plan/2026-XX-XX-rag-baseline-report.md`

**P0-2 Done 标准**:
- `provenance_boost_enabled` 默认 True,`compiled_truth_enabled` 默认 True
- 所有现有 RAG 测试无回归(`tests/services/rag/` 全绿)
- P0-1 baseline 上对比"关 vs 开":Recall@5 不下降;**期望** authority-aware case 上 +5pp,learner-targeted query 上 +3pp
- 改动落 commit + 在 staging 跑 1 周 shadow 观察

**2 周整体 Done 标准**:
- 有 baseline 数据
- 知道 RAG 当前 per-shape Recall@5 真实值
- 知道 P0-2 对 Recall 的真实影响(数据,非估计)
- 输出 1 份 1-2 页决策建议(继续 RAG 优化 vs 冻结 vs redirect)给你

---

## 2. P0-1:RAG 评估 harness(1.5-2 周)

### Why

`tests/services/rag/` 3886 行测试**零 IR 度量**(`recall@k / mrr / ndcg` 全 grep 空)。任何后续 RAG 改动(P0-2 包括)无法用数据证明是改善还是退化。**先建度量,再谈优化**。

### What

#### 模块结构

```
deeptutor/services/rag/eval/
├── __init__.py
├── metrics.py          # compute_recall_at_k / compute_mrr / compute_ndcg / compute_per_shape
├── golden_set.py       # RetrievalGoldenSet dataclass + JSON loader + schema 校验
├── harness.py          # 跑 pipeline.search,对照 expected,聚合结果

eval/datasets/
└── rag_golden_v1.json  # 60-100 条人工标注

scripts/
└── run_rag_eval.py     # CLI: --baseline <commit> --candidate <commit> 出对比报告

tests/services/rag/eval/
├── test_metrics.py
├── test_golden_set.py
└── test_harness.py
```

#### Golden set 标注规格

- **60-100 条**,按 query_shape 分层:
  - `concept_like`:12-20 条
  - `mcq_like`:12-20 条
  - `case_like`:12-20 条
  - `standard_like`:12-20 条
  - `calc_like`:12-20 条
- **每条 schema**:

```json
{
  "id": "rag-eval-001",
  "query": "GB50300-2019 第 5.3.2 条对混凝土养护温度有什么规定?",
  "query_shape": "standard_like",
  "expected_source_types": ["standard", "standard_code_exact"],
  "expected_chunk_ids": ["chunk_abc123", "chunk_def456"],
  "expected_keywords_in_top_k": ["GB50300", "5.3.2", "养护温度"],
  "expected_exact_question_match": false,
  "annotator": "内部专家姓名 / id",
  "annotated_at": "2026-05-XX",
  "notes": "标准题,主要测 standard_code_exact 通道是否优先命中"
}
```

- **标注流程**:
  1. 从生产 Langfuse trace 抽 200 条真实 query,按 query_shape 分桶
  2. 内部建筑考试专家逐条标注 expected chunks(看实际 chunks 库)
  3. 双盲交叉验证(两位专家独立标注 → 不一致项讨论)
  4. v1 ship 60-100 条,后续可加到 200+

#### Metrics 实现

```python
# deeptutor/services/rag/eval/metrics.py

def compute_recall_at_k(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    k: int,
) -> float:
    if not expected_chunk_ids:
        return 0.0
    top_k_set = set(retrieved_chunk_ids[:k])
    hits = sum(1 for ec in expected_chunk_ids if ec in top_k_set)
    return hits / len(expected_chunk_ids)

def compute_mrr(retrieved: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in expected_set:
            return 1.0 / rank
    return 0.0

def compute_ndcg_at_k(...): ...

def compute_per_shape(
    results: list[EvalResult],
) -> dict[str, dict[str, float]]:
    # 按 query_shape 分桶,每桶出 recall@1/5/10, mrr, ndcg@5
    ...
```

#### Harness 接入主链路

```python
# deeptutor/services/rag/eval/harness.py

async def run_eval(
    golden_set: RetrievalGoldenSet,
    *,
    kb_name: str,
    env_override: dict[str, str] | None = None,
) -> EvalReport:
    rag_service = RAGService()
    results = []
    for item in golden_set.items:
        with _env_context(env_override):  # 临时改 env 比较 baseline vs candidate
            evidence_bundle = await rag_service.search(
                query=item.query,
                kb_name=kb_name,
                intent="",  # eval 不走 intent 强制路径
            )
        retrieved_chunk_ids = [
            block.get("chunk_id")
            for block in evidence_bundle.get("evidence_bundle", {}).get("content_blocks", [])
        ]
        results.append(EvalResult(
            item=item,
            retrieved_chunk_ids=retrieved_chunk_ids,
            recall_at_5=compute_recall_at_k(retrieved_chunk_ids, item.expected_chunk_ids, k=5),
            ...
        ))
    return EvalReport(results=results, per_shape=compute_per_shape(results))
```

#### CLI 输出格式

```bash
$ python -m scripts.run_rag_eval --baseline current --candidate p0-2-enabled

RAG Retrieval Quality Comparison
================================
Baseline:  current (ef0f9904)
Candidate: p0-2-enabled (env SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=true, SUPABASE_RAG_COMPILED_TRUTH_ENABLED=true)
Golden set: rag_golden_v1.json (78 items)

Per-shape Recall@5:
                  baseline  candidate  Δ
  concept_like      0.683    0.683     +0.000
  mcq_like          0.756    0.792     +0.036  ↑
  case_like         0.611    0.628     +0.017  ↑
  standard_like     0.812    0.871     +0.059  ↑↑  (provenance_boost 生效)
  calc_like         0.450    0.450     +0.000
  WEIGHTED          0.706    0.745     +0.039  ↑

Per-shape MRR:
  ...

Overall: Recall@5 +3.9pp, MRR +0.04. PASS rag_retrieval_quality_gate.
```

### Done = 通过的 acceptance test 清单

- [ ] `deeptutor/services/rag/eval/` 全部模块代码 + ≥ 80% 离线测试覆盖
- [ ] `eval/datasets/rag_golden_v1.json` 60+ 条标注完成,双盲交叉验证通过
- [ ] `scripts/run_rag_eval.py` 能跑出 baseline + candidate 对比 markdown 报告
- [ ] `eval/gates.yaml` 加入 `rag_retrieval_quality_gate`,PR 必跑
- [ ] 跑一次 current main(`origin/main` HEAD)的 baseline,**结果落盘** `docs/plan/2026-XX-XX-rag-baseline-report.md`
- [ ] contract guard 全绿
- [ ] 现有所有 RAG 测试 (`tests/services/rag/`) 无回归

### 估时分解

| 子任务 | 估时 |
|---|---|
| `metrics.py` + 离线测试 | 2 天 |
| `golden_set.py` + schema + loader + 测试 | 1 天 |
| `harness.py` + 主链路接入 + 测试 | 2 天 |
| `scripts/run_rag_eval.py` CLI + markdown 输出 | 1 天 |
| `eval/gates.yaml` 接入 + CI 跑通 | 1 天 |
| **代码侧累计** | **7 天 ≈ 1.5 周** |
| Golden set 60+ 条专家标注 + 双盲 | **3-5 天**(取决于专家可用度,可并行代码侧) |
| baseline 数据 commit | 0.5 天 |
| **总计(代码 + 标注并行)** | **~2 周** |

### 风险登记

| 风险 | 级别 | 缓解 |
|---|---|---|
| **Golden set 标注质量低 → eval 失真** | **高** | 内部专家强制参与;双盲交叉验证;v1 ship 后允许迭代到 v2 |
| 主链路接入时发现 evidence_bundle schema 缺 chunk_id | 中 | 已 grep 实证 chunk_id 在 `_search_source:1670` 透传,有;若 fallback 路径丢字段,加补丁 |
| 60 条样本统计意义不足 | 中 | v1 60 条求 lower bound,后续可加到 200+;per-shape 分桶可缓解 |
| 标注耗时超预期专家不够忙活 | 中 | 代码侧可独立先跑通(用 mock golden set),等专家标注 ready 再切真集 |
| `RAGService.search` 拒绝 eval 期间的频繁调用(Supabase rate limit) | 低 | eval 内置 sleep + retry;若 DashScope rerank 配额触发,临时关 rerank 跑 |

---

## 3. P0-2:开 2 个已实现未开的 FF(1-2 天)

### Why

70/100 评估实证:**两项关键功能完整实现但默认 disabled**——是免费午餐。

| 配置项 | 位置 | 默认 | 实现 | 开启即得 |
|---|---|---|---|---|
| `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` | `supabase.py:1640` | False | `provenance.py:66 apply_provenance_ranking` + 8 层 `_AUTHORITY_RANK` 完整 | authority-aware ranking(exact_question +0.04 / standard_code_exact +0.02 / exact_question 命中硬置顶) |
| `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` | `supabase.py:1627` | False | `compiled_truth_source.py` + `_compiled_truth_plan` 完整,**shadow 已默认开** | 学员弱点 / 错因 / 训练标签作为 evidence 进 RRF |

### What

#### 改动

```python
# deeptutor/services/rag/pipelines/supabase.py

# 第 1627 行
- compiled_truth_enabled=_env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", False),
+ compiled_truth_enabled=_env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", True),

# 第 1640 行
- provenance_boost_enabled=_env_flag("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", False),
+ provenance_boost_enabled=_env_flag("SUPABASE_RAG_PROVENANCE_BOOST_ENABLED", True),
```

加配套测试:

```python
# tests/services/rag/test_provenance_boost_default_on.py
def test_provenance_boost_default_enabled() -> None:
    """Regression: provenance boost should default ON after P0-2."""
    config = _load_search_config_with_minimal_env()
    assert config.provenance_boost_enabled is True

def test_provenance_boost_respects_explicit_off() -> None:
    """If user explicitly sets env=false, respect it (FF 灰度通道还在)."""
    os.environ["SUPABASE_RAG_PROVENANCE_BOOST_ENABLED"] = "false"
    config = _load_search_config_with_minimal_env()
    assert config.provenance_boost_enabled is False
    del os.environ["SUPABASE_RAG_PROVENANCE_BOOST_ENABLED"]

# tests/services/rag/test_compiled_truth_default_on.py
# 同款
```

### Done = acceptance test 清单

- [ ] 改 `_load_search_config:1627, 1640` 默认值 → True
- [ ] 2 个新测试 pass
- [ ] 现有 `tests/services/rag/` 全部测试无回归
- [ ] 跑一次 P0-1 eval harness,confirm Recall@5 不下降(per-shape)
- [ ] **期望命中**:`standard_like` Recall@5 +5pp(provenance boost 在 standard_code_exact / standard_precision 通道生效);`mcq_like` / `case_like` +3pp(exact_question / questions_bank authority boost)
- [ ] **期望命中**(compiled_truth):若 KB 有 compiled_learning_truth 数据(即用户有学习记录),learner-targeted query 上 Recall@5 +3pp;若没数据,中性
- [ ] staging shadow 1 周观察 retrieval_empty_rate / avg_top1_sim 趋势,无退化再上 prod
- [ ] 改动 commit 落 origin/main + 上 Aliyun(走 `redeploy_aliyun_fast.sh`)

### 风险登记

| 风险 | 级别 | 缓解 |
|---|---|---|
| `provenance_boost` 让 exact_question 过强,挤掉某些 standard 召回 | 中 | P0-1 eval 拦截;FF 仍存(env override 可关) |
| `compiled_truth_enabled=True` 但实际 KB 没数据 → 中性 | 低 | shadow 模式已跑,真开不会改变行为,只是 trace 上更明显 |
| 与并发 agent 改 RAG 模块冲突 | 中 | RAG 单一权威 `RAGService` 不允许并行重写;改前先看 `docs/plan/INDEX.md` 看有无并发计划 |

### 估时

- 代码改 + 测试:**4 小时**
- staging 跑 + 观察:**1 周(嵌入 P0-1 期间)**
- prod 部署:**0.5 小时**(走标准 `redeploy_aliyun_fast.sh`)

---

## 4. 2 周后的决策点(用真实数据驱动)

**P0-1 + P0-2 完成后**,基于 baseline 数据决定下一步:

### Decision Tree

```
看 P0-1 baseline 数据 + 用户反馈数据
│
├─ Weighted Recall@5 ≥ 0.85  且 retrieval_empty_rate < 10%
│     └─ 结论:RAG 不是当前瓶颈 → **冻结 RAG**,资源转去:
│            • 内容覆盖度(规范库 / 题库扩充)
│            • 模型升级(已在做的 cross-model eval 加深)
│            • mobile UX
│
├─ Weighted Recall@5 ∈ [0.70, 0.85)  或  某个 shape 明显拖后腿
│     └─ 结论:**针对性优化**,只做最高 ROI 的 1-2 个 P1 item
│            • 若 standard_like / case_like 弱 → 推 P1-3 clause v2 分块标准(协调外部数据流程)
│            • 若 concept_like 弱锚 query 召回差 → 推 P0-3 LLM rewriter fallback(3-5 天)
│            • 若 LLM 回答幻觉率高 → 推 P1-4 hallucination guard(1 周)
│            • 不全做 P1,只挑数据最支持的 1-2 项
│
└─ Weighted Recall@5 < 0.70
      └─ 结论:**RAG 是真瓶颈**,全做 P1(6-8 周)
             • P1-1 结构化 context 注入
             • P1-2 检索结果级语义 cache
             • P1-3 clause v2 分块
             • P1-4 hallucination guard
             • P1-5 hybrid 权重 grid search
```

**这个决策点不在本计划承诺范围**——P0-1 + P0-2 完成后单开 ADR 决策。

---

## 5. 不做的事(non-goals)

1. **不**做 P1/P2 任何项目——等 P0-1 数据决定
2. **不**改 `contracts/rag.md` 契约——P0-1 + P0-2 不触碰契约边界
3. **不**改 LlamaIndex 本地管道——不用
4. **不**改 Supabase 端 `search_unified / search_questions_bank_text` SQL function——外部数据流程
5. **不**引外部依赖(Redis / GPU / 新 vector DB)
6. **不**重写 `supabase.py::search` 主链路
7. **不**把 eval harness 塞进生产 hot-path——只 offline / prerelease gate
8. **不**让 LLM 自动生成 golden set 标注——专家人工标注
9. **不**预先承诺 2 周后的 phase——基于数据决定

---

## 6. 与契约 / 单一权威纪律的关系

按 `AGENTS.md §5.7` Single Authority Hard Gate + `contracts/rag.md`:

- **`RAGService` 仍是唯一 grounding 入口** —— eval harness 通过 `RAGService.search` 调用,不绕过。
- **`evidence_bundle` schema 不动** —— eval 只读 `content_blocks[].chunk_id`,不改字段。
- **`_AUTHORITY_ORDER` / `_AUTHORITY_RANK` 不动** —— P0-2 只开 `provenance_boost_enabled` flag,启用既有 ranking 逻辑。
- **`contracts/rag.md` 不动** —— 本计划无契约级改动。

---

## 7. 上 `docs/plan/INDEX.md`

按 AGENTS Plan Directory Discipline,新计划必须挂索引。在 `docs/plan/INDEX.md` 加:

```markdown
- [2026-05-28 RAG 诊断优先 + 免费午餐(2 周)](2026-05-28-rag-diagnostic-first-prd.md) — P0-1 评估 harness + P0-2 开 2 FF,数据驱动后续决策
```

(等你同意后我挂)

---

## 8. 待你决定的 3 件事

1. **挂 `docs/plan/INDEX.md`** —— 现在挂?
2. **Golden set 标注专家** —— 内部建筑考试专家可用?2 周内能投 3-5 天?
3. **谁来执行 P0-1 代码** —— 我下一步直接开干,还是先 `/gstack-plan-eng-review` 一轮?

---

## 附:计划版本史

- v1(2026-05-28 上午):基于两份评估报告口述,基线多处错误。**已删除**。
- v2(2026-05-28 中午):基于 codegraph 实证,代码证据级别基线。**已删除**。
- **v3(本文件,2026-05-28 下午)**:基于 70/100 评估报告 + 战略反思后的 scope 决策(诊断优先 + 免费午餐)。

—— 完 ——
