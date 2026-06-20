# OKF Dry Consumer v0

## 范围

本次只做 OKF-like compiled inspection pack 的干消费验证：

- 读取 `okf_rubric_pilot_v0/manifest.json`
- 读取 `okf_rubric_pilot_v0/question_context_pack.json`
- 读取 `okf_rubric_pilot_v0/scoring_point_index.json`
- 校验 counts 一致
- 校验所有 runtime guard 均为 false
- 输出 receipt

不写 runtime supply，不写 canonical truth，不写 LearnerState / GBrain / production registry / official score。

## 产物

- `docs/原始数据/数据盘点/extractions/okf_dry_consumer_v0/receipt.json`
- `docs/原始数据/数据盘点/extractions/okf_dry_consumer_v0/receipt.md`

复现命令：

```bash
python docs/原始数据/数据盘点/scripts/build_okf_dry_consumer.py --generated-at 2026-06-19T00:00:00+08:00
python -m pytest tests/scripts/test_okf_dry_consumer.py -q
```

## 结果

读取成功：

| 项目 | 数量 |
|---|---:|
| cases | 1 |
| rubrics | 5 |
| scoring points | 15 |

receipt 状态：

```text
dry_consumed_non_runtime
```

## Authority Guard

receipt 继续保留：

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

OKF-like compiled inspection pack 已完成第一层 dry consumer 验证。它证明当前 compiled JSON 可以被安全读取，但仍不是 runtime supply。

下一步 blocker 不是读写能力，而是 source alignment：需要把 `json_source_ledger_v0` 里的 `exam_cleaned_json` 与 rubric candidate 的 year/case/sub-question/page/chunk 对齐，再扩 431 个采分点。
