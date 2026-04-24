# 鲁班智考反馈 Top10 根因修复计划

Status: Draft
Date: 2026-04-24
Scope: TutorBot / unified turn / mobile history / observability logs

## 目标

把运营反馈、用户反馈、阿里云后台日志和 Langfuse 证据收敛成 10 个可执行问题，按 3 个一组修复。每一组都必须先用测试锁住失败形状，再做最小代码改动。

## 非目标

- 不新增第二条聊天 WebSocket；聊天仍走 `/api/v1/ws`。
- 不新增 TutorBot 以外的业务身份。
- 不把临时 debug 面板、Langfuse trace、tool call 当成用户正文来源。
- 不在同一批次里顺手重构无关 UI 或历史代码。

## Root-Cause Gate

### 一等业务事实

学员在小程序里看到的是一个连续、可删除、可回看、专业可信的建筑实务学习对话；后台可以完整追踪运行过程，但后台过程不能泄露到用户正文。

### 单一 authority

- 对话身份: `SQLiteSessionStore.sessions.conversation_id` 是小程序对话的 canonical id；`sessions.id` 只是内部持久化行 id。
- turn 正文: `result.metadata.response` 或明确 public final content 是 canonical final answer。
- 时间: 服务端负责把秒级持久化时间转换成对外明确单位，不能让客户端猜秒/毫秒。
- 后台日志: `data/user/logs/deeptutor_YYYYMMDD.log` 是本地文本日志 authority，保留期由启动/初始化逻辑硬清理到 90 天。

### Competing authorities

- raw `tb_*` session id 与 `tutorbot:bot:...:chat:tb_*` mirror id 同时参与列表、删除、消息读取。
- 前端直接消费秒级 float 时间，导致按毫秒解释时显示 1970。
- public content stream、tool trace、provider error、Langfuse output 都可能被当成 assistant final。
- question generation 的内部 agent 输出、答案解析和题卡 presentation 边界不清。

## Top10 问题与批次

| # | 问题 | 证据 | 根因 | 修复批次 |
| --- | --- | --- | --- | --- |
| 1 | 历史会话重复、删除后重现、404 Conversation not found | 阿里云 SQLite 同一 `conversation_id` 同时存在 raw `tb_*` 与 `tutorbot:...:tb_*`；日志有 DELETE 404 | `session.id` 和 `conversation_id` 都在当对话 authority | Batch 1 |
| 2 | 会话日期显示 1970 年 1 月 | 阿里云 `sessions.created_at` 是 Unix seconds，如 `1777025696.61565` | 对外 payload 没有明确毫秒/ISO，客户端可误按毫秒解析 | Batch 1 |
| 3 | 后台/tool 内容泄露给用户 | Langfuse trace `e73e601...` 输出 fenced `bash read_file ...` | final answer guard 只挡一部分内部话术，未挡 tool command / XML / provider error | Batch 1 |
| 4 | 练题生成空回复或中断后无可用结果 | Langfuse `2e1b8d...` deep_question cancelled，内部已生成部分题但 final 为空 | turn terminal 状态和 partial artifact 物化策略不一致 | Batch 2 |
| 5 | “只出题不要答案”仍出现答案/解析或数量不一致 | 用户反馈 + Langfuse generator 产出含答案解析 | 题目 presentation、fallback text、assistant content 三套输出边界不清 | Batch 2 |
| 6 | 原始 provider error 暴露给用户 | Langfuse `DataInspectionFailed` 被写入 assistant_content | provider error 没有在 terminal public error 层统一降噪 | Batch 2 |
| 7 | RAG / Supabase timeout 导致慢、空、质量不稳 | Langfuse `supabase.rpc.search_unified ReadTimeout` | retrieval 失败没有稳定降级和用户可见解释 | Batch 3 |
| 8 | 后台运行日志缺少 90 天保留硬约束 | 阿里云已有文本日文件，但代码未见 retention 测试/清理 | 日志写入和保留策略分离，没有启动时强约束 | Batch 3 |
| 9 | 专业考试方向错配，如一造/一建混用 | 用户反馈：一造提问变一建答案 | exam track 不是 TutorBot runtime 的单一显式上下文 | Batch 3 |
| 10 | 小程序交互按钮、键盘、返回、复制、充值体验问题 | 多份反馈截图集中出现 | 原生表面缺少统一 interaction QA gate | Batch 4 |

