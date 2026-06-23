# HKUDS v1.4.5 + OpenMAIC 612a147 Clean-room Absorption Record

状态：Draft / clean-room task intake

日期：2026-06-16

适用范围：上游能力吸收、Learning Brain / learner-state、benchmark spine、OpenMAIC / Scene Runtime Core、微信结构化 renderer、source ingestion。

关联约束：

- [CONTRACT.md](../../../CONTRACT.md)
- [contracts/index.yaml](../../../contracts/index.yaml)
- [docs/plan/INDEX.md](../INDEX.md)
- [docs/openmaic/README.md](../../openmaic/README.md)
- [docs/openmaic/ADR-004-source-ingestion-provenance.md](../../openmaic/ADR-004-source-ingestion-provenance.md)
- [docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md](../../openmaic/ADR-005-mini-program-surface-renderer-contract.md)
- [docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md](../../openmaic/ADR-006-supabase-knowledge-base-reuse.md)
- [docs/plan/回归测试工程与质量门/2026-04-23-deeptutor-benchmark-single-spine-prd.md](../回归测试工程与质量门/2026-04-23-deeptutor-benchmark-single-spine-prd.md)
- [docs/plan/学习脑与学员记忆/2026-06-09-learner-memory-lifecycle-execution-plan.md](../学习脑与学员记忆/2026-06-09-learner-memory-lifecycle-execution-plan.md)
- [docs/plan/微信小程序与结构化渲染/2026-04-16-wechat-structured-teaching-renderer-prd.md](../微信小程序与结构化渲染/2026-04-16-wechat-structured-teaching-renderer-prd.md)

## 1. 审计证据

本记录来自 2026-06-16 只读 upstream audit。当前本仓工作区为 detached HEAD `519098b7457fd68a1ae7285d8fd860b8c23d0860`，仓库未配置 `upstream` remote；审计只通过 direct URL fetch / 临时 clone 获取证据，未 merge、pull、port code 或改 runtime。

HKUDS/DeepTutor：

- `main`: `360966a8abfa26863226f48aeb6faf1ed1ca5785`
- 最新 tag: `v1.4.5`
- `v1.4.5` peeled commit: `dcb9bce8df62f52ac0ba58f209d946d8f4a90500`
- 本地与 HKUDS main merge-base: `0b180274e4367e35d848f6609ce7f483a886297c`
- 本地 ahead / behind HKUDS main: `1565 / 402`
- `v1.4.4..v1.4.5`: 111 files changed, 2967 insertions, 4208 deletions
- License: Apache-2.0

OpenMAIC：

- prior audited main: `3ccd5da6da0818608de78d86f1f7e428b9b8af54`
- current main: `612a1471e75b905b0649a56781ad0d6a009eee98`
- latest tag remains `v0.2.2` at `46a2497debd41815a2ae0a0d6acc7fe91db3b3a3`
- `3ccd5da..612a147`: 352 files changed, 52195 insertions, 785 deletions
- License: AGPL-3.0. The new `@maic/dsl`, `@maic/renderer`, and `@maic/importer` packages are also AGPL-3.0.

## 2. Clean-room Rules

本批次只允许吸收 workflow grammar、gate、test shape、security checklist 和 authority mapping。禁止：

1. 复制 HKUDS / OpenMAIC source code into this repo.
2. 复制 OpenMAIC schema、prompt、UI、renderer package、importer package 或 package structure。
3. 新增第二条 chat / classroom WebSocket；聊天与课堂问答仍只走 `/api/v1/ws`。
4. 新增第二套 learner memory、RAG、router、Partner identity、standalone learning runtime 或 classroom-specific knowledge authority。
5. 让 source ingestion、document extraction、renderer adapter 直接成为 lesson content truth。

## 3. 变化摘要与吸收判断

