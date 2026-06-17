# 鲁班评分引擎 异步执行与 UX Runtime 方案（Stream F · planning + 接口草案）

> Status: `Proposed v0`（2026-06-04）。**测试环境 / 设计与接口草案 only —— 本文档不实现大系统、不新增队列系统、不新增数据库表、不改 `CaseGradingSkillKernel`(`case_kernel.py`)、不让 RAG 进评分 authority、不接 production runtime、不把未复核 AI-Draft 写入 Learning Brain。**
> 前置证据：`docs/plan/2026-06-04-luban-grading-engine-ai-draft-test-ab-plan.md`（A.1-A.5 架构边界）、`deeptutor/services/construction_grading/best_quality_ai_draft.py`、`deeptutor/api/utils/task_id_manager.py`、`deeptutor/api/utils/task_log_stream.py`、`deeptutor/api/routers/knowledge.py`（已落地的 BackgroundTasks + SSE 异步 job 范式）。

## 0. First Principles 与本方案的边界

一等事实 = **一次学生作答经批改并经老师确认后产生的可信 learning evidence**。批改本身（尤其 Best-Quality 4 模型裁决）是**昂贵的中间计算**，不是一等事实，因此它**不应阻塞**学生提交动作的请求线程，也**不应**在未复核前进入 Learning Brain。

本方案只回答一个工程问题：**「学生点提交 → 看到批改结果」这条交互如何异步化，使重计算不阻塞热路径、又能 fail-closed。** 它**不**回答评分逻辑（在 service/skill 层，已落地）、**不**接生产 runtime（红线）。

Less is more 的硬约束在本文档体现为：**复用项目已有的 `BackgroundTasks + TaskIDManager + KnowledgeTaskStreamManager(SSE)` 范式，不引入 celery/arq/dramatiq/rq 等任何新队列依赖。**（已核验依赖见 §4。）

---

## 1. 当前 Best-Quality 延迟评估（cached-replay vs live 四模型）

必须区分两种延迟，它们差 3-4 个数量级，决定了热路径能否同步执行：

### 1.1 Cached-replay（本轮测试环境实际跑的）

`best_quality_for_golden(question, student_id)` 在缓存裁决模式下，读取 `artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/unified_predictions_485_span_guarded.json`（1.34 MB，含 4 个 `prediction_sets`），对单题做 per-point 裁决（`adjudicate` + `build_ai_draft` guards）。

实测（本机，20 题 golden fixture 全跑通，0 fail-closed）：

| 指标 | 值 |
|---|---|
| 缓存预测文件加载（一次性 / 可 lru_cache） | ~6.7 ms |
| 单题裁决（cached-replay）min / median / max / mean | 6.9 / 7.5 / 16.1 / 8.3 ms |
| 可裁决题数 / unavailable | 20 / 0 |

**结论**：cached-replay 近乎瞬时（亚 20ms），**理论上可同步返回**。但它不是产品形态——cached-replay 只对已离线裁决过的 golden 样本可用，**对真实新作答无缓存**，会 `BestQualityUnavailable` fail-closed。

### 1.2 Live 四模型（真实产品形态的重路径）

真实新作答下，Best-Quality 需要对四个异构裁判（GPT5.5 / Opus4.8 / DeepSeek-V4 / Qwen3.7）各发一次 LLM 调用，再做 per-point 裁决。延迟估算（基于 §3 引用的同类 LLM 调用经验，非本轮实测，**标注为估算**）：

| 阶段 | 估算延迟 |
|---|---|
| 单模型一次结构化批改（含 N 个采分点） | 3–15 s（取决于题长/采分点数/provider 排队） |
| 四模型 **并行** wall-clock（取最慢者 + 裁决） | ~8–20 s（p50），尾部可达 30–60 s |
| 四模型 **串行**（不推荐） | 4× 单模型 ≈ 15–60 s |

**结论**：live Best-Quality 的 wall-clock 在**秒到分钟**量级，**绝不能放进 `/api/v1/ws` 同步请求线程或 HTTP 请求-响应周期内**。这正是需要异步执行 + 轮询/流式回传的根因。

### 1.3 两条线对照

