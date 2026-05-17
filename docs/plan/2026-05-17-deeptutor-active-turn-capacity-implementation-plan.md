# DeepTutor 50-120 Active Turn Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不新增第二套聊天入口的前提下，把现网从单容器单进程形态推进到可验证的 `50-120 active turn` Phase 1 能力。

**Architecture:** `/api/v1/ws` 继续作为唯一对外入口；内部逐步拆出 capacity load gate、Redis admission control、Redis-backed turn event stream、worker role、Postgres session/turn store。先用当前阿里云 ECS + Docker Compose 完成同机多角色验证，再决定是否迁托管 Redis/Postgres 或多 ECS。

**Tech Stack:** FastAPI WebSocket, `TurnRuntimeManager`, SQLiteSessionStore -> PostgresSessionStore, Valkey/Redis, Redis Streams, Docker Compose, pytest, public `/api/v1/ws` load gate, Aliyun `test2.yousenjiaoyu.com`.

---

## 0. 当前事实与目标边界

### 现网事实，2026-05-17

- 阿里云机器是 `8 vCPU / 30G RAM`，根盘 `99G` 已用约 `88%`。
- DeepTutor 仍是 `deeptutor` all-in-one 单容器；后端是单个 `uvicorn` 进程。
- Compose 中有 `deeptutor-valkey`，但当前运行环境未确认启用 `DEEPTUTOR_RATE_LIMIT_BACKEND=redis`。
- `/api/v1/ws` 单次 smoke 成功，约 `1.76s`。
- 轻压测结果：`5/10/20` 并发 light turn 都出现少量 terminal timeout；压测后 metrics 显示 `turns_started_total=37`、`turns_completed_total=32`、`turns_failed_total=5`。
- 日志出现 `Turn ... exceeded 75.0s runtime deadline`。

### 本计划不承诺的事

- 不把 `50-120 active turn` 等同于 `50-120` 同时在线用户。
- 不把同机多角色说成机器级高可用。
- 不通过新增 `/api/v1/mobile/tutorbot/ws/...` 或其他聊天 WebSocket 路由解决容量。
- 不直接用多开 `uvicorn --workers` 硬扩，因为当前 live subscriber 与 runtime execution 仍有进程内 authority。

### One Business Fact

系统真正要维护的一等事实是：**每个 accepted turn 必须有唯一生命周期状态、唯一执行 owner、可恢复事件流、最终 terminal event，并且不能让 `reasoning` 抢占 `fast` 主路径。**

### One Authority

- `turn admission` authority: Redis/Valkey admission counter + queue metadata。
- `turn execution owner` authority: worker lease。
- `turn/session persistence` authority: Postgres store。
- `turn event delivery` authority: Redis event stream + persisted event index。
- `/api/v1/ws` transport authority: gateway 只负责 start/subscribe/resume/cancel，不直接承担长任务执行。

---

## 1. 交付分层

### Phase 0: 先修现网下界，目标 20 light turn 0 失败

Phase 0 不改变主架构，只补齐容量测试、terminal timeout 根因证据、Redis rate limit backend 启用检查和磁盘红线。

Exit criteria:

- `20` 并发 light turn 连续 3 轮 `0` failed。
- `turns_in_flight` 压测后回到 `0`。
- `turns_failed_total` 不增长。
- 每个客户端都收到 `done` 或明确 `error` terminal event。

### Phase 1A: 单容器内全局准入，目标 40-50 accepted active turn 可控

先不拆 worker，只把 admission 从“请求进入后超时”改成“入口先判断 accept/enqueue/reject/degrade”。

Exit criteria:

- `fast_active_limit=40`、`reasoning_active_limit=8` 可配置。
- 超额请求返回可观测 queue/reject 事件，不进入无边界执行。
- metrics 暴露 active、queued、rejected、degraded。

### Phase 1B: 同机 gateway/worker 分离，目标 50-80 active turn

拆出 `gateway`、`fast-worker`、`reasoning-worker` 三种角色；gateway 不执行长任务，worker 通过 Redis queue 消费 turn。

