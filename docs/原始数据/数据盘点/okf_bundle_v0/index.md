---
type: "BundleIndex"
title: "Luban OKF Bundle v0"
description: "Minimal markdown-and-yaml OKF navigation bundle for Luban data assets."
resource: "docs/原始数据/数据盘点/okf_bundle_v0"
tags:
  - "luban"
  - "okf"
  - "asset-inventory"
timestamp: "2026-06-19T00:00:00+08:00"
status: "markdown_yaml_only"
---

# Luban OKF Bundle v0

This is the minimal OKF shape for Luban data assets: Markdown files with YAML frontmatter and links.

## Core Counts

- Raw asset files: 1107
- Cleaned JSON sources: 383
- PDF files: 95
- Compiled asset files: 5059
- Candidate cases / rubrics / scoring points: 25 / 117 / 431

## OKF Concepts

- [OKF candidate scope](okf/candidate-scope.md)
- [OKF source alignment](okf/source-alignment.md)
- [Asset gap map](gaps/asset-gap-map.md)

## Asset Buckets

- [全原始资产文件](assets/all-raw-files.md)
- [清洗 JSON 源](assets/cleaned-json-sources.md)
- [历年真题结构化 JSON](assets/exam-cleaned-json.md)
- [章节练习库](assets/practice-question-banks.md)
- [2026 教材结构化内容](assets/textbook-2026.md)
- [2026 taxonomy](assets/taxonomy-2026.md)
- [规范/标准结构化 JSON](assets/standards-json.md)
- [讲义 JSON](assets/lecture-json.md)
- [PDF 原件库](assets/pdf-library.md)
- [渲染/图片资产](assets/rendered-images.md)
- [编译资产 / artifacts 总账](assets/compiled-assets-ledger.md)
- [案例题 OKF-like 候选评分工件](assets/case-rubric-candidate-scope.md)

## Format Boundary

OKF here means Markdown + YAML frontmatter + links. Signing, runtime pointer policy, official scoring, LearnerState, and GBrain writes are DeepTutor governance layers, not OKF format requirements.

## Generation

- [Generation log](log.md)