## Batch 1 验收标准

1. 给定 raw `tb_*` 与 mirror session 同属一个 `conversation_id`，列表、消息读取、删除必须按同一个对话处理。
2. 小程序会话列表返回 ISO 时间和毫秒时间字段；旧秒级字段不再作为唯一时间来源。
3. `read_file` / fenced `bash` / `<rags>` / provider error / toolcall 形态的内容不会进入用户正文，统一降级为安全提示。

## Batch 1 实施记录

Status: Implemented locally and verified on Aliyun

代码入口：

- `deeptutor/api/routers/mobile.py`
- `deeptutor/services/session/sqlite_store.py`
- `deeptutor/services/user_visible_output.py`

修复内容：

1. `_load_mobile_conversation_variants` 不再在 direct `session.id` 命中后提前返回，而是继续合并同一 `conversation_id` 下的 TutorBot mirror row；delete / batch / messages 共享同一加载路径。
2. `list_sessions_by_owner_and_conversation` 同时按 `sessions.conversation_id` 和 `sessions.id` 查找，兼容历史 raw `tb_*` 行。
3. 小程序会话列表新增 `created_at_ms` / `updated_at_ms`，并把 `created_at` / `updated_at` 输出为 ISO 字符串，避免客户端误把秒级时间当毫秒。
4. 用户可见输出 guard 新增 tool command、`<rags>`、toolcall、provider raw error 识别，统一降级为安全提示，后台 trace/log 仍保留原始信息。

验证：

- `pytest tests/api/test_mobile_router.py -q`
- `pytest tests/services/test_user_visible_output.py -q`
- `pytest tests/services/session/test_sqlite_store.py -q -k "session_payloads_do_not_expose_internal_runtime_state or list_sessions_by_owner_filters_source_and_archived or list_sessions_by_owner_and_conversation_uses_canonical_id or list_sessions_supports_keyset_cursor"`
- `pytest tests/api/test_unified_ws_turn_runtime.py -q -k "prefers_result_response_as_assistant_content"`
- 本地端到端：`python scripts/run_mobile_login_smoke.py --api-base-url http://127.0.0.1:8019 --register --username-prefix codexbatch1 --first-message '请只回复：第一轮ok。' --second-message '继续上一轮，请只回复：第二轮ok。' --timeout-seconds 90`
  - run_id: `mobile-login-smoke-1777033187`
  - result: `passed=true`
  - covered: auth/register, create conversation, two `/api/v1/ws` turns, message history read, conversation delete cleanup
  - cleanup check: local SQLite had zero remaining rows for `tb_0aad729c071845e7b2f2bae1`
- 阿里云端到端：
  - deploy: selective sync to `/root/deeptutor`, rebuild image with `bash scripts/server_restart_aliyun.sh`, container `deeptutor` healthy.
  - internal run: `docker exec deeptutor python scripts/run_mobile_login_smoke.py --api-base-url http://127.0.0.1:8001 --register --username-prefix aliyunbatch1 ...`
    - run_id: `mobile-login-smoke-1777035029`
    - result: `passed=true`
    - conversation_id: `tb_fd151155acd045658844bf38`
  - public run: `docker exec deeptutor python scripts/run_mobile_login_smoke.py --api-base-url https://test2.yousenjiaoyu.com --register --username-prefix aliyunpub1 ...`
    - run_id: `mobile-login-smoke-1777035067`
    - result: `passed=true`
    - conversation_id: `tb_4700bbc225a444bbacfd833c`
  - public timestamp contract: `created_at` / `updated_at` returned ISO strings and `created_at_ms` / `updated_at_ms` returned millisecond integers for `tb_d273b7ebd9894f568dac73ce`.
  - cleanup check: Aliyun SQLite had zero remaining rows for all three smoke conversations.
  - observability: Langfuse traces recorded both internal and public smoke turns for `tb_fd151155acd045658844bf38` and `tb_4700bbc225a444bbacfd833c`.

