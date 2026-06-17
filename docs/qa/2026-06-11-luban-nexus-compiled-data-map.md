# 鲁班 Nexus-like 编译数据地图

本文档记录当前一批 Nexus-like 编译产物的位置、结构和权限边界，供后续 AI/Claude Code/Codex 继续做数据整理、审核、报告和回归 A/B 时使用。

## 核心原则

本批工作落地的是编译闭环：

```text
coverage gap
-> typed work order
-> source candidate evidence
-> strong/weak 分层
-> 审核/回归后才允许进入 runtime
```

这些产物是 compiler workbench，不是 release truth。任何后续 agent 不能把 candidate patch 直接当成 canonical runtime，也不能把学生答卷源材料当成评分 authority。

## 源数据位置

| 数据层 | 路径 | 说明 | 权限边界 |
|---|---|---|---|
| 2026 源材料池 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/` | 教材、规范、讲义、题库、考生答卷源材料 | source pool，不等于 runtime truth |
| 题库 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/` | 真题、答案解析、考生答卷排版 | question/evidence source |
| 考生答卷 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/近三年案例题_按学生答卷排版.md` | 考生答卷文本 | 不是 label authority |
| 教材 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强/` | 教材 content blocks | source evidence lane |
| 标准 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/标准文件/` | 标准条文 JSON | source evidence lane |
| 讲义 | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/讲义/` | 讲义页级 chunks | teaching evidence lane |

## Runtime Supply 位置

| 产物 | 路径 | 作用 | 当前边界 |
|---|---|---|---|
| runtime supply 根 | `deeptutor/services/construction_grading/runtime_supply/` | 版本化运行时供给 shard | 只有 signed/versioned bundle 才能被 runtime 消费 |
| unified knowledge | `deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_unified_knowledge.json` | 教材/标准/讲义/题库聚合后的教学上下文 bundle | teaching context，不是 answer key |
| source alignment repairs | `deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/source_alignment_repairs.json` | 污染源/错路径修复 overlay | release_candidate overlay，仍非 official scoring truth |
| taxonomy index | `deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json` | canonical leaf/node 索引 | 用于对齐与覆盖统计 |

## Workbench 产物位置

| 产物 | 路径 | 关键结构 | 用途 |
|---|---|---|---|
| source/runtime reconciliation | `artifacts/luban_grading_artifacts/docs2026_runtime_reconciliation_20260611/reconciliation_report.json` | `source_lanes`, `coverage`, `blockers`, `next_compile_work_orders`, `safety` | 说明 docs/2026 源数据与 runtime supply 的对应关系 |
| leaf coverage work orders | `artifacts/luban_grading_artifacts/unified_knowledge_leaf_coverage_work_orders_20260611/leaf_coverage_work_orders.json` | `coverage`, `summary`, `work_orders[]`, `safety` | 把 coverage gap 编译成 P0/P1/P2 工作单 |
| P0 source reanchor candidates | `artifacts/luban_grading_artifacts/p0_leaf_source_reanchor_candidates_20260611/reanchor_candidates.json` | `summary`, `reanchor_candidates[]`, `unresolved_leaf_ids`, `safety` | 给 57 个 P0 叶子找源证据候选，并做 strong/weak 分层 |
| P0 candidate patches | `artifacts/luban_grading_artifacts/p0_leaf_reanchor_candidate_patch_20260611/candidate_patch_report.json` | `candidate_patches[]`, `weak_pollution_refinements[]`, `summary`, `safety` | 54 个 strong 候选转成 review-only patch；3 个 weak 候选转污染精修队列 |
| workbench data map | `artifacts/luban_grading_artifacts/p0_leaf_reanchor_candidate_patch_20260611/COMPILED_DATA_MAP.md` | Markdown summary | 当前批次机器生成版数据地图 |

## 当前批次结果

| 指标 | 值 |
|---|---:|
| canonical leaves total | 3158 |
| populated leaves | 395 |
| populated leaf rate | 0.12507916402786573 |
| typed work orders emitted | 405 |
| P0 question_without_knowledge | 57 |
| P1 knowledge_without_question emitted | 120 |
| P2 incomplete_multisource_context | 228 |
| P0 source records scanned | 5358 |
| P0 candidates total | 283 |
| P0 strong candidate leaves | 54 |
| P0 weak-only leaves | 3 |
| candidate patches emitted | 54 |
| weak pollution refinements emitted | 3 |

## P0 Candidate Patch 结构

`candidate_patch_report.json` 中每个 `candidate_patches[]` 大致形态：

```json
{
  "patch_id": "candidate_patch:<leaf_id>",
  "leaf_id": "<canonical leaf id>",
  "leaf_path": "<taxonomy path>",
  "target": "canonical_unified_knowledge.nodes[<leaf_id>].sources",
  "operation": "append_candidate_sources_after_review",
  "patch_status": "review_required_not_installed",
  "source_candidates": [
    {
      "source_lane": "textbook | standard | lecture",
      "source_path": "<relative source json path>",
      "record_id": "<source record id>",
      "score": 8.8333,
      "matched_terms": ["..."],
      "snippet": "...",
      "candidate_only": true
    }
  ],
  "preconditions": {
    "requires_human_or_ai_auditor_review": true,
    "requires_regression_ab_before_runtime_install": true
  }
}
```

含义：这是可审核 patch，不是已经安装的 runtime source。

## Weak Pollution Refinement 结构

3 个 weak 叶子不能直接并入 runtime，因为最佳候选只命中了泛路径词：

| leaf_id | 问题 | 当前处理 |
|---|---|---|
| `1A413022-07-a` | 只命中“基坑支护工程施工”，没有命中“临时用电组织设计/用电组织设计规定”等具体点 | 进入 weak pollution refinement |
| `1A413024-04-b` | 只命中“土石方工程与回填施工”，没有命中“填料选用”等具体点 | 进入 weak pollution refinement |
| `1A413046-06` | 只命中“主体结构工程施工”，没有命中“脚手架验收与检查制度”等具体点 | 进入 weak pollution refinement |

`weak_pollution_refinements[]` 每项包含：

```json
{
  "pollution_risk": "generic_path_term_only",
  "rejected_top_candidate": {
    "matched_terms": ["泛路径词"],
    "snippet": "..."
  },
  "required_specific_terms": ["必须命中的具体术语"],
  "recommended_action": "rerun_source_search_with_specific_terms_or_mark_external_source_required",
  "install_allowed": false
}
```

## 安全边界

本批产物必须保持：

```json
{
  "candidate_only": true,
  "installed_runtime_supply": false,
  "canonical_truth_written": false,
  "official_score_allowed": false,
  "production_write_count": 0,
  "release_truth_claimed": false
}
```

任何后续流程如果要把 54 个 strong patch 并入 runtime，必须先新增一个明确的 `reviewed_patch -> new runtime_supply version -> regression A/B -> release gate` 步骤，不能直接改现有 `canonical_unified_knowledge.json`。

## 下一步

1. 对 54 个 `candidate_patches[]` 做 evidence auditor 审核：确认 snippet 与 leaf_path/keywords 语义一致，不只是同词污染。
2. 对 3 个 `weak_pollution_refinements[]` 用 `required_specific_terms` 重跑更窄搜索；若仍无强候选，标 `external_source_required` 或 `source_missing`。
3. 通过审核的 patch 编译成新的 runtime supply 候选版本，而不是原地修改当前 bundle。
4. 对新 bundle 跑 M34/M35 相关 regression A/B，再决定是否进入 controlled default。
