# 实施计划：DeepTutor Observability Phase 2（Surface ACK）

## 1. 本批目标

本批只做 PRD `Phase 2：表面 ACK 与 trace enrich` 的最小可交付实现，不提前展开 ARR/AAE/OA 的重平台部分。

范围收敛为：

1. 服务端新增统一 `surface telemetry intake`
2. `/metrics` 与 `/metrics/prometheus` 纳入表面事件与覆盖率快照
3. Web / `wx_miniprogram` / `yousenwebview` 接入 PRD 第一阶段必采事件中的高价值子集
4. 保持 best-effort、低基数、单一 authority，不阻塞真实聊天链路

明确不在本批直接交付：

1. 表面事件持久化数据库
2. 复杂前端离线队列
3. 完整 Release Room 页面
4. 自动把表面失败回灌 ARR dataset
5. 全量多端 E2E 自动化

## 2. 一等业务事实

本批维护的唯一业务事实是：

1. 服务端知道 turn 开始和结束，不等于用户真的看到了内容
2. 因此必须补一条从表面回链到 `session_id / turn_id / release_id` 的 ACK 证据链

对应 authority：

1. `turn authority`
   - 仍然只在 `/api/v1/ws`
   - 表面事件不得创造第二套会话或 turn 语义
2. `surface telemetry authority`
   - 只负责记录客户端对既有 turn 的表面观察
   - 只消费既有 `session_id / turn_id / user_id / release_id`
   - 不参与路由决策、不参与聊天执行

## 3. 事件词汇表与第一批范围

PRD 的必采事件共有十个；本批优先落高价值、低歧义、可稳定验证的一组：

1. `ws_connected`
2. `start_turn_sent`
3. `session_event_received`
4. `first_visible_content_rendered`
5. `done_rendered`
6. `user_cancelled`
7. `resume_attempted`
8. `resume_succeeded`
9. `surface_render_failed`

说明：

1. `user_retry_clicked` 先不作为统一客户端基础设施事件落库，本批留在下一轮与具体 UI 重试行为一起收口
2. 所有事件都必须带 `event_id`
3. 所有事件都必须允许 best-effort 丢失，绝不阻塞主链路

## 4. 交付物

### 4.1 服务端

1. 新增表面 telemetry 服务，负责：
   - 事件校验与归一化
   - `event_id` 去重
   - 低基数聚合
   - recent events 快照
2. 新增 HTTP intake 路由
3. `/metrics` 增加：
   - `surface_events`
   - `coverage`
4. `/metrics/prometheus` 增加：
   - `deeptutor_surface_event_total{surface,event_name,status}`
   - `deeptutor_surface_first_render_coverage_ratio{surface}`
   - `deeptutor_surface_done_render_coverage_ratio{surface}`

### 4.2 客户端

1. Web：
   - start/resume/cancel/session/ws open
   - 首次可见内容 render
   - done render / render failed
2. `wx_miniprogram`：
   - 对应 WS 生命周期与消息渲染事件
3. `yousenwebview`：
   - 对应 WS 生命周期与消息渲染事件
   - 保留既有 analytics，不替代，只补统一 intake

### 4.3 测试

至少覆盖：

1. 服务端 intake 去重与覆盖率计算
2. `/metrics` 与 `/metrics/prometheus` 的新增输出
3. `wx_miniprogram` 的事件回调接线
4. `yousenwebview` 的事件回调接线

## 5. 设计约束

1. 不新增第二套聊天入口，不新增 WS 路由
2. Prometheus labels 只允许低基数：`surface / event_name / status`
3. `session_id / turn_id / event_id / user_id` 不进入 Prometheus labels
4. 客户端 telemetry 失败必须静默退化
5. 允许 ACK 缺失，但缺失只能被记录为 `unknown / missing`，不能伪装成成功
6. 先收口统一词汇表和 intake，再考虑持久化和 dashboard

## 6. 文件级切口

预计会改这些文件：

1. `deeptutor/api/main.py`
2. `deeptutor/api/runtime_metrics.py`
3. `deeptutor/api/routers/observability.py`
4. `deeptutor/services/observability/__init__.py`
5. `deeptutor/services/observability/surface_events.py`
6. `tests/api/test_runtime_metrics.py`
7. 视实现需要新增 `tests/api/test_observability_router.py`
8. `web/context/UnifiedChatContext.tsx`
9. `web/components/chat/home/ChatMessages.tsx`
10. 视实现需要新增 `web/lib/surface-telemetry.ts`
11. `wx_miniprogram/utils/ws-stream.js`
12. `wx_miniprogram/pages/chat/chat.js`
13. 视实现需要新增 `wx_miniprogram/utils/surface-telemetry.js`
14. `wx_miniprogram/tests/test_ws_stream.js`
15. `yousenwebview/packageDeeptutor/utils/ws-stream.js`
16. `yousenwebview/packageDeeptutor/pages/chat/chat.js`
17. 视实现需要新增 `yousenwebview/packageDeeptutor/utils/surface-telemetry.js`

## 7. 实施步骤

### Step 1：建立服务端 surface telemetry authority

新增统一服务，负责：

1. 校验 `surface / event_name / event_id`
2. 记录事件计数
3. 维护 recent events
4. 计算覆盖率快照
5. 处理 duplicate event

设计要求：

1. 允许无认证事件，但若有认证信息应回填 `user_id`
2. 不依赖数据库
3. 内存态退化可接受

### Step 2：暴露 intake 与 OM 出口

新增路由：

1. `POST /api/v1/observability/surface-events`

并把其结果接入：

1. `/metrics`
2. `/metrics/prometheus`

### Step 3：接入 Web 事件

在现有 `UnifiedChatContext` 和消息渲染层补：

1. `start_turn_sent`
2. `ws_connected`
3. `session_event_received`
4. `resume_attempted`
5. `resume_succeeded`
6. `user_cancelled`
7. `first_visible_content_rendered`
8. `done_rendered`
9. `surface_render_failed`

### Step 4：接入小程序事件

`wx_miniprogram` 与 `yousenwebview` 都按同一词汇表补：

1. WS 打开
2. session 事件接收
3. resume
4. cancel
5. 首次可见内容刷到页面
6. done 已渲染
7. 恢复失败或渲染失败

### Step 5：验证

执行：

1. `pytest tests/api/test_runtime_metrics.py tests/api/test_observability_router.py tests/api/test_system_router.py::test_turn_contract_endpoint_exposes_unified_schema`
2. `node wx_miniprogram/tests/test_ws_stream.js`

若 `yousenwebview` 无独立测试 harness，则至少保证：

1. 代码路径与 `wx_miniprogram` 对齐
2. 无语法错误

## 8. 验收标准

本批完成后，必须满足：

1. `/metrics` 能看到 surface event 快照与覆盖率
2. `/metrics/prometheus` 能导出 surface 低基数指标
3. Web 与两个小程序表面至少都能上报 `start_turn_sent / first_visible_content_rendered / done_rendered`
4. 任一 ACK 事件都能回链 `session_id / turn_id`
5. telemetry 失败不会阻塞聊天主流程

## 9. 已知风险与替代方案

1. Web 首次可见内容判断基于组件首次渲染成功，而不是浏览器真实像素可见
   - 这是第一阶段可接受 proxy
   - 后续若需要更严定义，可引入 `IntersectionObserver`
2. 小程序 ACK 仍可能在切后台时丢失
   - 第一阶段允许记为 `coverage unknown`
   - 不可伪造成功
3. 当前服务端为内存态聚合
   - 适合先建立统一词汇表和控制面出口
   - 若后续需要历史追踪，再接轻量持久化