| | Cached-replay | Live 四模型 |
|---|---|---|
| 延迟量级 | ~7.5 ms / 题 | 8–60 s / 题（估算） |
| 适用 | 离线回放、测试 harness、回归 | 真实新作答的高质量复核 |
| 失败模式 | 无缓存 → fail-closed | provider 超时/限流 → timeout fallback |
| 是否需异步 | 否（但仍走同一接口便于切换） | **是（强制）** |

---

## 2. 异步设计（最小接口草案，不实现）

### 2.1 复用而非新建：执行模型

直接复用 `knowledge.py` 已验证的范式（无新组件）：

- **提交**：FastAPI `BackgroundTasks.add_task(...)` 把重计算移出请求线程；同步阻塞调用用 `loop.run_in_executor(...)` 包住，避免阻塞事件循环。
- **状态登记**：`TaskIDManager.generate_task_id(task_type, task_key)` 生成 `grading_{ts}_{uuid}`，`update_task_status(...)` 记录 `running → completed/error/cancelled`（进程内单例，含 `cleanup_old_tasks`）。
- **流式 / 轮询回传**：`KnowledgeTaskStreamManager`（SSE，`event: log|complete|failed`，500 条 ring buffer + backlog replay）。已支持订阅后补发历史事件 + 完成即收尾，天然适配 partial result。

> ⚠️ 这些都是**进程内**状态（`TaskIDManager`/`KnowledgeTaskStreamManager` 是单例字典）。对测试环境 / 单进程 harness 足够。**多 worker / 跨进程持久化不在 v0 范围**（见 §4 缺口）；若未来需要，复用已在 `pyproject.toml` 的 `redis`，而非引入队列框架。

### 2.2 流式入口唯一性（硬约束对齐）

生产聊天流式入口唯一 = `/api/v1/ws`（AGENTS 硬约束）。**本方案不新增聊天 WebSocket**。批改 job 的状态/流式回传走**独立的 SSE 任务流**（与 `knowledge.py` 的 `/tasks/{task_id}/stream` 同构），它**不是**聊天入口，是任务进度通道，不违背唯一性。挂载点延续 Stream A/B 既定结论：**harness 层（QA-gated）**，不进 capability/TutorBot 生产 loop。

### 2.3 接口草案（pydantic 模型 + route 签名，仅文档，不落地）

```python
# ⚠️ DRAFT ONLY — 不在本 stream 落地为生产代码。挂载于 QA-gated harness 层。
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class GradingEngine(str, Enum):
    deepseek_fast = "deepseek_fast"          # 实时低成本（未来生产成本线，本轮不接）
    best_quality_4model = "best_quality_4model"  # 高质量复核（能力天花板，candidate_only）


class GradingJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    partial = "partial"        # 已有部分采分点裁决，整体未完成
    completed = "completed"
    failed = "failed"          # fail-closed：含 best_quality_unavailable / provider_timeout
    cancelled = "cancelled"


class SubmitGradingJobRequest(BaseModel):
    case_id: str
    student_id: str
    answer_text: str
    engine: GradingEngine = GradingEngine.best_quality_4model
    # 测试环境强制 candidate_only；不写 Learning Brain，不接 runtime。
    candidate_only: bool = True


class SubmitGradingJobResponse(BaseModel):
    task_id: str
    status: GradingJobStatus = GradingJobStatus.queued
    engine: GradingEngine
    stream_url: str                # 形如 /.../grading-jobs/{task_id}/stream（SSE）
    poll_url: str                  # 形如 /.../grading-jobs/{task_id}


class PointPartial(BaseModel):
    point_id: str
    hit: str | None = None         # 已裁决点回填；未完成为 None
    high_risk: bool = False        # genuine ambiguity → 人工复核（不自动 mastery）


class GradingJobState(BaseModel):
    task_id: str
    status: GradingJobStatus
    engine: GradingEngine
    points_total: int
    points_done: int
    partial_points: list[PointPartial] = Field(default_factory=list)
    # 仅 status==completed 时填充；为 ai_draft_shadow 的现有 draft 结构（含 guards）。
    draft: dict[str, Any] | None = None
    # fail-closed 原因：best_quality_unavailable / provider_timeout / jurors_lt_3 ...
    fail_reason: str | None = None
    # 红线复述：未复核 draft 永不自动写入 Learning Brain；teacher-final 才是写入 authority。
    not_production_grade: bool = True
    requires_teacher_review: bool = True


# ---- route 签名草案（不实现）----
# @router.post("/learning-brain/grading-jobs", ...QA-gated deps...)
# async def submit_grading_job(
#     req: SubmitGradingJobRequest,
#     background_tasks: BackgroundTasks,
# ) -> SubmitGradingJobResponse: ...
#     # 1. task_id = TaskIDManager...generate_task_id("grading", f"{case_id}:{student_id}")
#     # 2. background_tasks.add_task(_run_grading_job, task_id, req)
#     # 3. 返回 stream_url / poll_url（即时返回，不阻塞）

# @router.get("/learning-brain/grading-jobs/{task_id}")
# async def poll_grading_job(task_id: str) -> GradingJobState: ...
#     # 读 TaskIDManager.get_task_metadata(task_id) + 进度，组装 GradingJobState

# @router.get("/learning-brain/grading-jobs/{task_id}/stream", ...QA-gated deps...)
# async def stream_grading_job(task_id: str) -> StreamingResponse: ...
#     # return StreamingResponse(get_task_stream_manager().stream(task_id),
#     #                          media_type="text/event-stream")  # 复用既有 SSE
```

