# OKF Candidate Scope v0

## 范围

本次从 `case_rubric_canonical.json` 和 `okf_source_alignment_v0` 生成完整 OKF-like source-layer candidate scope。

输入：

- `docs/原始数据/数据盘点/extractions/case_rubric_canonical.json`
- `docs/原始数据/数据盘点/extractions/okf_source_alignment_v0/case_alignment.jsonl`

输出：

- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/manifest.json`
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/cases.jsonl`
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/rubrics.jsonl`
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/scoring_points.jsonl`
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/scoring_point_index.json`
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/summary.md`

复现命令：

```bash
python docs/原始数据/数据盘点/scripts/build_okf_candidate_scope.py --generated-at 2026-06-19T00:00:00+08:00
python -m pytest tests/scripts/test_okf_candidate_scope.py -q
```

## 结果

| 项目 | 数量 |
|---|---:|
| cases | 25 |
| rubrics | 117 |
| scoring points | 431 |

状态：

```text
source_layer_candidate_complete
```

## 产物语义

`okf_candidate_scope_v0` 是完整 source-layer candidate，不是 signed runtime supply。

每个 scoring point 保留：

- point id
- case / rubric / sub-question 归属
- 采分点文本
- 分值候选
- point type
- judge rule
- canonical rubric JSON path
- 清洗真题 JSON source
- question chunk / page / anchor
- runtime guard

## Authority Guard

```json
{
  "authority_status": "candidate_review",
  "runtime_consumable": false,
  "canonical_write_allowed": false,
  "learner_truth_write_allowed": false,
  "gbrain_write_allowed": false,
  "production_registry_write_allowed": false,
  "official_score_allowed": false
}
```

## 结论

OKF source-layer 的第一阶段目标已经落地：25 个案例、117 个 rubric、431 个 scoring point 均已生成 candidate artifacts，并可通过 `scoring_point_index.json` 检索。

下一步不是继续扩格式，而是进入签发前验证：

1. source/STORM review ledger
2. deterministic schema validator
3. adversarial scoring guard
4. signed runtime_supply candidate
5. shadow consumer
