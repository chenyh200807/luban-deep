# PDF Source Ledger v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: raw PDF evidence ledger only; not runtime supply, not official score authority.
- PDF files: **95**
- Candidate structured derivative refs: **39**
- Still needing compilation or mapping: **56**

## Status Counts

| Status | Count |
|---|---:|
| `candidate_structured_derivative_refs_available` | 39 |
| `raw_indexed_review_later` | 28 |
| `raw_indexed_needs_standard_json_backfill` | 13 |
| `raw_indexed_needs_textbook_chunking_or_mapping` | 6 |
| `raw_indexed_needs_practice_mapping_or_backfill` | 5 |
| `raw_indexed_needs_formula_mapping_or_backfill` | 2 |
| `raw_indexed_needs_lecture_chunking_or_mapping` | 1 |
| `raw_indexed_needs_exam_mapping_or_backfill` | 1 |

## Category Counts

| Category | Count |
|---|---:|
| `supplement_pdf` | 28 |
| `standard_pdf` | 21 |
| `exam_pdf` | 17 |
| `textbook_pdf` | 11 |
| `lecture_pdf` | 9 |
| `practice_pdf` | 7 |
| `formula_pdf` | 2 |

## P1 Missing Derivative Sample

- `docs/原始数据/PDF/一建建筑实务（智能体资料）_副本/建筑《学天一本通+必刷题》SMR【推荐】/2025年一建【建筑】学天-一本通（精讲班讲义）.pdf` — raw_indexed_needs_lecture_chunking_or_mapping
- `docs/原始数据/PDF/一建建筑实务（智能体资料）_副本/建筑历年真题2015-2025/一建-建筑五年真题.pdf` — raw_indexed_needs_exam_mapping_or_backfill
- `docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）/2025一建《建筑实务》电子教材（可搜索）.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）/2025一建《建筑实务》电子教材（可搜索）_1-164_37-164.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）/2025一建《建筑实务》电子教材（可搜索）_165-219.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）/2025一建《建筑实务》电子教材（可搜索）_220-383.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/建筑实务11.20_副本/2025年一建电子版教材（可搜索版）/2025一建《建筑实务》电子教材（可搜索）_9-36.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/建筑实务11.20_副本/2026一建《建筑》电子版教材 6-8/2026一建《建筑》电子版教材_6-8.pdf` — raw_indexed_needs_textbook_chunking_or_mapping
- `docs/原始数据/PDF/行业标准文件/10、GB 55016—2021建筑环境通用规范.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/11、GB 55016—2021建筑与市政工程施工质量控制通用规范.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/12、GB 50325-2020 民用建筑工程室内环境污染控制标准.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/14、GB 55030—2022建筑与市政工程防水通用规范.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/21、GB 55015—2021建筑节能与可再生能源利用通用规范.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/2、GB50016-2014《建筑设计防火规范》(2018年版).pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/3、GB55034-2022建筑与市政施工现场安全卫生与职业健康通用规范.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/4、GB／T+506402023建筑与市政工程绿色施工评价标准.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/5、GBT50378-2019绿色建筑评价标准(2024年版).pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/6、GB+175-2023通用硅酸盐水泥.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/7、JGJT 498—2024《施工现场建筑垃圾减量化技术标准》.pdf` — raw_indexed_needs_standard_json_backfill
- `docs/原始数据/PDF/行业标准文件/8、GB_T 50328-2014 建设工程文件归档规范(2019年版).pdf` — raw_indexed_needs_standard_json_backfill

## Guardrails

- This ledger preserves PDF source facts and derivative status only.
- Candidate structured derivative refs are unverified hints, not signed PDF -> JSON provenance.
- Existing JSON derivatives still need a PDF -> JSON provenance map before release signing.
- Missing derivative does not mean the PDF is useless; it means it has not been normalized into the current structured source layer.
- No record in this ledger may be consumed as runtime context or official scoring authority without a later signed release artifact.