### 2.4 Partial result / timeout / fail-closed 行为

- **Partial**：四模型并行时，每个采分点一旦满足 ≥3 裁判（现有 `adjudicate` 的硬下限）即可 emit 一条 `event: log` 的 point partial，`points_done` 递增。整体未完成前 `status=partial`，前端可逐点点亮。**裁决逻辑不改**——partial 只是把现有 per-point 结果增量回传。
- **Timeout fallback**：单模型超过软上限（建议 20s，可配置常量，不硬编码）即视为该裁判缺席；若存活裁判 ≥3 仍可裁决（degraded，标 `model_set` 缩减）；若 <3 → **fail-closed**：`status=failed`，`fail_reason="jurors_lt_3"`，**不**降级成单 DeepSeek 冒充 Best-Quality（红线，`best_quality_ai_draft.py` 既有约束）。
- **Fail-closed 统一出口**：`BestQualityUnavailable` / 全模型超时 / 缓存缺失 → `status=failed` + `fail_reason`，**绝不**产出占位分数、**绝不**写 Learning Brain。与 `best_quality_ai_draft.py:41` 的 fail-closed 语义一致。
- **未复核不入 Brain**：job `completed` 仅意味着 draft 就绪；写入 Learning Brain 依旧只经 `teacher_review_writeback.py`（teacher-final），与 Stream B/D 一致，本异步层不碰写回 authority。

---

## 3. DeepSeek Fast vs Best-Quality 使用场景划分

| 维度 | DeepSeek Fast | Best-Quality 4-model |
|---|---|---|
| 定位 | 未来**生产成本线**（实时低成本） | 当前**能力天花板**（高质量复核） |
| 延迟预算 | 同步可接受（亚秒~数秒，单模型） | 异步强制（8–60s，秒~分钟） |
| 执行方式 | 可同步返回 / 短异步 | **必走 §2 异步 job** |
| 触发场景 | 学生即时自测、海量低风险题、首轮快速反馈 | 老师工作台复核、高价值/高争议题、抽检校准、`high_risk` 二次裁决 |
| 写入 authority | 同样**不自动**入 Brain，仍需 teacher-final | 同样需 teacher-final；`high_risk/unsupported` 永不自动 mastery |
| 成本 | 低（单模型） | 高（4× LLM + 裁决） |
| 本轮状态 | **不接 production runtime（红线）**，仅作场景划分占位 | 测试环境 cached-replay 已落地；live 仅设计 |

**路由原则（thin wrapper）**：`engine` 字段由调用方/工作台选择，路由层只薄转发到对应执行器，**不内置自动 escalation 逻辑**（避免造第二套决策权威）。Fast→Best 的升级（如 Fast 标 `high_risk` 后转人工 + Best 复核）由老师工作台显式触发，属未来 stream，不在 v0。