| 来源 | 变化域 | 路径证据 | 判断 |
| --- | --- | --- | --- |
| HKUDS v1.4.5 | Guided Learning on chat loop, loop-plugin framework, mastery policy/tools | `deeptutor/loop_plugins/*`, `deeptutor/learning/policy.py`, `deeptutor/tools/mastery_tool.py`, `deeptutor/api/routers/unified_ws.py` | 需要设计评审；只吸收 pure policy / gate idea，不吸收 runtime framework |
| HKUDS v1.4.5 | Partner export and save-to-notebook | `web/components/partners/*`, `web/lib/chat-export.ts` | 与本仓 single authority 无直接收益；仅可作为 existing session/message read-model serializer 参考 |
| HKUDS v1.4.5 | faster turn completion / title after answer saved | `deeptutor/services/session/turn_runtime.py`, `deeptutor/agents/chat/*` | 需先写 turn contract/eval；不可直接改 public stream done semantics |
| OpenMAIC 612a147 | answer-content eval | `eval/orchestration/answer-content-*` | 可低风险转译为 benchmark spine synthetic scenario pack；不得复制 prompt/scenario text |
| OpenMAIC 612a147 | iframe sandbox hardening | `components/scene-renderers/InteractiveIframeHost.tsx` | 可吸收为 ADR-005 / renderer gate 安全项；不复制 implementation |
| OpenMAIC 612a147 | document extractor provider foundation | `lib/document/extractors/*`, `lib/document/*` | 需要设计评审；只能落到 `SourceIngestionService` provider policy，不新增资料 authority |
| OpenMAIC 612a147 | `@maic/dsl`, `@maic/renderer`, `@maic/importer` packages | `packages/@maic/*` | AGPL clean-room only；不吸收源码/包结构/UI |
| OpenMAIC 612a147 | slide renderer/editor/import/PPTX pipeline | `components/slide-renderer/*`, `packages/@maic/importer/*` | 产品与 license 风险高；只保留 Scene Runtime Core / export gate 方向 |

## 4. Issue Drafts

### Issue 1: Review mastery-gate policy as Learning Brain / training_intent input

目标：评审 HKUDS v1.4.5 的 mastery gate 思路是否能映射到 DeepTutor 现有 `training_intent`、Learning Brain、`NextBestAction`，而不是新增 Guided Learning runtime 或 loop plugin。

唯一业务事实：学员下一步训练动作必须来自已有学习证据、稳定 claim、复测结果和处方 authority，而不是 chat loop 插件临时 stage cursor。

允许落点：

- `deeptutor/services/learner_state/training_intent.py`
- `deeptutor/services/learner_state/personalization_context.py`
- `deeptutor/services/learner_state/next_best_action.py`
- existing Learning Brain / learner-state tests

非目标：

- 不新增 `loop_plugins` runtime。
- 不新增 `mastery_mode` 作为 public request mode。
- 不新增第二套 learner progress / learning runtime。
- 不让 LLM qualitative pass 直接写 canonical learner truth。

最小 gate：

1. 先写设计评审，不写代码。
2. 若进入实现，必须用现有 learner-state tests 覆盖：L0 不升 stable claim、L1/L2 才能影响 NextBestAction、canonical write gate 不放宽。
3. `python scripts/check_contract_guard.py <changed files>` 必须通过。
4. 不新增 `/api/v1/ws` route、capability mode、memory table 或 RAG provider。

### Issue 2: Translate OpenMAIC answer-content eval into benchmark spine scenarios

目标：把 OpenMAIC “先回答用户本轮问题，不先讲课/跑题”的 eval 思路转译为 DeepTutor benchmark spine 的 synthetic scenario pack。

唯一业务事实：benchmark case identity、failure taxonomy、run artifact 只能由现有 benchmark spine 维护。

允许落点：

- `docs/plan/回归测试工程与质量门/2026-04-23-deeptutor-benchmark-single-spine-prd.md`
- existing benchmark fixtures / runner, if implementation is later approved

非目标：

- 不复制 OpenMAIC eval source、prompt、scenario wording、judge prompt。
- 不把真实用户对话放进 git。
- 不新增第二套 eval runner forest。

最小 gate：