Exit criteria:

- `gateway x2`、`fast-worker x4`、`reasoning-worker x1-2` 在同机 Compose 可运行。
- kill 单个 worker 后，turn lease 过期并被恢复或 fail-closed。
- `50` mixed active turn 下 `fast p95 < 8s`，failure rate `< 1%`。

### Phase 1C: Postgres + Redis event stream，目标 80-120 active turn

把 SQLite/session/event replay 从单进程瓶颈里移出，支撑 gateway 多副本与 worker 多副本。

Exit criteria:

- `PostgresSessionStore` 成为 production store。
- `RedisTurnEventStream` 支持 `after_seq` replay/resume。
- `80` active turn 连续 3 轮通过；`120` active turn 有明确 queue 和降级，不雪崩。

---

## 2. 文件结构

### 新增文件

- `scripts/run_ws_capacity_probe.py`: 可复用公网/本地 `/api/v1/ws` 阶梯压测脚本，输出 JSON summary。
- `tests/services/observability/test_ws_capacity_probe.py`: 验证压测统计、terminal event 判定、失败分类。
- `deeptutor/services/capacity/admission.py`: admission control 数据模型与策略。
- `deeptutor/services/capacity/redis_admission.py`: Redis/Valkey 实现。
- `tests/services/capacity/test_admission.py`: admission 单测。
- `deeptutor/services/session/event_stream.py`: turn event stream interface。
- `deeptutor/services/session/redis_event_stream.py`: Redis Streams 实现。
- `tests/services/session/test_redis_event_stream.py`: event stream 单测。
- `deeptutor/services/session/postgres_store.py`: Postgres-backed session/turn store。
- `tests/services/session/test_postgres_store_contract.py`: store contract tests。
- `deeptutor/services/session/worker.py`: worker role entrypoint。
- `scripts/run_turn_worker.py`: worker CLI wrapper。
- `deployment/aliyun/docker-compose.capacity.yml`: Phase 1 gateway/worker/redis/postgres compose overlay。

### 修改文件

- `deeptutor/api/routers/unified_ws.py`: start_turn 改为通过 admission/queue 或保持 feature-flag old path；subscribe 改读 event stream。
- `deeptutor/services/session/turn_runtime.py`: 分离 create_turn、execute_turn、publish_event；保留 old path feature flag。
- `deeptutor/services/session/__init__.py`: wire store/event stream/worker dependencies。
- `deeptutor/api/runtime_metrics.py`: 增加 capacity metrics。
- `docker-compose.yml`: 保持现有 all-in-one 默认；新增 env 和 overlay 兼容。
- `docs/zh/guide/aliyun-deploy.md`: 增加 capacity overlay 部署与回滚 runbook。

---

## 3. 实施任务

### Task 1: Capacity Probe Gate

**Files:**
- Create: `scripts/run_ws_capacity_probe.py`
- Create: `tests/services/observability/test_ws_capacity_probe.py`

- [ ] **Step 1: 写失败测试**

```python
def test_summarize_capacity_results_counts_terminal_timeout():
    from scripts.run_ws_capacity_probe import summarize_results

    rows = [
        {"ok": True, "terminal": "done", "latency_ms": 1000.0, "messages": 7},
        {"ok": False, "terminal": "exception", "latency_ms": 45000.0, "messages": 3, "error": "TimeoutError"},
    ]

    summary = summarize_results(concurrency=2, rows=rows, wall_ms=45010.0)

    assert summary["concurrency"] == 2
    assert summary["ok"] == 1
    assert summary["failed"] == 1
    assert summary["failure_categories"] == {"terminal_timeout": 1}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/services/observability/test_ws_capacity_probe.py -q`

Expected: `ModuleNotFoundError` 或 `ImportError`。

- [ ] **Step 3: 实现最小脚本**

`scripts/run_ws_capacity_probe.py` 必须支持：

```bash
python3 scripts/run_ws_capacity_probe.py \
  --api-base-url https://test2.yousenjiaoyu.com \
  --levels 5,10,20 \
  --message "请只回复 ok" \
  --timeout-seconds 45 \
  --json-out artifacts/ws_capacity_probe.json
```