---

## 4. 最小实现路径（复用项 vs 缺口）

### 4.1 可直接复用（已核验存在，零新增依赖）

| 能力 | 复用对象 | 证据 |
|---|---|---|
| 后台执行（移出请求线程） | FastAPI `BackgroundTasks` + `run_in_executor` | `deeptutor/api/routers/knowledge.py:752,851` |
| 任务 ID / 状态机 | `TaskIDManager`（running/completed/error/cancelled + cleanup） | `deeptutor/api/utils/task_id_manager.py` |
| 流式 / partial 回传（SSE） | `KnowledgeTaskStreamManager`（buffer+backlog+complete/failed） | `deeptutor/api/utils/task_log_stream.py` |
| 裁决与 guards（fat skill） | `best_quality_draft` / `adjudicate` / `build_ai_draft` | `best_quality_ai_draft.py`、`ai_draft_shadow.py` |
| draft → 写回（teacher-final） | `build_teacher_review_writeback` / `write_grading_error_events` | `teacher_review_writeback.py`、`writeback.py` |
| 周期/定时执行（如需批量复核） | `CronService`（已有，asyncio timer） | `deeptutor/tutorbot/cron/service.py:63` |
| 跨进程持久化基建（如需） | `redis>=5.0.0`（已在依赖） | `pyproject.toml:50,63` |

**未发现任何 celery / arq / dramatiq / rq / apscheduler 依赖** —— 因此「不新增队列系统」约束**天然满足**：复用上述进程内范式即可，无需引入队列框架。

### 4.2 缺口（实现时需补，但不在本 planning stream 落地）

1. **新作答的 live 四模型 provider 调用**：当前 `best_quality_ai_draft.py` 只读缓存预测；live 路径需要四模型并行调用封装（依赖 provider key，与本轮「不依赖 live key」约束冲突，故仅设计）。
2. **进程内状态的多 worker 局限**：`TaskIDManager`/Stream manager 是单例字典，多 uvicorn worker 下任务对其他 worker 不可见。v0 测试环境单进程可接受；生产化时用已有 `redis` 做 task 状态/事件背板（复用，不引队列）。
3. **partial 增量回传到 `GradingJobState.partial_points` 的组装**：现有 SSE 只发 log/complete/failed，需薄封装把 per-point 裁决 emit 为结构化 partial 事件（在 service 层产出，route 层只转发）。

### 4.3 推荐落地顺序（未来 stream，非本轮）

1. harness 层加 `POST /learning-brain/grading-jobs`（QA-gated），cached-replay 引擎走同步快路径 + 同一 job 接口（验证接口形态，无 live key 依赖）。
2. 接 `TaskIDManager` + SSE，跑通 submit → poll/stream → completed 的端到端（仍 cached-replay）。
3. 补 live 四模型并行执行器（需 key），灰度只走老师工作台高价值题。
4. （可选）多 worker 化时用 redis 背板替换进程内单例。

---

## 5. 验收对照（Stream F）

- **不新增队列系统**：满足。已核验 `pyproject.toml` 无 celery/arq/dramatiq/rq/apscheduler；方案纯复用 `BackgroundTasks + TaskIDManager + KnowledgeTaskStreamManager`（§4.1）。唯一可复用持久化基建 `redis` 已在依赖，仅作多 worker 化缺口的占位（§4.2），v0 不启用。
- **方案清晰**：cached-replay vs live 延迟分层（§1）、submit/poll/partial/timeout/fail-closed 接口草案（§2）、Fast vs Best 场景划分（§3）齐备。
- **最小实现路径明确**：复用项 7 项 + 缺口 3 项 + 落地顺序 4 步（§4）。
- **未触任何停止条件**：无新表、未改 `case_kernel.py`、RAG 不进评分、不写生产库、未复核 draft 不入 Brain、不重跑 485、不接 production runtime。
- **未写生产代码**：接口草案仅存于本文档代码块。

> 待挂 `docs/plan/INDEX.md`（由总控统一更新，本 stream 不编辑 INDEX）。
