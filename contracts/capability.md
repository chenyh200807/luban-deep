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

## Schema

- 机器可读 schema：`deeptutor/capabilities/request_contracts.py`
- 当前已导出的 schema：`CAPABILITY_REQUEST_SCHEMAS`

## 必测项

- `tests/runtime/test_orchestrator_autoroute.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
