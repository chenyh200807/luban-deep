# tests/fixtures

测试与离线 eval 用的 fixture 数据。本 README 重点说明 **RAG 检索质量 golden set**
(P0-1 / T3) 的标注规范;其余 fixture 见各自文件。

## RAG 检索质量 golden set(P0-1 / T3)

专家人工标注的检索真值,喂给 `tests/services/rag/test_retrieval_quality.py` 的 e2e
gate(`test_rag_retrieval_quality_baseline`),产出 per-shape Recall@K / MRR 报告。

> **硬规则:不允许用 LLM 自动生成标注(`expected_chunk_ids` 的判断)。**
> query 样例可借助工具收集,但「哪些 chunk 才是这条 query 的正确证据」必须由内部
> 建筑考试专家逐条人工判定。

### 文件

| 文件 | 用途 |
|---|---|
| `rag_retrieval_golden_v1.template.json` | 模板。5 个 query_shape 各 1 条骨架,`expected_chunk_ids` 是占位符。 |
| `rag_retrieval_golden_v1.json` | **专家产出**。标注完成后由模板扩充并另存为此名。e2e gate 只认这个文件名;不存在时 gate 自动 skip。 |

### Schema(每条)

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✓ | 唯一标识,建议 `<shape>-NNN`(如 `standard-014`) |
| `query` | ✓ | 真实用户 query(从生产 Langfuse trace 抽) |
| `query_shape` | ✓ | 五选一,见下 |
| `expected_chunk_ids` | ✓ | **专家判定**的正确证据 chunk_id 列表(KB 里真实存在的 id) |
| `annotator` | ✓ | 标注人姓名/工号(双盲交叉用) |
| `notes` | — | 为什么这几个 chunk 才是 expected(为后续迭代留 trace) |

`query_shape` 取值(`test_retrieval_quality.py::_VALID_SHAPES`):
`concept_like` / `mcq_like` / `case_like` / `standard_like` / `calc_like`

### 标注流程(PRD §2)

1. **抽样**:从生产 Langfuse trace 抽 ~200 条真实 query,按 `query_shape` 分桶。
2. **专家标注**:逐条对照 KB 里**实际的 chunks**(不凭记忆)标 `expected_chunk_ids`,填 `notes`。
3. **双盲交叉**:两位专家独立标注同一批 → 不一致项讨论定稿。
4. **数量**:v1 ship **60-100 条**,5 个 shape 分层,**每层 12-20 条**。后续可扩到 200+。
5. **另存**:把定稿写入 `rag_retrieval_golden_v1.json`(替换模板所有占位符)。

### 统计诚实(PRD 3A)

每 shape 12-20 条 → Wilson 95% CI 宽约 ±25% → baseline **只能可靠 detect ≥15pp 的移动**。
报告会自动带 CI,如实呈现。chunk_id 必须 KB 真实存在:gate 跑前 `preflight_check_stale`
批量核验,KB 重灌导致 id 失效会 raise `StaleGoldenSetError` 并列出失踪 id。

### 完成后跑 baseline

```bash
# staging/CI,需要真实 KB + 可达 Supabase
RAG_EVAL_KB_NAME=<eval KB 名> \
  pytest tests/services/rag/test_retrieval_quality.py -k baseline -v -s
```

不设 `RAG_EVAL_KB_NAME` 或 golden 不存在 → gate 自动 skip。报告落
`artifacts/rag_eval/baseline_<GIT_SHA>.md`,随后 commit 到 baseline 报告(T8)。

### P0-2 灰度(与 baseline 同跑)

代码默认 `provenance_boost` / `compiled_truth` 均 **OFF**(契约 `rag.md` §20/§22)。
量化「开启是否改善」要在 staging `.env` 显式开启后再跑一次对比:

```bash
SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=true \
SUPABASE_RAG_COMPILED_TRUTH_ENABLED=true \
RAG_EVAL_KB_NAME=<eval KB> \
  pytest tests/services/rag/test_retrieval_quality.py -k baseline -v -s
```

对比 true vs false 的 per-shape Recall@5(看 Wilson CI 是否显著);数据证明改善后,
才走正式契约变更(改 §20/§22 + 理由)落代码默认 ON。
