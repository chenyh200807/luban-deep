# OKF Source Alignment v0

## 范围

本次把 `case_rubric_canonical.json` 中的 25 个案例，与 `json_source_ledger_v0` 登记过的清洗真题 JSON 做 case-level source alignment。

输入：

- `docs/原始数据/数据盘点/extractions/case_rubric_canonical.json`
- `docs/原始数据/数据盘点/extractions/json_source_ledger_v0/sources.jsonl`
- `docs/原始数据/2026_副本/题库/**/FINAL_CLEANED_EXAM_V*.json`

输出：

- `docs/原始数据/数据盘点/extractions/okf_source_alignment_v0/report.json`
- `docs/原始数据/数据盘点/extractions/okf_source_alignment_v0/report.md`
- `docs/原始数据/数据盘点/extractions/okf_source_alignment_v0/case_alignment.jsonl`

复现命令：

```bash
python docs/原始数据/数据盘点/scripts/build_okf_source_alignment.py --generated-at 2026-06-19T00:00:00+08:00
python -m pytest tests/scripts/test_okf_source_alignment.py -q
```

## 结果

| 项目 | 数量 |
|---|---:|
| target cases | 25 |
| aligned cases | 25 |
| ordinal sub-question matches | 9 |
| case-level only | 16 |

状态：

```text
case_source_alignment_ready
```

## 解释

所有 25 个 canonical rubric case 都已经找到清洗真题 JSON 中的 case chunk，并保留了：

- source ledger 记录
- source file hash
- chunk id
- page
- original anchor
- JSON path
- sub-question alignment 状态

其中 9 个 case 的清洗 JSON 已经按小问拆成与 rubric 小问数一致的 exercises，因此标为 `ordinal_match`；另外 16 个 case 先标为 `case_level_only`，表示题干 chunk 可追溯，但小问级拆分还需后续增强。

## Authority Guard

本产物只是 source alignment，不写 runtime supply、不写 official score。

```json
{
  "runtime_consumable": false,
  "canonical_write_allowed": false,
  "learner_truth_write_allowed": false,
  "gbrain_write_allowed": false,
  "production_registry_write_allowed": false,
  "official_score_allowed": false
}
```

## 结论

`ledger_to_okf_source_alignment` blocker 已解除。OKF 可以继续扩展到完整 candidate scope，但仍然只能作为 source-layer candidate，不是签发 runtime supply。
