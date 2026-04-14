# Config Runtime Contract

## 范围

这一份 contract 管：

- runtime config 加载
- `.env` / catalog / persisted settings 的优先级
- provider 解析与 fallback
- 模型、embedding、search、rag provider 的统一解析语义

## 单一控制面

- 单一 config 入口：`deeptutor/services/config/*`
- 单一 provider runtime 解析：`provider_runtime.py`
- 单一 env 读取通道：`env_store.py`

## 硬约束

1. 业务模块不得绕开 config runtime 直接各自读取 `.env` 并解释含义。
2. 同一 provider 决策不能在多个模块重复实现不同 fallback 逻辑。
3. “空值”“未设置”“显式禁用”三种语义必须统一解释。
4. 新增 provider 或配置源时，必须写清优先级和回退规则。
5. 线上与本地的配置行为必须由同一套 runtime 代码解释。

## 必测项

- `tests/services/config/test_provider_runtime.py`
- `tests/services/config/test_embedding_runtime.py`
- `tests/services/config/test_knowledge_base_config.py`