核心行为：

- 对每个并发层级并行建立 WebSocket。
- 每个连接发送 `start_turn`。
- 收到 `done` 算成功，收到 `error` 算 terminal failure。
- 连接超时但已收到部分事件时归类 `terminal_timeout`。
- 输出 `p50_ms`、`p95_ms`、`max_ms`、`failed`、`failure_categories`。

- [ ] **Step 4: 跑本地单测**

Run: `pytest tests/services/observability/test_ws_capacity_probe.py -q`

Expected: PASS。

- [ ] **Step 5: 跑公网轻 gate**

Run:

```bash
python3 scripts/run_ws_capacity_probe.py --api-base-url https://test2.yousenjiaoyu.com --levels 5,10,20 --json-out artifacts/ws_capacity_probe_$(date +%Y%m%dT%H%M%S).json
```

Expected for Phase 0 closure: `5/10/20` 全部 `failed=0`。

### Task 2: Terminal Timeout Root Cause

**Files:**
- Modify: `deeptutor/services/session/turn_runtime.py`
- Modify: `deeptutor/api/runtime_metrics.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 1: 增加 terminal guarantee 测试**

新增测试：模拟 capability 抛错、LLM 超时、client disconnect 三类情况，断言 turn 最终有 `done` 或 `error` terminal event，且 `turns_in_flight` 回到 `0`。

- [ ] **Step 2: 明确失败分类**

在 `turn_runtime.py` 中把 75s deadline cancellation 的输出事件统一成 public `error` terminal event，metadata 至少包含：

```python
{
    "status": "failed",
    "error_category": "turn_timeout",
    "terminal_recovered": True,
}
```

- [ ] **Step 3: 修复 subscriber 断开后的 terminal publish**

即使客户端先断开，runtime 仍必须把 terminal event 写入 store/event log；不能只向 live queue 推送。

- [ ] **Step 4: 验证**

Run:

```bash
pytest tests/api/test_unified_ws_turn_runtime.py -q
python3 scripts/run_ws_capacity_probe.py --api-base-url https://test2.yousenjiaoyu.com --levels 5,10,20
```

Expected: tests PASS；公网 probe 失败率降到 0 或有明确 terminal error，不再出现 silent terminal timeout。

### Task 3: Redis Admission Control

**Files:**
- Create: `deeptutor/services/capacity/admission.py`
- Create: `deeptutor/services/capacity/redis_admission.py`
- Create: `tests/services/capacity/test_admission.py`
- Modify: `deeptutor/api/routers/unified_ws.py`
- Modify: `deeptutor/api/runtime_metrics.py`

- [ ] **Step 1: 写 admission 策略测试**

测试用例必须覆盖：

- 同一用户 `per_user_active_limit=1`。
- `fast_active_limit` 满后进入 queue。
- `reasoning_active_limit` 满后不影响 `fast`。
- queue 满后返回 reject。

- [ ] **Step 2: 定义返回值**

`AdmissionDecision` 只允许四种：

```python
Literal["accept", "enqueue", "reject", "degrade"]
```

每个 decision 必须带 `reason`、`mode`、`active_count`、`queued_count`。

- [ ] **Step 3: 接入 `/api/v1/ws`**

`unified_ws.py` 的 start_turn path：

1. normalize mode。
2. call admission。
3. `accept`: 继续旧执行 path。
4. `enqueue`: 返回 queue event。
5. `reject`: 返回 public error event，不能创建 dangling running turn。
6. `degrade`: mode 降为 `fast` 并记录 metadata。

- [ ] **Step 4: 验证**

Run:

```bash
pytest tests/services/capacity/test_admission.py tests/api/test_unified_ws_turn_runtime.py -q
```

Expected: PASS。

### Task 4: Event Stream Interface

**Files:**
- Create: `deeptutor/services/session/event_stream.py`
- Create: `deeptutor/services/session/redis_event_stream.py`
- Create: `tests/services/session/test_redis_event_stream.py`
- Modify: `deeptutor/services/session/turn_runtime.py`

- [ ] **Step 1: 写 contract test**

覆盖：

- append event returns monotonically increasing `seq`。
- read after `seq` returns catchup。
- subscribe sees new event。
- retention trimming 不破坏最新 terminal event。

- [ ] **Step 2: 实现 interface**

接口最小形状：

```python
class TurnEventStream(Protocol):
    async def append(self, turn_id: str, event: dict[str, object]) -> dict[str, object]: ...
    async def read_after(self, turn_id: str, after_seq: int) -> list[dict[str, object]]: ...
    async def close(self) -> None: ...
