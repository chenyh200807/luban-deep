# Capability Contract

## 范围

这一份 contract 管：

- capability 路由决策
- capability request config schema
- orchestrator 选择 capability 的规则
- registry 作为唯一 capability 注册入口

## 单一控制面

- 单一 capability 入口：`ChatOrchestrator`
- 单一 capability schema 源：`deeptutor/capabilities/request_contracts.py`
- 单一 capability 注册入口：`CapabilityRegistry`

## 硬约束

1. capability 选择必须由 orchestrator 主导，router 不得偷偷维持第二套主路由逻辑。
2. capability config 不得在不同入口使用不同字段名表达同一语义。
3. 公开 capability config 必须先过 `request_contracts.py` 校验。
4. 新 capability 如果有公开配置，就必须补 schema 和 request validator。
5. adapter 可以做输入归一化，但不能成为 capability 决策的真实来源。
6. semantic router / rollout mode / shadow decision 也属于 orchestrator 的 capability 控制面；`mobile`、`unified_ws` 这类 adapter 只能传递 hints / auth / transport metadata，不能并行决定 capability。
7. adapter 如果需要把 token claims、wallet identity 或旧字段 alias 归一到 canonical 用户上下文，也只能服务于统一 request config 装配；不能把 capability 选择下沉到 adapter 本身。
8. 响应风格公开字段只能使用 `requested_response_mode`；`teaching_mode` 若仍被旧入口传入，只能在 adapter 层归一化并删除，不能继续作为 capability config 或路由决策字段存在。
9. 请求里的 `capability` 只允许作为 hint；最终写入 turn/session 的 capability 必须是 orchestrator runtime-resolved canonical capability，不能把 request hint 当成持久化真相。
10. adapter 可以做 presentation / timestamp / conversation read-model 装配，但不得在装配层重新决定 capability、改写 canonical final answer、或把 presentation blocks 当作 capability 执行结果的新 authority；adapter 输出必须来自 runtime-resolved turn/session/message 真相。
11. `exam_track` 这类领域上下文只能作为 request config / interaction_hints / metadata 的 scoped input 进入 orchestrator 和 capability；它不得改变 capability 选择权威，也不得被 adapter 用来创建平行 capability。

## Schema

- 机器可读 schema：`deeptutor/capabilities/request_contracts.py`
- 当前已导出的 schema：`CAPABILITY_REQUEST_SCHEMAS`

## 必测项

- `tests/runtime/test_orchestrator_autoroute.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
