# 2026-06-06 WeChat TutorBot Question Source Manifest

## Purpose

This manifest records the question-bank authority used by the WeChat TutorBot real-exam QA loop.

Current important boundary:

- The active DeepTutor repo does not contain `docs/2026/题库`.
- The available source bank is external to this repo:
  `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/`
- Future QA rows must reference this manifest, file hash, and resolved `question_id` / `chunk_id`; otherwise the run does not prove which official source owned the answer.

This file is a manifest only. It does not copy production DB data and does not write canonical learner truth.

## Source Structure

Observed JSON structure:

```text
{
  "meta": { "source": "...", "generated_at": "...", "version": "..." },
  "stats": { "total_chunks": N, "total_exercises": N, ... },
  "chunks": [...]
}
```

## Source Files

Generated with:

```bash
find /Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库 -name 'FINAL_CLEANED_*.json' -type f -print0 | xargs -0 shasum -a 256
```

| File | Chunks | Exercises | Source label | SHA256 |
| --- | ---: | ---: | --- | --- |
| `FINAL_CLEANED_EXAM_V2015.json` | 35 | 52 | 2015年一级建造师《建筑实务》考试真题及答案解析 | `8ef277d588d7b56066538912b8952f54d44924902bef02518c64d3d18d43b248` |
| `FINAL_CLEANED_EXAM_V2016.json` | 35 | 53 | 2016年一级建造师《建筑实务》考试真题及答案解析 | `2549e4f5fe5971f80cc810ada00d49dc02814fc5485bcc48801abda097c3fdbc` |
| `FINAL_CLEANED_EXAM_V2017.json` | 34 | 35 | 2017年一级建造师《建筑实务》考试真题及答案解析 | `a5ec4346428b50ae37b7dc768497bb8eb54aebf48880d9c965ed59bce52fa269` |
| `FINAL_CLEANED_EXAM_V2018.json` | 48 | 50 | 2018年一级建造师《建筑实务》考试真题及答案解析 | `4c68731cbc125c02d702d3f620c2347e85985b8cb9d1f419b02a111073961f8b` |
| `FINAL_CLEANED_EXAM_V2019.json` | 48 | 52 | 2019年一级建造师《建筑实务》考试真题及答案解析 | `9c85553a4c64725292b184fcda1a92acc5cef824c53471e6996da3008a88b6af` |
| `FINAL_CLEANED_EXAM_V2020.json` | 53 | 56 | 2020年一级建造师《建筑实务》考试真题及答案解析 | `e85837c2469c5a824b43629a5ce5ce4b6009a0e2426ee1b5ea84bd05cfe6c4c8` |
| `FINAL_CLEANED_EXAM_V2021.json` | 46 | 59 | 2021年一级建造师《建筑实务》考试真题及答案解析 | `82ac9d9c73aa7e66d551551a4b28966c4a5cf84373327ae322dc6bdfe15636af` |
| `FINAL_CLEANED_EXAM_V2022.json` | 44 | 44 | 2022年一级建造师《建筑实务》考试真题及答案解析 | `315cdc2157208ee75a052be6903b87d85bdc1b4ebea795b85ad8aeb32da3a751` |
| `FINAL_CLEANED_EXAM_V2023.json` | 38 | 61 | 2023年一级建造师《建筑实务》考试真题及答案解析 | `46c0dc9d5633ddb317fead28df6dc7bdd81e9493814ab6828896b5bb5a2b35de` |
| `FINAL_CLEANED_EXAM_V2024.json` | 40 | 39 | 2024年一级建造师《建筑实务》考试真题及答案解析 | `807eccf62d1ca393d737c10b6d18ba70a00bb128ab63f363f39be055d87f2340` |
| `FINAL_CLEANED_EXAM_V2025.json` | 43 | 59 | 2025年一级建造师《建筑实务》考试真题及答案解析 | `78f708cc883cddcf1f7547d2347d34bd387b64ed02e6d12cc052195d2a05987a` |
| `FINAL_CLEANED_ZL500.json` | 403 | 403 | ZL864考证宝典必刷500题2025 | `362fb9ee252130b3a352838e59db60ea5480b1d5a664e178f205aa65e863f8ba` |
| `FINAL_CLEANED_QIANTIZAN.json` | 630 | 630 | SMR章节千题斩2025 | `f3434b93c611a18a9f44fbb9339d4de1a87bc92a223a0908507a49fc3e9c90e9` |

## Ledger Requirement

Every 30-round QA row that claims official-answer authority must include:

- `question_source_authority`: this manifest path
- `source_file`: one of the files above
- `source_hash`: matching SHA256
- `question_id` or `chunk_id`
- `stem_hash`
- `option_surface`: `source` / `query` / `visible_card`
- `official_answer`
- `resolved_authority`: e.g. `exact_question`, `followup_question_context`, `lifecycle_clarification`

## Open Risk

This manifest proves the local source files available during QA. It does not prove those files are the production KB artifact, Supabase source, or deploy-time RAG index. Production release evidence still needs a separate KB artifact/signature check.
