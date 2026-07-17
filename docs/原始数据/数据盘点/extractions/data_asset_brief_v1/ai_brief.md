# AI Data Asset Brief v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: asset inventory only; not runtime supply, not official scoring, not learner truth.
- Raw asset files: **1,655** (4.44 GB)
- Cleaned JSON sources: **383**
- PDFs: **95**
- Images/render evidence: **615**
- Compiled/artifact files indexed: **7,133** (1.07 GB)

## One-Minute Takeaways

- 优先目标是全数据资产总账，而不是先接 production runtime consumer。
- 结构化 JSON 已有 383 个，足够让 AI 快速知道教材、真题、讲义、标准、taxonomy 的入口。
- 真题层有 555 道练习，其中案例题 218、选择题 337。
- 章节练习有 1,033 道，适合客观题闭环和错因解释。
- PDF 有 95 个；逐 PDF ledger 已生成，仍需对未映射 PDF 做 chunking 或 provenance backfill。
- 编译资产 ledger 已收录 7,133 个 artifacts/runtime 文件，复制 623 个小型 manifest-like 快照；payload 原地保留。
- OKF-like 候选评分工件已覆盖 25 cases / 117 rubrics / 431 scoring points，但仍是 candidate-only。

## Asset Buckets

| 资产桶 | 数量 | 单位 | 可用状态 | AI 首入口 |
|---|---:|---|---|---|
| 全原始资产文件 | 1,655 | file | inventory_ready | `docs/原始数据` |
| 清洗 JSON 源 | 383 | json_file | machine_readable_ledger_ready | `docs/原始数据/数据盘点/extractions/json_source_ledger_v0/sources.jsonl` |
| 历年真题结构化 JSON | 11 | year_file | structured_high_with_case_rubric_gap | `docs/原始数据/2026_副本/题库/*/FINAL_CLEANED_EXAM_V*.json` |
| 章节练习库 | 1,033 | exercise | structured_high_for_objective_questions | `docs/原始数据/2026_副本/题库/864考证宝典ZL + 章节千题斩SMR` |
| 2026 教材结构化内容 | 650 | content_block | structured_high | `docs/原始数据/2026_副本/2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*fixed.json` |
| 2026 taxonomy | 2,116 | node | structured_high_with_mapping_gaps | `docs/原始数据/2026_副本/taxonomy/FINAL_CLEANED_TAXONOMY2026.json` |
| 规范/标准结构化 JSON | 8 | standard_file | structured_high_for_grounding | `docs/原始数据/2026_副本/标准文件/*.json` |
| 讲义 JSON | 327 | page_json | structured_medium | `docs/原始数据/2026_副本/讲义/*/page_*.json` |
| PDF 原件库 | 95 | pdf_file | raw_evidence_needs_ocr_or_existing_json | `docs/原始数据/PDF` |
| 渲染/图片资产 | 615 | image_file | raw_visual_evidence | `docs/原始数据/2026_副本/**/docx_render_check*` |
| 编译资产 / artifacts 总账 | 7,133 | compiled_asset_file | inventory_ready_not_runtime_truth | `docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/manifest.json` |
| 案例题 OKF-like 候选评分工件 | 431 | candidate_scoring_point | source_layer_candidate_complete | `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0` |

## PDF Compilation Status

- Status: `partially_structured_not_fully_pdf_compiled`
- Raw PDFs indexed: **95** (4.08 GB)
- Structured JSON artifacts exist for textbook, exams, practice questions, lectures, and 8 standard files, but PDF links are still candidate evidence.
- Not yet done: no per-PDF full-text/chunk manifest, no one-to-one PDF→JSON provenance map, no full OCR quality ledger.
- Per-PDF ledger: **39** candidate structured derivative refs, **56** still need compilation or mapping.

## What AI Should Load First

- `docs/原始数据/数据盘点/extractions/data_asset_brief_v1/ai_brief.md` — 最快读懂全资产规模、边界和下一步路由
- `docs/原始数据/数据盘点/extractions/data_asset_brief_v1/manifest.json` — 机器可读 totals、guardrails、entrypoints
- `docs/原始数据/数据盘点/extractions/json_source_ledger_v0/sources.jsonl` — 逐个清洗 JSON source 的路径、bucket、sha256 和 shape
- `docs/原始数据/数据盘点/extractions/pdf_source_ledger_v1/pdf_sources.jsonl` — 逐个 PDF 的 hash、分类、结构化派生状态和下一步动作
- `docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/manifest.json` — 编译资产、artifacts、runtime_supply 的总入口和边界
- `docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/files.jsonl` — 逐个编译资产文件的路径、hash、分组和 authority 状态
- `docs/原始数据/数据盘点/extractions/raw-data-current-profile.json` — 全目录原始资产深度统计
- `docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/manifest.json` — 案例题候选 rubric / scoring point source-layer 范围

## Guardrails

- 本产物只回答资产规模、入口、可用性和边界，不签发 production truth。
- PDF 原件库不等于已 OCR/已结构化/已可检索知识库。
- artifacts/workbench 编译产物不等于 runtime truth；runtime_supply 也必须逐 pointer 检查 published/status。
- 案例题 correct_answer / 候选 scoring point 不等于 official scoring authority。
- 任何 runtime default、LearnerState、GBrain、official score 写入都必须走后续独立 gate。
