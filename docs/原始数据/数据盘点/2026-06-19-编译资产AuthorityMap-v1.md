# 编译资产 Authority Map v1

- **日期**: 2026-06-19
- **目标**: 在 `compiled_asset_ledger_v1` 之后，明确每组编译资产能不能被 AI / runtime 读取、谁是 authority、哪些必须禁止直读。
- **产物**: `docs/原始数据/数据盘点/extractions/compiled_asset_authority_map_v1/`
- **状态**: `compiled_asset_authority_map_only`，不是 runtime install，不是 official score authority，不写 LearnerState / GBrain / production registry。

## 结论先行

当前可以安全交给 AI 的不是 `artifacts/*` payload 本身，而是 authority map。

结果是:

- 21 个 compiled asset group 已完成 authority 分类。
- `artifacts/*` 直读 runtime 的允许数是 0。
- 真实 runtime pointer / manifest 只认 `deeptutor/services/construction_grading/runtime_supply/` 根下文件，共 15 条。
- 其中 4 条是 `published=true` 且具备 hash gate，可作为 runtime consumer 的候选读取入口。
- 其余 11 条仍是 release candidate / blocked / no-publish-flag，不能作为 runtime default。

## 分类结果

| 类别 | 数量 | 允许用途 | 禁止用途 |
|---|---:|---|---|
| `candidate_compiler_workbench_read_only` | 7 | LLM compiler 组织候选知识、rubric、policy | runtime 直读、official score、LearnerState |
| `review_or_audit_evidence_read_only` | 6 | QA / 评审 / 共识证据复核 | canonical truth、runtime default |
| `multimedia_or_product_candidate_read_only` | 4 | 产品资产盘点、视觉/微课候选审查 | 教学/判分 truth |
| `auxiliary_artifact_or_report_read_only` | 3 | 只读辅助报告和审计线索 | 自动晋升 |
| `runtime_supply_pointer_gated` | 1 | 逐 pointer 做 published/status/hash/schema gate | 把目录整体当 runtime truth |

## Runtime pointer 结果

| 指标 | 数量 |
|---|---:|
| runtime pointer / manifest | 15 |
| published + hash-gated | 4 |
| release candidate / blocked | 11 |
| artifacts direct runtime read allowed | 0 |

当前 4 个 published + hash-gated 指针是:

- `kb_v5_chunks_full`
- `lecture_teaching_cards`
- `case_rubric_full`
- `topic_waterproof`

注意: `published=true` 仍不等于 official score，也不等于 LearnerState / GBrain 写入许可。它只表示 runtime consumer 可以在 hash/schema/consumer gate 通过后读取相应 packet。

## 关键修正

这次特意防住一个容易犯的错:

- `artifacts/luban_grading_artifacts/.../runtime_supply/manifest.json` 这类名字里带 `runtime_supply` 的 workbench 产物，不算真实 runtime supply。
- 真正 runtime supply authority 只认 `deeptutor/services/construction_grading/runtime_supply/`。
- `artifacts/*` 即使长得像 runtime 包，也只能先归入 candidate / workbench / review evidence。

## AI 第一入口

后续 AI 判断编译资产能不能用，优先读:

1. `docs/原始数据/数据盘点/extractions/compiled_asset_authority_map_v1/manifest.json`
2. `docs/原始数据/数据盘点/extractions/compiled_asset_authority_map_v1/group_authority.json`
3. `docs/原始数据/数据盘点/extractions/compiled_asset_authority_map_v1/runtime_pointers.jsonl`
4. `docs/原始数据/数据盘点/extractions/compiled_asset_authority_map_v1/consumer_policy.json`
5. `docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/files.jsonl`

## 三原则落地

- **Thin wrappers, fat skills**: authority map 只是薄索引和消费策略；真正知识编译、判分签发、runtime packet 构建仍归各自 compiler / skill / runtime service。
- **First principles**: 一等事实是“谁能读、谁不能读、什么 gate 之后才能读”，不是“文件名像 runtime 就能用”。
- **Less is more**: 不新增 runtime registry，不移动 payload，不复制第二套 truth，只在数据盘点层给出消费边界。

## 诚实边界

- `compiled_asset_authority_map_v1` 不签发 runtime。
- published pointer 仍需 hash/schema/consumer gate。
- candidate workbench 可以被 LLM 组织、提炼、批判，但不能直接升级为 canonical truth。
- official score、LearnerState、GBrain、production registry 仍然全部禁止直写。

## 下一步

下一步应做 `asset_gap_map_v1`:

1. 哪些 PDF 仍无结构化正文 / chunk manifest。
2. 哪些结构化题目缺 taxonomy、answer provenance、rubric 或 score。
3. 哪些 published runtime pointer 缺 consumer 级真实使用证据。
4. 哪些 candidate workbench 需要进入 signed release 流水线，哪些应归档为只读证据。