1. 场景必须合成、匿名、可复现，禁止使用真实用户原文。
2. case 必须登记 `dataset_id / dataset_version / case_id / contract_domain / failure_taxonomy_scope`。
3. 先本地 synthetic smoke，再进入 release gate 候选。
4. 输出归入统一 run artifact，不另写平行 report authority。

### Issue 3: Add imported interactive content sandbox safety to ADR-005 and renderer gates

目标：把 OpenMAIC iframe sandbox hardening 转译为 DeepTutor OpenMAIC / 微信 renderer 的安全 gate。

唯一业务事实：`lesson_ir` 不能携带 raw HTML、inline script、iframe 或任意 JS simulation；若未来存在 imported interactive content，必须先被 Scene Runtime Core 降级/隔离，且 P0 小程序主表面不得依赖 iframe/WebView。

允许落点：

- [docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md](../../openmaic/ADR-005-mini-program-surface-renderer-contract.md)
- [docs/plan/微信小程序与结构化渲染/2026-04-16-wechat-structured-teaching-renderer-prd.md](../微信小程序与结构化渲染/2026-04-16-wechat-structured-teaching-renderer-prd.md)
- P2/P3 renderer gate checklist

非目标：

- 不实现 iframe host。
- 不允许小程序用 WebView/iframe 承载 P0 player。
- 不允许 imported HTML 直接进入 lesson truth。

最小 gate：

1. `lesson_ir` validator 拒绝 raw HTML、inline script、iframe、external CSS、browser-only handlers。
2. HTML export 如需 iframe/sandbox，必须独立于 P0 小程序主表面，并禁止 same-origin host state access。
3. 小程序 renderer gate 增加 “imported interactive content does not render executable HTML/JS” 检查。
4. 任一 interactive block 失败只能降级当前 block/scene，不得拖垮整条消息或课堂。

### Issue 4: Document extractor provider as SourceIngestionService design input only

目标：把 OpenMAIC document extractor provider foundation 转译为 DeepTutor source ingestion 的设计输入，而不是新增第二套 document ingestion authority。

唯一业务事实：进入 `lesson_ir` 的资料来源、解析结果、版权等级和 provenance 必须由 `SourceIngestionService` 写入 `source_manifest`；知识召回仍由 `RAGService` 提供 evidence。

允许落点：

- [docs/openmaic/ADR-004-source-ingestion-provenance.md](../../openmaic/ADR-004-source-ingestion-provenance.md)
- [docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md](../../openmaic/ADR-006-supabase-knowledge-base-reuse.md)
- existing document extraction utilities only if later approved

非目标：

- 不复制 OpenMAIC extractor provider code。
- 不新增 `exam_classroom_sources`、`classroom_documents` 或课堂专用 RAG。
- 不让 extractor 直接写 `lesson_ir`。

最小 gate：

1. 先写 contract/eval：provider selection must be deterministic and fail closed。
2. 解析输出必须带 page/paragraph/table/image provenance、confidence、copyright level 和 allowed use。
3. 低置信度、unknown、forbidden source 必须进入 `review_required`，不得进入 published/export。
4. 任何实现必须证明 `SourceIngestionService -> source_manifest -> LessonIRService` 的唯一写入链路。

## 5. docs/plan/INDEX.md 同步要求

本文件应挂在 “上游能力吸收” 主线下，作为 2026-06-16 之后 HKUDS v1.4.5 与 OpenMAIC `612a147` 的 clean-room intake。后续若 Issue 1-4 进入实施，应优先作为本文件的 child plan / checklist，不要再开第二条 upstream absorption 主线。

## 6. Stop Conditions

出现任一情况，停止吸收并回到设计评审：

1. 需要复制 OpenMAIC AGPL source/schema/prompt/UI。
2. 需要新增 chat/classroom WebSocket route。
3. 需要新增 learner memory / RAG / router / Partner identity / standalone learning runtime。
4. 需要绕过 `SourceIngestionService` 或 `RAGService`。
5. 需要把 imported HTML/JS/iframe 作为 P0 小程序播放器主路径。
