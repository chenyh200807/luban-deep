# 实施计划：DeepTutor Observability M0/M1（第一批）

## 1. 本批目标

本批只交付当前条件下最稳健、最有复用价值的一批能力，不追求一次把 `ARR / AAE / OA / OM` 全量铺开。

范围收敛为：

1. `M0`
   - 统一 `release lineage`
   - 统一基础观测字段命名
   - 让 trace / metrics / system control surface 能围绕同一条版本事实回链
2. `M1`
   - 补齐服务端 OM 基线
   - 把当前真正承载业务的 `WebSocket + turn runtime` 拉进 runtime metrics
   - 补齐 turn trace enrich

明确不在本批直接交付：

1. ARR runner 总线化
2. AAE score 面
3. OA state store
4. Web / 小程序 / yousenwebview 的完整 surface ack 上报闭环

原因：

1. 当前仓库已经有 Langfuse、`/healthz`、`/readyz`、`/metrics/prometheus`，但缺少统一版本事实与 WS/turn 运行事实，这是最短木板
2. 如果先做 client ack 而服务端还没有统一 release lineage 和 turn runtime metrics，后续归因仍然会散
3. 本仓当前主工作树很脏，第一批必须选最容易独立验证、最不容易引入第二套 authority 的切口

## 2. 一等业务事实

本批维护的唯一业务事实是：

1. 任一线上 turn，都必须能稳定回链到同一条 `release lineage`
2. 任一线上 turn / ws 故障，都必须能在统一 OM 面板里看到最小可诊断运行事实

对应 authority：

1. `release lineage authority`
   - 服务端 runtime 统一生成
   - trace、metrics、system control surface 只能消费，不得各自重算另一套业务 ID
2. `turn/ws runtime metrics authority`
   - 服务端 runtime 统一记录
   - 由统一 API metrics 出口暴露

## 3. 交付物

### 3.1 代码交付

1. 新增 release lineage 模块
2. turn runtime trace metadata 增加：
   - `release_id`
   - `git_sha`
   - `service_version`
   - `deployment_environment`
   - `prompt_version`
   - `ff_snapshot_hash`
3. unified turn contract trace_fields 同步升级
4. system / metrics control surface 暴露 release lineage
5. runtime metrics 增加 WebSocket / turn 维度：
   - ws 当前连接数
   - ws 累计打开/关闭数
   - turn started / completed / failed / cancelled
   - turn 平均耗时
   - turn in-flight
6. Prometheus 文本出口同步增加上述指标

### 3.2 文档交付

1. 本实施计划
2. 如实现中需要，补最小 operator-facing 字段说明

### 3.3 测试交付

至少覆盖：

1. release lineage 解析与稳定性
2. turn contract trace_fields 更新
3. `/metrics` 与 `/metrics/prometheus` 输出新增字段
4. turn runtime 在成功 / 失败 / 取消场景下的指标更新

## 4. 文件级切口

预计会改这些文件：

1. `deeptutor/services/observability/release_lineage.py`
2. `deeptutor/api/runtime_metrics.py`
3. `deeptutor/api/main.py`
4. `deeptutor/contracts/unified_turn.py`
5. `deeptutor/services/session/turn_runtime.py`
6. `deeptutor/api/routers/unified_ws.py`
7. `tests/api/test_main_entrypoints.py`
8. `tests/api/test_system_router.py`
9. 视实现需要新增 `tests/services/observability/test_release_lineage.py`
10. 视实现需要新增或补充 `tests/api/test_unified_ws_turn_runtime.py`

## 5. 实施步骤

### Step 1：建立 release lineage authority

新增统一模块，负责：

1. 读取 `service_version`
2. 解析 `git_sha`
3. 解析 `deployment_environment`
4. 读取 `prompt_version`
5. 基于受控 flag 集生成 `ff_snapshot_hash`
6. 生成稳定 `release_id`

设计要求：

1. 允许显式 env override
2. 没有 Git 信息时也要稳定退化
3. 不得在 trace、metrics、router 各处重复拼接 release_id

### Step 2：补齐 trace enrich

在 `turn_runtime` 的统一 trace metadata 写入点注入 release lineage。

设计要求：

1. 只改统一 authority 写入点
2. 不在 capability / tool 层散点补字段
3. contract trace_fields 与实际 metadata 一致

### Step 3：补齐服务端 OM 基线

在 runtime metrics 中增加：

1. ws 连接生命周期统计
2. turn 生命周期统计
3. turn 平均耗时
4. in-flight turn 数
5. release lineage 快照

设计要求：

1. Prometheus labels 保持低基数
2. `session_id / turn_id / trace_id` 不进入 Prometheus labels
3. 高基数事实继续放 trace / logs

### Step 4：把统一控制面出口接通

把新增 metrics 接入：

1. `/metrics`
2. `/metrics/prometheus`
3. 必要时补 system control surface 的 release 字段

### Step 5：测试与验收

执行最小必要测试：

1. `pytest tests/services/observability/test_release_lineage.py`
2. `pytest tests/api/test_system_router.py tests/api/test_main_entrypoints.py`
3. `pytest tests/api/test_unified_ws_turn_runtime.py -k observability`
4. 若增加 JS 侧变更，再补对应 node 测试

## 6. 验收标准

本批完成后，必须满足：

1. 任一 turn trace 都能看到 release lineage 六元组
2. `/metrics` 能看见 release 与 ws/turn runtime snapshot
3. `/metrics/prometheus` 能导出同一批低基数 runtime 指标
4. system contract 的 `trace_fields` 与实际 trace metadata 一致
5. 测试通过，且没有新增第二套 turn/session/release authority

## 7. 已知未覆盖与下一批

本批之后，下一批再做：

1. Web surface ack
2. wx_miniprogram surface ack
3. yousenwebview surface ack
4. release room 初版
5. ARR lite runner

这样切的原因不是保守，而是先把“版本事实 + runtime 事实”这条主 spine 建稳，再把表面 ACK 和评测层挂上去，整体风险最低。