```

- [ ] **Step 3: Redis Streams 实现**

使用 key:

```text
deeptutor:turn-events:{turn_id}
```

metadata 中保留 `seq`，不要把 Redis stream id 暴露为 public seq authority。

- [ ] **Step 4: 验证**

Run:

```bash
pytest tests/services/session/test_redis_event_stream.py tests/api/test_unified_ws_turn_runtime.py -q
```

Expected: PASS。

### Task 5: Worker Role Split

**Files:**
- Create: `deeptutor/services/session/worker.py`
- Create: `scripts/run_turn_worker.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Modify: `docker-compose.yml`
- Create: `deployment/aliyun/docker-compose.capacity.yml`

- [ ] **Step 1: 定义 worker job payload**

Job payload 只包含已持久化 turn 的引用：

```json
{
  "turn_id": "turn_x",
  "session_id": "session_x",
  "mode": "fast",
  "lease_id": "worker-uuid",
  "attempt": 1
}
```

不要把完整 prompt、答案、learner profile 作为 queue authority。

- [ ] **Step 2: 拆 `execute_turn`**

`TurnRuntimeManager.start_turn()` 只负责 create/admit/enqueue；`execute_turn(turn_id)` 负责真正执行。

- [ ] **Step 3: worker loop**

worker loop:

1. claim job。
2. renew lease。
3. call `execute_turn`。
4. publish terminal。
5. release active slot。

- [ ] **Step 4: Compose overlay**

`deployment/aliyun/docker-compose.capacity.yml` 定义：

```yaml
services:
  gateway:
    command: python -m uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001
  fast-worker:
    command: python scripts/run_turn_worker.py --pool fast --concurrency 10
  reasoning-worker:
    command: python scripts/run_turn_worker.py --pool reasoning --concurrency 4
```

第一阶段同机目标：

- `gateway x2`
- `fast-worker x4`
- `reasoning-worker x1`

- [ ] **Step 5: 验证**

Run:

```bash
pytest tests/api/test_unified_ws_turn_runtime.py tests/services/session/test_redis_event_stream.py -q
docker compose -f docker-compose.yml -f deployment/aliyun/docker-compose.capacity.yml config
```

Expected: tests PASS；compose config valid。

### Task 6: Postgres Store Migration

**Files:**
- Create: `deeptutor/services/session/postgres_store.py`
- Create: `tests/services/session/test_postgres_store_contract.py`
- Modify: `deeptutor/services/session/__init__.py`
- Add migration under: `supabase/migrations/` or deployment-owned Postgres migration path, depending final DB authority.

- [ ] **Step 1: Store contract tests**

Contract must cover:

- create session。
- create turn。
- append turn event。
- get events after seq。
- set/get active object。
- list sessions by owner。

- [ ] **Step 2: Additive schema**

Tables:

```sql
sessions(id text primary key, owner_id text, created_at timestamptz, metadata jsonb);
turns(id text primary key, session_id text references sessions(id), status text, created_at timestamptz, updated_at timestamptz, payload jsonb);
turn_events(turn_id text references turns(id), seq bigint, event jsonb, created_at timestamptz, primary key(turn_id, seq));
session_state(session_id text primary key references sessions(id), active_object jsonb, suspended_object_stack jsonb, updated_at timestamptz);
```

- [ ] **Step 3: Dual-write flag**

Introduce env:

