# DeepTutor Observability OA/OM 根因修复报告

- 时间：2026-07-13 18:11 Asia/Shanghai
- 执行 cwd：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- Git authority：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- 最终专家裁决：GO（代码修复可交付）；当前 live runtime 仍 BLOCKED（SHA/dirty authority 不一致）

## 根因与收权

真正坏掉的一等业务事实是：日报把“candidate release、live runtime、离线 artifact、进程本地 store”拼成了一条看似完整的证据链，但它们并不一定来自同一运行时 authority。

争夺 authority 的位置包括：旧 daily wrapper 回读、进程内空 SurfaceEventStore、`--metrics-json`/TestClient fallback、仅按 SHA 判断 runtime、以及 `WS=None` 被 release gate 当健康。

修复后的唯一放行链为：`live /metrics provenance` → 严格 runtime identity（SHA、环境、FF、deploy manifest、双方 clean）→ synthetic WS → ARR/benchmark → observer/OA/release/daily。任一环缺失都 fail-closed；离线 artifact 只能用于离线分析，不能授权 live side effect。

## 已修复

1. 删除 observer 对上一轮 `daily_trends/latest` 的回读，消除 N-1 反馈环。
2. observer 优先消费目标 runtime `/metrics.surface_events`，不再把日报进程自己的空 store 当 release truth。
3. metrics transport fallback 默认关闭；只有显式 opt-in 才允许 TestClient，且 fallback/artifact 不得触发 live WS、ARR 或 benchmark。
4. synthetic WS 前置严格 runtime identity；同 SHA 但环境、FF、manifest 不同，或任一侧 dirty/unknown，均 BLOCKED。
5. `unified_ws_smoke=None/DEFERRED` 在 release gate 中 fail-closed。
6. daily verdict 对缺失/UNKNOWN lineage 与缺失 gate fail-closed，不再误标 TRUSTED。
7. synthetic WS 不再本地铸造 `student_demo` token；缺少合规 eval-runner token 时 DEFERRED。
8. automation 配置改以父仓 `.env` 为唯一环境 authority；不得复制/软链 `artifacts/.env`。

## 验证

- 聚焦根因测试：92 passed。
- observability 全套：327 passed。
- contract guard：passed；无 protected contract domain 变更。
- `py_compile`、`git diff --check`：passed。
- 真实失败路径：candidate `91e01e57e3ac`，live runtime `954c830c7bc5`；生成 `runtime_authority_preflight.json` 后退出 1，未推进 observer/OA/release/daily。
- 最终独立专家冷审：GO。

## 提交

- `f9e27fda`：包含 observer daily-loop 删除及其测试（并行 authority 提交）。
- `91e01e57`：runtime strict preflight、artifact/live 隔离与 WS gate fail-closed（并行 authority 提交）。
- `c7dbd018`：剩余 runtime authority、eval token、verdict 与 metrics-surface 实现收口。
- `02ddfce0`：metrics-surface authority 反例测试补齐。

## 尚未关闭

- 当前 `:8001` 仍由另一 worktree 的临时进程提供，runtime SHA 为 `954c830c7bc5`；本轮未杀进程、未部署。
- foreign-release OM 仍可能先写 shared `om_runs/latest.json`；主 daily 已阻断，但独立 reader 的 lineage filter 是后续 P1。
- Langfuse、冻结窗口 turn/chat/product 数据、Playwright 与真微信 DevTools 仍是外部证据缺口，不能由本修复推导为 release ready。
- Web surface telemetry 的 Bearer/401 producer 缺陷应另开窄修复，不与本次 authority spine 混改。

## 最小下一步 prompt

`在不杀未知进程、不部署的前提下，审计并修复 om_runs/latest 的 foreign-release reader lineage filtering；先写跨 SHA latest 反例，再做最小收权，保持 artifacts cwd，并只提交相关文件。`
