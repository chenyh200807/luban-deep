# OpenMAIC 文档层级说明

本目录用于沉淀“建筑实务 AI 互动课堂”相关的架构、实施、ADR 和历史材料。

自 2026-04-22 起，文档层级固定如下。

## 1. Canonical

以下文件是当前唯一 authority：

- [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
- [建筑实务AI互动课堂_Implementation_Plan_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)
- [ADR-001-lesson-ir-authority.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/ADR-001-lesson-ir-authority.md)
- [ADR-002-classroom-turn-transport.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/ADR-002-classroom-turn-transport.md)
- [banned-v1.1-patterns.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/banned-v1.1-patterns.md)

职责分工：

- `架构与实施收口_v1.2`：定义 authority、transport、状态机、P0/P1/P2 边界、release gate。
- `Implementation_Plan_v1.2`：唯一 live implementation plan，可直接派工。
- `ADR-001`：`LessonIRService`、唯一 writer、revision / CAS、projection 规则。
- `ADR-002`：课堂问答 transport、thin adapter 规则、grounding_context。
- `banned-v1.1-patterns`：旧设计的禁用模式清单。

如果这些文档之间发生冲突，优先级如下：

1. `CONTRACT.md`
2. `contracts/index.yaml`
3. `建筑实务AI互动课堂_架构与实施收口_v1.2.md`
4. `ADR-001 / ADR-002`
5. `建筑实务AI互动课堂_Implementation_Plan_v1.2.md`
6. 其他 supporting / historical 文档

## 2. Supporting

以下文件只保留背景说明和设计素材职责：

- [建筑实务AI互动课堂_技术实现蓝图_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_技术实现蓝图_v1.1.md)
- [建筑实务AI互动课堂_实施任务拆解_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_实施任务拆解_v1.1.md)

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
3. [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
4. 对应 ADR
5. [建筑实务AI互动课堂_Implementation_Plan_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)

## 5. 文档治理规则

- 不允许继续维护第二份 live task plan。
- 不允许把 v1.1 文档里的旧表、旧 API、旧状态机直接复制进新实现。
- 任何涉及 `lesson_ir`、`/api/v1/ws`、learner-state 写回的改动，都必须同时检查对应 ADR 和 contract。
- 若新增 capability、schema 或 transport，必须先有 ADR，再有实现。