```text
DEEPTUTOR_SESSION_STORE=sqlite|postgres
DEEPTUTOR_SESSION_DUAL_WRITE=false|true
```

Production cutover order:

1. dual-write on。
2. compare latest turn/session rows。
3. switch read to Postgres。
4. keep SQLite fallback for rollback window。

- [ ] **Step 4: 验证**

Run:

```bash
pytest tests/services/session/test_postgres_store_contract.py tests/api/test_unified_ws_turn_runtime.py -q
```

Expected: PASS。

### Task 7: Aliyun Capacity Acceptance

**Files:**
- Modify: `docs/zh/guide/aliyun-deploy.md`
- Modify: `scripts/verify_aliyun_observability.sh`
- Create: `scripts/run_aliyun_capacity_gate.sh`

- [ ] **Step 1: 容量 gate 脚本**

`scripts/run_aliyun_capacity_gate.sh` 固定跑：

```bash
python3 scripts/run_ws_capacity_probe.py --api-base-url https://test2.yousenjiaoyu.com --levels 20,50,80 --json-out artifacts/aliyun_capacity_gate.json
```

`120` 只在 `CAPACITY_GATE_LEVEL=full` 时跑，避免日常误伤生产。

- [ ] **Step 2: 观测采集**

容量 gate 前后必须抓：

- `/readyz`
- `/metrics`
- `docker stats --no-stream`
- `docker logs --since 10m deeptutor`
- `df -h /`

- [ ] **Step 3: 验收标准**

Phase 1B:

- `50` active turn: `failed_rate < 1%`，`fast p95 < 8s`，`turns_in_flight=0` after drain。

Phase 1C:

- `80` active turn: same criteria。
- `120` active turn: allow queue/degrade，but no silent timeout, no leaked in-flight。

---

## 4. 当前最优交付顺序

1. 先做 Task 1 + Task 2：把 `20` 并发 silent terminal timeout 修到 0。
2. 再做 Task 3：先让系统会拒绝/排队，而不是无边界吃流量。
3. 再做 Task 4：外置 event stream，为 gateway/worker 分离铺路。
4. 再做 Task 5：同机拆 role，目标 `50`。
5. 再做 Task 6：Postgres store，目标 `80-120`。
6. 最后做 Task 7：阿里云容量 gate 固化，形成可重复证据。

---

## 5. 不确定性与替代方案

| 不确定性 | 风险 | 验证方式 | 替代方案 |
|---|---|---|---|
| LLM provider 实际并发限额 | `fast` 请求被上游排队拖慢 | 分 provider 记录 latency/error/rate limit | 降低 accepted active，增加 queue/degrade |
| Supabase RAG 高峰表现 | RAG turn p95 远高于 light turn | 混载 `fast no-rag`、`fast rag`、`reasoning rag` | 高峰默认关闭 rerank 或降低 `top_k` |
| 单机磁盘 88% | ClickHouse/MinIO/docker build cache 继续增长导致服务风险 | 每次 gate 前抓 `df -h /` 和 `docker system df` | 清理 Docker build cache 或迁移 Langfuse/ClickHouse |
| 同机 Redis/Postgres 可用性 | 单机仍非 HA | kill/restart 容器演练 | Phase 1.5 使用托管 Redis/Postgres |
| 多 worker 对 session state 的一致性 | follow-up/active object 漂移 | store contract + long-dialog replay | Postgres 切读前保留 single executor |

---

## 6. 最终收线口径

只有同时满足以下条件，才能说“已具备 50-120 active turn Phase 1 能力”：

- `20/50/80` 容量 gate 有 JSON artifact。
- `120` gate 至少证明 queue/degrade 不雪崩。
- `turns_in_flight` 不泄漏。
- terminal event 100% 收敛。
- `fast` 与 `reasoning` 指标分开。
- worker kill/restart 有恢复证据。
- gateway restart 后 `resume_from` 仍可用。
- 阿里云公网入口 `https://test2.yousenjiaoyu.com/api/v1/ws` 验证通过。
- 明确标注：同机 Phase 1 不是机器级高可用。