## Batch 2 验收标准

1. deep_question 被取消或超时时，不把空 assistant content 当成成功完整回答。
2. “只出题不要答案”请求的用户可见题卡不展示答案解析。
3. provider 原始错误被统一转为用户可理解的失败提示，并保留后台 trace。

## Batch 2 实施记录

Status: Implemented locally and verified on Aliyun

代码入口：

- `deeptutor/services/session/turn_runtime.py`
- `deeptutor/api/routers/mobile.py`
- `deeptutor/services/render_presentation.py`

修复内容：

1. turn 取消和失败路径现在会物化一条安全 assistant message，避免历史里只剩用户问题或空回复。
2. 取消和失败的 public error event 只返回安全提示；原始 provider error 继续留在后台日志 / trace，不进入用户正文。
3. 小程序消息序列化时会重新规范化 presentation；非 `review_mode` 的题卡会清空 `followup_context.correct_answer` 与 `explanation`，讲评模式才允许展示答案解析。
4. 部署时补齐 `render_presentation.py`，保证云上 presentation builder 与移动端序列化出口使用同一份签名和同一套答案隐藏 contract。

验证：

- `pytest tests/api/test_mobile_router.py -q`
- `pytest tests/api/test_unified_ws_turn_runtime.py -q -k "prefers_result_response_as_assistant_content or cancels_superseded_running_turn_before_new_turn or provider_raw_error or replays_events_and_materializes_messages"`
- `pytest tests/services/test_user_visible_output.py -q`
- 阿里云部署：
  - selective sync to `/root/deeptutor`, including `render_presentation.py`, then rebuild with `bash scripts/server_restart_aliyun.sh`.
  - container `deeptutor` healthy; `/readyz` passed on both `http://127.0.0.1:8001` and `https://test2.yousenjiaoyu.com`.
- 阿里云公网端到端：
  - normal auth/chat/history/delete smoke: `mobile-login-smoke-1777036591`, `passed=true`, conversation `tb_b1f6fc77016d4abfb84a76f3`.
  - cancellation smoke: conversation `tb_270a19904bd44fd9b9cbe25c` returned user-visible cancel text `本轮生成已取消，请重新发送或换个题目继续。` and did not expose `Turn cancelled`.
  - presentation smoke: conversation `tb_d9eaadacc4b5464fbb0edf95` returned status 200 and `followup_context.correct_answer=""`, `explanation=""` for non-review MCQ.
  - cleanup check: Aliyun SQLite had zero remaining `sessions` / `messages` rows for all Batch 2 smoke conversations.
  - observability: Langfuse ClickHouse traces for `tb_b1f6fc77016d4abfb84a76f3` and `tb_270a19904bd44fd9b9cbe25c` show public assistant output; cancellation trace output is the safe cancel text, not raw backend status.
- 云上生产容器未安装 `pytest`，因此没有在正在服务的容器内临时安装 dev 依赖；云上验证以公网 HTTP/WS + Langfuse + SQLite 为准，代码级回归在本地完成。

## Batch 3 验收标准

1. RAG timeout 有明确 degraded metadata、可观测日志和用户可见降级。
2. 后台文本日志每日落盘，启动时自动清理 90 天以前的 `deeptutor_YYYYMMDD.log`。
3. exam track 进入 TutorBot runtime canonical config，不再由 prompt 猜。
4. retention 有单元测试，不依赖人工清理。

## Batch 4 验收标准

1. 小程序关键交互完成 DevTools 或真机回归清单。
2. Top10 文档状态更新为 Implemented / Remaining Risk。
