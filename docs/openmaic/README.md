# OpenMAIC 文档层级说明

本目录用于沉淀“建筑实务 AI 互动课堂”相关的架构、实施、ADR 和历史材料。

自 2026-04-22 起，文档层级固定如下。自 2026-04-24 起，本目录迁入 `docs/openmaic/`；旧 `doc/openmaic/` 只保留为历史路径，不再新增内容。

## 1. Canonical

以下文件是当前唯一 authority：

- [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
- [建筑实务AI互动课堂_Implementation_Plan_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)
- [ADR-001-lesson-ir-authority.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-001-lesson-ir-authority.md)
- [ADR-002-classroom-turn-transport.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-002-classroom-turn-transport.md)
- [ADR-003-quality-evaluation-release-gate.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-003-quality-evaluation-release-gate.md)
- [ADR-004-source-ingestion-provenance.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-004-source-ingestion-provenance.md)
- [ADR-005-mini-program-surface-renderer-contract.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md)
- [ADR-006-supabase-knowledge-base-reuse.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md)
- [banned-v1.1-patterns.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/banned-v1.1-patterns.md)

职责分工：

- `架构与实施收口_v1.2`：定义 authority、transport、状态机、P0/P1/P2 边界、release gate。
- `Implementation_Plan_v1.2`：唯一 live implementation plan，可直接派工。
- `ADR-001`：`LessonIRService`、唯一 writer、revision / CAS、projection 规则。
- `ADR-002`：课堂问答 transport、thin adapter 规则、grounding_context。
- `ADR-003`：`LessonQualityEvaluator`、质量分、发布 gate、人工教研验收。
- `ADR-004`：资料解析、source chunk、citation、provenance、版权 gate。
- `ADR-005`：微信小程序主表面、Scene Runtime Core、wx renderer、job progress、socket、上传、宿主包同步。
- `ADR-006`：现有 Supabase RAG 知识库复用、`kb_chunks / questions_bank` 到 `source_manifest` 的映射、知识覆盖 gate。
- `banned-v1.1-patterns`：旧设计的禁用模式清单。

产品表面约束：

- P0 学员端主表面是 `wx_miniprogram`，不是 Web。
- `yousenwebview/packageDeeptutor` 是佑森宿主内交付包，必须保留宿主路由、登录、会员、点数和 workspace shell 适配。
- Web/Admin 只作为教研审核、运营管理、导出预览或后续后台，不是 P0 学员端播放器 authority。
- HTML export 是导出 artifact，不等于 Web 主产品表面。

如果这些文档之间发生冲突，优先级如下：

1. `CONTRACT.md`
2. `contracts/index.yaml`
3. `建筑实务AI互动课堂_架构与实施收口_v1.2.md`
4. `ADR-001 / ADR-002 / ADR-003 / ADR-004 / ADR-005 / ADR-006`
5. `建筑实务AI互动课堂_Implementation_Plan_v1.2.md`
6. 其他 supporting / historical 文档

## 2. Supporting

以下文件只保留背景说明和设计素材职责：

- [建筑实务AI互动课堂_技术实现蓝图_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_技术实现蓝图_v1.1.md)
- [建筑实务AI互动课堂_实施任务拆解_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_实施任务拆解_v1.1.md)

限制：

- 不能再单独定义 authority
- 不能再单独定义 API 真相
- 不能再单独定义表结构真相
- 不能再单独定义 P0/P1/P2 和发布门槛

## 3. Historical

以下文件为历史快照，不再作为当前实施依据：

- `建筑实务AI互动课堂_Implementation_Plan_v1.0.docx`
- `建筑实务AI互动课堂_PRD_v1.0.docx`
- `建筑实务AI互动课堂_文档包_v1.0/`

## 4. 开发规则

开始实现前，必须先读：

1. [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
2. [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
3. [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
4. 对应 ADR
5. [建筑实务AI互动课堂_Implementation_Plan_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)

## 5. 文档治理规则

- 不允许继续维护第二份 live task plan。
- 不允许把 v1.1 文档里的旧表、旧 API、旧状态机直接复制进新实现。
- 任何涉及 `lesson_ir`、`/api/v1/ws`、learner-state 写回、质量评测、来源治理的改动，都必须同时检查对应 ADR 和 contract。
- 若新增 capability、schema 或 transport，必须先有 ADR，再有实现。
- OpenMAIC 只作为体验标杆和 black-box benchmark；禁止复制其源码、Prompt、Schema、UI、素材或具体生成流程。
- 不允许先实现 Web-only player 再把微信小程序当二期适配；P0 验收必须覆盖微信开发者工具或真机 smoke。
