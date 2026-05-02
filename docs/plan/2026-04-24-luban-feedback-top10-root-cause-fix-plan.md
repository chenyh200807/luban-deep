# 鲁班智考反馈 Top10 根因修复计划

Status: Draft (Batch 1-4 implemented; 2026-04-25 Batch A-H implemented locally, with selected Aliyun/DevTools verification noted per batch)
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

## Batch 3 实施记录

Status: Implemented locally and verified on Aliyun

代码入口：

- `deeptutor/tools/builtin/__init__.py`
- `deeptutor/tutorbot/agent/tools/deeptutor_tools.py`
- `deeptutor/services/rag/pipelines/supabase.py`
- `deeptutor/services/rag/service.py`
- `deeptutor/logging/logger.py`
- `deeptutor/services/exam_track.py`
- `deeptutor/services/session/turn_runtime.py`
- `deeptutor/tutorbot/agent/loop.py`
- `deeptutor/agents/chat/agentic_pipeline.py`

修复内容：

1. RAG 低层 contract 仍保留 typed `RAGError`；用户可见工具层统一转为 `retrieval_degraded=true` / `retrieval_status=failed`，并返回安全降级提示，不泄露 Supabase timeout 原文。
2. Supabase partial retrieval warning 进入 payload、evidence bundle 与 observability metadata；`RAGService` raw log capture 覆盖 `deeptutor.SupabasePipeline`。
3. 文本日志 authority 固定为 `data/user/logs/deeptutor_YYYYMMDD.log`，`Logger` 初始化时按文件日期自动删除 90 天以前的 DeepTutor 日志文件，忽略 malformed / unrelated logs。
4. 新增 canonical `exam_track` normalizer，支持 `first_construction / second_construction / first_cost / second_cost`；`一造` 等显式用户输入进入 runtime config、session preferences、trace metadata、TutorBot prompt instruction 和 RAG routing metadata。
5. review 后补充多考试方向防误持久化：比较/选择类问题如“一建和一造有什么区别”不会写入单一 `exam_track`；只有否定后剩余唯一方向或单方向明确请求才持久化。

本地验证：

- `pytest tests/services/rag/test_rag_failure_contract.py tests/services/rag/test_rag_pipelines.py -q`
- `pytest tests/core/test_capabilities_runtime.py -q -k "rag_adapter_tool"`
- `pytest tests/core/test_chat_capability_mode_selection.py -q`
- `pytest tests/logging/test_log_retention.py tests/logging/test_json_file_logging.py tests/logging/test_request_context.py -q`
- `pytest tests/services/test_exam_track.py tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_bootstraps_interaction_hints_as_soft_system_guidance tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_persists_exam_track_as_scoped_runtime_metadata -q`
- `pytest tests/services/test_exam_track.py tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_persists_exam_track_as_scoped_runtime_metadata -q`
- `python -m compileall deeptutor/services/exam_track.py deeptutor/services/session/turn_runtime.py deeptutor/tools/builtin/__init__.py deeptutor/tutorbot/agent/tools/deeptutor_tools.py deeptutor/tutorbot/agent/loop.py deeptutor/agents/chat/agentic_pipeline.py deeptutor/services/rag/pipelines/supabase.py deeptutor/logging/logger.py`

阿里云验证：

- deploy: selective sync to `/root/deeptutor`, rebuild image with `bash scripts/server_restart_aliyun.sh`, container `deeptutor` healthy.
- readiness: `http://127.0.0.1:8001/readyz` and `https://test2.yousenjiaoyu.com/readyz` both returned `ready=true`.
- public auth/chat/history smoke:
  - run_id: `mobile-login-smoke-1777039129`
  - result: `passed=true`
  - conversation_id: `tb_bb93952b64f34e519fbb6da1`
  - first assistant: `一级造价方向已确认。`
  - second assistant: `仍按一级造价。`
- SQLite runtime authority check before cleanup:
  - raw conversation row stored `exam_track=first_cost` and `interaction_hints.exam_track=first_cost`.
  - smoke cleanup removed both raw and TutorBot mirror rows; remaining `sessions=0`, `messages=0`.
- Langfuse ClickHouse evidence:
  - trace `8a384b4892dc61552d73af4735bdc56e` for `tb_bb93952b64f34e519fbb6da1` stored `metadata['exam_track']='first_cost'` and output `一级造价方向已确认。`
  - trace `1d2560133cdd24093b821e30810aca8d` stored `metadata['exam_track']='first_cost'` and output `仍按一级造价。`
- retention simulation in live container:
  - `_prune_legacy_text_logs(..., retention_days=90)` removed only `deeptutor_20251231.log`; kept boundary `deeptutor_20260124.log`, malformed log, and unrelated log.
- RAG degradation simulation in live container:
  - forced typed `RAGSearchError(stage='pipeline.search', retryable=True)`.
  - `RAGTool` returned `success=false`, `retrieval_degraded=true`, `retrieval_status=failed`, and public status event without raw timeout text.
- real RAG probe in live container:
  - `rag_search('一造工程计价索赔处理原则', kb_name='construction-exam', routing_metadata.exam_track='first_cost')`
  - provider `supabase`, `source_count=6`, `retrieval_status=ok`, `retrieval_degraded=false`.
- text log evidence:
  - `/app/data/user/logs/deeptutor_20260424.log` exists and contains restart, Langfuse, and RAGService entries after deployment.

## Batch 4 验收标准

1. 小程序关键交互完成 DevTools 或真机回归清单。
2. Top10 文档状态更新为 Implemented / Remaining Risk。

## Batch 4 实施记录

Status: Implemented locally and synced to Aliyun source; automated wx/yousenwebview tests passed; DevTools Computer Use Chinese copy loop verified

Root-cause gate:

- 一等业务事实：小程序操作按钮必须执行用户当下看到的动作；复制复制可见内容，返回返回可用入口，不能依赖 raw message 或页面栈刚好存在。
- 单一 authority：复制以当前 message 的可见渲染状态为 authority；充值页返回以微信页面栈为优先 authority，失败时回到 chat entry。
- Competing authorities：`msg.content`、`renderableContent`、structured `blocks`、`mcqCards` 曾同时表达“回答正文”；`navigateBack` 曾假设页面栈一定存在。

代码入口：

- `wx_miniprogram/pages/chat/chat.js`
- `wx_miniprogram/pages/billing/billing.js`
- `wx_miniprogram/tests/test_chat_copy_authority.js`
- `wx_miniprogram/tests/test_billing_navigation.js`
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- `yousenwebview/tests/test_package_chat_copy_authority.js`

修复内容：

1. `onCopy` 不再直接复制 `msg.content`；AI 消息优先按可见题卡、结构化 block、再到 `renderableContent/content` 生成剪贴板文本。
2. 结构化表格、公式、步骤、总结、图表 fallback table、MCQ 题卡都有稳定文本序列化，避免用户点“复制回答”得到空内容或 raw fallback。
3. 根包充值页 `goBack` 先走 `wx.navigateBack`；如果页面是外部直达或没有上一页，自动 `switchTab` 回 `/pages/chat/chat`。
4. 当前微信开发者工具实际运行的是 `yousenwebview/packageDeeptutor`，因此把复制 authority 修复移植到分包 chat；分包 billing 已有 `navigateBack -> reLaunch(route.chat())` 兜底，不重复加分支。
5. DevTools 真实表格复制暴露出本地 fixture 过窄：真实 markdown parser 的 table cell 不是 `{text: ...}`，而是 `content / nodes / children` inline tree；补充 `_copyInlineNodesText` 后，复制 authority 能递归读取真实渲染节点文本。
6. 原始反馈中的历史页残留继续收口：`capability=tutorbot` 是内部 runtime 身份，历史页用户可见标签统一显示为“智能对话”；历史预览清理 markdown table separator 行和旧缓存里已经压平的 `------ ------`，避免列表继续显示内部身份或 markdown 分隔符。
7. 历史页缓存读取时不再直接相信 60 秒内的展示态缓存，会先重新清洗 `preview / capabilityLabel / searchText`，避免旧缓存把已修复问题短时间内继续带回 UI。

本地验证：

- `node wx_miniprogram/tests/test_chat_copy_authority.js`
- `node wx_miniprogram/tests/test_billing_navigation.js`
- `node wx_miniprogram/tests/test_history_display_authority.js`
- `node wx_miniprogram/tests/test_chat_layout.js`
- `node wx_miniprogram/tests/test_ai_message_state.js`
- `for f in wx_miniprogram/tests/test_*.js; do node "$f"; done`
- `node yousenwebview/tests/test_package_chat_copy_authority.js`
- `node yousenwebview/tests/test_history_display_authority.js`
- `node yousenwebview/tests/test_billing_packages.js`
- `node yousenwebview/tests/test_chat_workspace_shell_layout.js`

阿里云源码验证：

- selective sync to `/root/deeptutor`:
  - `wx_miniprogram/pages/chat/chat.js`
  - `wx_miniprogram/pages/billing/billing.js`
  - `wx_miniprogram/tests/test_chat_copy_authority.js`
  - `wx_miniprogram/tests/test_billing_navigation.js`
  - `wx_miniprogram/tests/test_history_display_authority.js`
  - `yousenwebview/packageDeeptutor/pages/chat/chat.js`
  - `yousenwebview/packageDeeptutor/pages/history/history.js`
  - `yousenwebview/tests/test_package_chat_copy_authority.js`
  - `yousenwebview/tests/test_history_display_authority.js`
  - this plan document
- 远端宿主机没有 `node`，因此通过 Docker Node runtime 挂载 `/root/deeptutor` 运行：
  - `node wx_miniprogram/tests/test_chat_copy_authority.js`
  - `node wx_miniprogram/tests/test_billing_navigation.js`
  - `node wx_miniprogram/tests/test_chat_layout.js`
  - `node wx_miniprogram/tests/test_ai_message_state.js`
  - `node yousenwebview/tests/test_package_chat_copy_authority.js`
  - `node yousenwebview/tests/test_billing_packages.js`
  - `node yousenwebview/tests/test_chat_workspace_shell_layout.js`
- 结果全部通过。

DevTools / 真机状态：

- Computer Use 找到正在运行的 `微信开发者工具 Stable v2.01.2510290`，项目为 `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview`。
- 模拟器从 `pages/freeCourse/freeCourse` 点击“开始答疑”，进入 `packageDeeptutor/pages/login/login`，用户授权后点击“微信一键登录”，真实路由进入 `packageDeeptutor/pages/chat/chat`，显示用户 `chenyh2008` 与余额 `997646`，调试器面板 `Errors: 0`。
- 先用英文表格问题做 smoke 时发现旧修复仍不完整：页面 toast 显示“内容已复制”，但系统剪贴板只有多行 `|`，说明不能只看 toast，必须核对 `pbpaste`。
- 根因证据：DevTools Console 读取当前 message 后确认真实表格 cell 结构为 `content / nodes / children` inline tree，旧 `_copyCellText` 只读 `text / value`，因此真实 parser 表格复制成空 cell。
- 修复后用中文真实问题验证：`请用一个两列表格回答：防火门考点和分值。不要超过20字。`
- 页面生成中文表格：`考点 / 分值`，含 `安装牢固、启闭灵活`、`密封条安装质量`、`开启方向`、`标识`、`常闭门自动关闭`、`常开门联动控制`。
- 点击“复制回答”后，`pbpaste` 返回：
  - `考点 | 分值`
  - `安装牢固、启闭灵活 | 0.5`
  - `密封条安装质量 | 0.5`
  - `开启方向 | 1`
  - `标识 | 0.5`
  - `常闭门自动关闭 | 0.5`
  - `常开门联动控制 | 1`
- 2026-04-25 继续用 Computer Use 验证历史页：从 `pages/freeCourse/freeCourse` 点击“开始答疑”，进入 `packageDeeptutor/pages/chat/chat`，再点击底部“历史”；真实页面路径为 `packageDeeptutor/pages/history/history`。
- 历史页真实列表显示 `18 条对话`、`18 近 7 天`；第一条防火门表格会话显示用户可见标签“智能对话”，预览为 `考点 分值 安装牢固、启闭灵活...`，未再出现内部 `TutorBot` 标签或 markdown 分隔符 `------ ------`。

## 2026-04-25 Two-Item Batch A 验收标准

1. #3 页面路由和返回：从分包 chat 切到底部 report/history/profile 后，再回到 chat，必须保留当前对话上下文；chat 页面重建时不能只恢复 session id 却显示空白欢迎态。
2. #9 移动端输入和遮挡：chat 输入框必须用键盘高度和安全区作为唯一布局 authority；历史页顶部管理按钮必须避让微信胶囊区域。
3. 本批只修 route continuity 与 input layout 两个 authority，不把反馈按钮、拖动菜单、支付、摸底测试混入同一补丁。

## 2026-04-25 Two-Item Batch A 实施记录

Status: Implemented locally and synced to Aliyun source; automated wx/yousenwebview tests passed locally and on Aliyun; DevTools Chinese input/send smoke passed

Root-cause gate:

- 一等业务事实：学习中切换页面不能丢当前会话；输入和顶部按钮不能被键盘或系统胶囊遮挡。
- 单一 authority：分包 workspace shell 的 `workspaceBack` 是回到当前学习任务的 authority；chat 当前会话由 `current_session_id + conversation_id` 补水；输入区高度由 keyboard height、safe bottom 和 workspace shell height 共同计算，但只在 chat surface 统一写入。
- Competing authorities：`wx.reLaunch` 销毁页面栈后，chat 只留下 `_sid/_convId`，没有消息补水；底部 fixed bar、键盘高度、底部 tab shell、历史页 capsule top 各自做局部布局，导致遮挡。
- 修法类型：收敛 writer-reader，不新增新路由、不新增专用 WebSocket、不增加 fallback interpreter。

代码入口：

- `yousenwebview/packageDeeptutor/custom-tab-bar/index.js`
- `wx_miniprogram/pages/chat/chat.js`
- `wx_miniprogram/pages/chat/chat.wxml`
- `wx_miniprogram/pages/history/history.js`
- `wx_miniprogram/pages/history/history.wxml`
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- `yousenwebview/packageDeeptutor/pages/chat/chat.wxml`
- `yousenwebview/packageDeeptutor/pages/history/history.js`
- `yousenwebview/packageDeeptutor/pages/history/history.wxml`

修复内容：

1. 分包自定义底栏从任何工作区页面切走时都保留当前页面作为 `workspaceBack`，避免 chat -> history/report/profile 后左上角无法回到原对话。
2. chat 页面在 `current_session_id` 存在但消息为空时自动调用 `_restoreConversation` 补水，避免只有 session id 而用户看到空白欢迎态。
3. 根包和分包 chat 的两个 textarea 都绑定 `cursor-spacing`、`bindfocus`、`bindblur`，输入框聚焦后使用键盘高度重算底部 bar 与 spacer。
4. 分包 chat 在键盘打开时临时把 bottom bar 提到键盘上方，键盘关闭时回到 workspace shell 上方或安全区上方。
5. 根包和分包 history 顶部内容增加 `navRightInset`，按微信胶囊 left/right 计算右侧避让，避免“管理”按钮和小程序关闭胶囊重合。

本地验证：

- `node wx_miniprogram/tests/test_chat_surface_layout_contract.js`
- `node wx_miniprogram/tests/test_chat_copy_authority.js`
- `node wx_miniprogram/tests/test_billing_navigation.js`
- `node wx_miniprogram/tests/test_history_display_authority.js`
- `node yousenwebview/tests/test_workspace_shell_navigation_authority.js`
- `node yousenwebview/tests/test_package_chat_surface_layout_contract.js`
- `node yousenwebview/tests/test_package_chat_copy_authority.js`
- `node yousenwebview/tests/test_history_display_authority.js`
- `node yousenwebview/tests/test_chat_bootstrap_authority.js`
- `node yousenwebview/tests/test_deeptutor_runtime_state.js`
- `node yousenwebview/tests/test_cross_home_navigation.js`
- `node yousenwebview/tests/test_chat_workspace_shell_layout.js`

阿里云源码验证：

- selective sync to `/root/deeptutor`:
  - `wx_miniprogram/pages/chat/chat.js`
  - `wx_miniprogram/pages/chat/chat.wxml`
  - `wx_miniprogram/pages/history/history.js`
  - `wx_miniprogram/pages/history/history.wxml`
  - `wx_miniprogram/tests/test_chat_surface_layout_contract.js`
  - `yousenwebview/packageDeeptutor/custom-tab-bar/index.js`
  - `yousenwebview/packageDeeptutor/pages/chat/chat.js`
  - `yousenwebview/packageDeeptutor/pages/chat/chat.wxml`
  - `yousenwebview/packageDeeptutor/pages/history/history.js`
  - `yousenwebview/packageDeeptutor/pages/history/history.wxml`
  - `yousenwebview/tests/test_workspace_shell_navigation_authority.js`
  - `yousenwebview/tests/test_package_chat_surface_layout_contract.js`
  - `yousenwebview/tests/test_chat_bootstrap_authority.js`
  - this plan document and Top10 issue register
- 远端通过 Docker Node runtime 挂载 `/root/deeptutor` 跑同一组 12 个测试，全部通过。

DevTools 真实界面验证：

- Computer Use 打开正在运行的 `微信开发者工具 Stable v2.01.2510290`，项目为 `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview`。
- 从 `pages/freeCourse/freeCourse` 点击“开始答疑”进入 `packageDeeptutor/pages/chat/chat`。
- 用中文真实输入验证两行输入：`请用两行回答：` + `防火门验收看什么？`；输入框可见换行，发送后进入有消息态，底部输入区没有被底栏遮住。
- 页面生成中文建筑实务回答，包含“外观、尺寸、配件、开启方向、密封性能、产品合格证、型式检验报告”等内容；该 smoke 证明本批输入布局修复没有破坏真实问答主链路。

剩余风险：

- 物理返回键/左上角返回从 login `reLaunch` 后回首页的完整矩阵还需要 DevTools 或真机继续跑。
- 原始反馈里的反馈按钮不可点、底部菜单拖动、对比分析多次点击属于交互命令 authority，不在本批布局修复内。
- 历史页以外的顶部 chrome 页面如果仍有胶囊遮挡，需要按同一 `navRightInset` 规则继续收敛。
- 底部“对话 -> 历史 -> 回对话”的视觉点击路径本批已有本地和阿里云自动化断言覆盖；DevTools 本轮只完成中文输入/发送 smoke，未把该视觉矩阵误报为已完成。

## 2026-04-25 Two-Item Batch B 验收标准

1. #7 出题/练题/摸底测试：摸底题目必须有稳定题号和 answer sheet；空白提交、部分提交、全部提交的语义必须区分；缺后端 `question_id` 时不能让 `undefined` 进入答题状态 authority。
2. #1 登录/授权/二次进入：微信主登录按钮不能触发 `getPhoneNumber` 高频限制；已登录用户从佑森入口进入鲁班智考时不能先显示登录页再纠偏；token 失效仍由目标页/API 层回收。
3. 本批只修 assessment 页面合同和登录入口 readiness；不把后端题库数量、练题生成性能、SMS 运营商送达延迟误报为已关闭。

## 2026-04-25 Two-Item Batch B 实施记录

Status: Implemented locally and synced to Aliyun source; automated wx/yousenwebview tests passed locally and on Aliyun; DevTools login navigation probe started

Root-cause gate:

- #7 一等业务事实：一次摸底测试必须有稳定题目 id、当前题、已答/未答状态和提交语义；UI 只能渲染这个投影，不能靠最后一题按钮猜提交状态。
- #7 单一 authority：`questions + selectedKeys` 是小程序本地答题状态 authority；`answerSheet / answeredCount / unansweredCount` 只由它们计算，不另存第二套状态。
- #1 一等业务事实：用户已有有效 token 时，入口应直接进入已登录学习态；只有目标页/API 明确 auth expired 时才回登录页。
- #1 单一 authority：宿主入口只传 authenticated hint；后端/API 仍是最终身份 authority，登录页不再用 profile bootstrap 阻塞已登录跳转。

代码入口：

- `wx_miniprogram/pages/assessment/assessment.js`
- `wx_miniprogram/pages/assessment/assessment.wxml`
- `wx_miniprogram/pages/assessment/assessment.wxss`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`
- `wx_miniprogram/pages/login/login.js`
- `wx_miniprogram/pages/login/login.wxml`
- `yousenwebview/app.js`
- `yousenwebview/pages/deeptutorEntry/deeptutorEntry.js`
- `yousenwebview/packageDeeptutor/pages/login/login.js`
- `yousenwebview/packageDeeptutor/pages/login/login.wxml`

修复内容：

1. 摸底测试题目归一化时给缺失 `question_id/id` 的题目补稳定 fallback id：`q_1`、`q_2` 等，避免多题共用 `undefined` 答题槽。
2. 根包和分包 assessment 增加答题卡，展示“已答 x / total”、题号格子、已答/当前状态，并支持点击题号跳题。
3. `answeredCount / unansweredCount / answerSheet` 统一由 `questions + selectedKeys + currentIndex` 计算；上一题、下一题、跳题、选项选择都会同步。
4. 提交语义区分三态：0 题作答显示“尚未作答”；部分作答显示“还有 N 题未答”；全部作答直接提交。
5. 微信主登录按钮从 `open-type="getPhoneNumber"` 改为普通 `bindtap="handleWechatLogin"`，手机号绑定不再抢占主登录入口，避免真实环境 `invoke getPhoneNumber too frequently`。
6. 佑森宿主入口给 deeptutor bridge 传 `authenticated=1/0`；本地 token 未过期时，bridge 加载分包后直接 redirect 到 `returnTo/chat`，不先进入 login 页。
7. 登录页如果被直达且已有 token，立即进入 chat/returnTo，不再等待 `getUserInfo()` profile bootstrap；token 清理由目标页/API 的 `AUTH_EXPIRED` 链路处理。

本地验证：

- `node wx_miniprogram/tests/test_assessment_contract.js`
- `node wx_miniprogram/tests/test_practice_entry_prompts.js`
- `node wx_miniprogram/tests/test_login_token_preserve.js`
- `node wx_miniprogram/tests/test_auth_token_expiry.js`
- `node yousenwebview/tests/test_package_assessment_contract.js`
- `node yousenwebview/tests/test_cross_home_navigation.js`
- `node yousenwebview/tests/test_deeptutor_entry_bridge.js`
- `node yousenwebview/tests/test_login_primary_wechat_authority.js`
- `node yousenwebview/tests/test_wechat_bind_phone_authority.js`
- `node yousenwebview/tests/test_wechat_login_resilience.js`
- `node yousenwebview/tests/test_login_send_code_feedback.js`
- `node yousenwebview/tests/test_login_token_preserve.js`
- `git diff --check`

阿里云源码验证：

- selective sync to `/root/deeptutor` for Batch B changed files and tests.
- 远端通过 Docker Node runtime 挂载 `/root/deeptutor` 跑同一组 12 个测试，全部通过。

DevTools 状态：

- Computer Use 已连接正在运行的 `微信开发者工具 Stable v2.01.2510290`，项目为 `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview`。
- 当前模拟器页面为 `pages/freeCourse/freeCourse`，调试器不再出现本批修复前的 `getPhoneNumber too frequently`；可见的剩余错误来自宿主课程接口 `https://www.yousenjiaoyu.com/getmajorzm net::ERR_HTTP2_PROTOCOL_ERROR`，不属于鲁班智考登录入口。
- 已在 Console 发起跳转登录页探针；因用户已有登录态，后续应验证入口直接进 `packageDeeptutor/pages/chat/chat`，不能把它误报成完整真机扫码验收。

剩余风险：

- #7 后端 `MemberConsoleService.create_assessment(count=20)` 仍需补 `requested_count/delivered_count` 和题库去重证据；当前修复只保证前端答题状态和提交语义稳定。
- #7 聊天练题入口仍主要靠 prompt 表达“5 题/不要答案”；后续应改为结构化 `deep_question` config，并处理 redacted public context 不覆盖 internal grading authority。
- #1 手机号验证码 1-2 分钟送达需要 SMS provider 日志和接口耗时证据；本批只拆开主登录按钮、入口 readiness 和 token gate。
- #1 登录动画和按钮 pending 仍可继续降级，但当前最核心的 getPhoneNumber 频控和已登录闪登录页已经收住。

## 2026-04-25 Three-Item Batch C 验收标准

Source: `曾美婵-鲁班智答问题反馈(1)(1).pptx` slides 1-3.

1. #9 复制答案：用户点击“复制回答”时，必须复制当前可见答案投影，覆盖结构化表格、题卡、公式和普通文本；不能复制 raw fallback 或空内容。
2. #9 反馈入口：消息级反馈必须能选标签、提交、失败不误报；产品级意见反馈必须有一等入口，不能让用户只靠猜拇指图标。
3. #5 中文引号：中文正文里的中文术语引用统一为 `“…”`；不能破坏 JSON、URL、代码块、行内代码和英文术语。

## 2026-04-25 Three-Item Batch C 实施记录

Status: Implemented locally; selectively synced to Aliyun before the final copy-serializer hardening; backend restarted healthy; automated root/package tests passed locally and on Aliyun source; Computer Use DevTools E2E completed for chat send, copy, message feedback, and profile feedback entry visibility.

Root-cause gate:

- 一等业务事实：用户看到的答案和反馈控件必须可操作、可复制、可读；后台/结构化/代码形态不能泄漏成用户正文或破坏中文阅读。
- 单一 authority：复制以 chat message 的可见渲染投影为 authority；消息级反馈以现有 `submitFeedback` API 为 authority；产品级意见反馈用微信原生 `open-type="feedback"`，不新增第二套后端页面；中文引号规范化由 `normalize_markdown_for_tutorbot` 承担，renderer 不做第二套格式 truth。
- Competing authorities：`msg.content`、`blocks`、`mcqCards` 曾同时争夺复制正文；“反馈”混合了消息质量反馈和产品意见反馈；小程序 renderer 如果也做中文标点替换，会和后端 final answer 形成重复 authority。
- 修法类型：收权和降级，不新增聊天 WebSocket、不新增反馈路由、不新增独立标点 renderer。

代码入口：

- `deeptutor/tutorbot/markdown_style.py`
- `tests/services/test_tutorbot_markdown_style.py`
- `wx_miniprogram/pages/chat/chat.js`
- `wx_miniprogram/pages/chat/chat.wxml`
- `wx_miniprogram/pages/chat/chat.wxss`
- `wx_miniprogram/pages/profile/profile.js`
- `wx_miniprogram/pages/profile/profile.wxml`
- `wx_miniprogram/pages/profile/profile.wxss`
- `wx_miniprogram/tests/test_chat_feedback_interaction.js`
- `wx_miniprogram/tests/test_chat_copy_authority.js`
- `wx_miniprogram/tests/test_profile_feedback_entry_contract.js`
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- `yousenwebview/packageDeeptutor/pages/chat/chat.wxml`
- `yousenwebview/packageDeeptutor/pages/chat/chat.wxss`
- `yousenwebview/packageDeeptutor/pages/profile/profile.js`
- `yousenwebview/packageDeeptutor/pages/profile/profile.wxml`
- `yousenwebview/packageDeeptutor/pages/profile/profile.wxss`
- `yousenwebview/tests/test_package_chat_feedback_interaction.js`
- `yousenwebview/tests/test_package_chat_copy_authority.js`
- `yousenwebview/tests/test_package_profile_feedback_entry_contract.js`
- this plan document and Top10 issue register

修复内容：

1. 复制：Computer Use 在微信开发者工具里真实点击“复制回答”时暴露出 `[object Object],[object Object]` 序列化泄漏；根因是复制路径把 rich-text node/list/paragraph 当普通对象 `String()`。本批把 loose node/text/blocks 统一收口到一个复制文本 serializer，根包和分包共用同一行为测试，确保复制的是当前可见答案文本而不是对象投影。
2. 消息级反馈：点踩后自动锚定到底部，避免弹窗被 fixed composer 影响；标签改为 `catchtap`，提交进入 `feedbackSubmitting` 状态；API 成功才显示“感谢反馈”并关闭，失败保留弹窗并提示“提交失败，请稍后重试”。
3. 产品级反馈：根包和分包 `profile` 链接区新增“意见反馈”，使用微信原生 `open-type="feedback"`，不新增自定义页面或后端路由。
4. 中文引号：`normalize_markdown_for_tutorbot` 将中文正文中的 `'中文'` / `‘中文’` 规范为 `“中文”`，并收紧中文引号外侧空格；跳过 fenced code、inline code、JSON-like 行和 URL。

微信开发者工具 Computer Use E2E：

- 从 `pages/freeCourse/freeCourse` 点击“开始答疑”进入 `packageDeeptutor/pages/chat/chat`。
- 真实输入并发送：`请用一个两列表格回答：防火门考点和分值；并说明‘强梁弱柱’这个词应该怎么理解。不要超过80字。`
- 后端链路可达，但当前模型 provider 返回 `Authentication Fails, Your api key: *486e is invalid`；因此正常 AI 答案和中文引号用户可见终态尚不能在 DevTools 里闭环验证。
- 复制：修复前点击“复制回答”后系统剪贴板为 `[object Object],[object Object],[object Object],[object Object],[object Object]`；修复并热重载后再次点击，剪贴板为当前可见错误答案文本，不再泄漏对象字符串。
- 消息反馈：点击点踩后反馈弹窗可见，选择标签并提交后出现“感谢反馈”，证明消息级反馈入口、标签和提交链路可操作。
- 产品反馈：进入 `packageDeeptutor/pages/profile/profile` 后可见“意见反馈”原生入口；无障碍点击和模拟器坐标点击均未弹出可观察原生反馈面板，判断为当前 DevTools 对 `open-type="feedback"` 面板不显式/不支持，需要真机补验。
- DevTools 仍有既存 `routeDone with a webviewId 155 is not found`、`selectable` deprecation、IntersectionObserver warning；它们不是本批 #1-#3 的直接根因，未在本批扩大处理。

本地验证：

- `pytest tests/services/test_tutorbot_markdown_style.py tests/services/test_user_visible_output.py -q`
- `python -m compileall deeptutor/tutorbot/markdown_style.py deeptutor/services/session/turn_runtime.py`
- `node wx_miniprogram/tests/test_chat_copy_authority.js`
- `node wx_miniprogram/tests/test_chat_feedback_interaction.js`
- `node wx_miniprogram/tests/test_profile_feedback_entry_contract.js`
- `node yousenwebview/tests/test_package_chat_copy_authority.js`
- `node yousenwebview/tests/test_package_chat_feedback_interaction.js`
- `node yousenwebview/tests/test_package_profile_feedback_entry_contract.js`
- `node wx_miniprogram/tests/test_chat_surface_layout_contract.js`
- `node wx_miniprogram/tests/test_history_display_authority.js`
- `node yousenwebview/tests/test_package_chat_surface_layout_contract.js`
- `node yousenwebview/tests/test_history_display_authority.js`
- `node yousenwebview/tests/test_chat_bootstrap_authority.js`
- `node yousenwebview/tests/test_workspace_shell_navigation_authority.js`

阿里云 Langfuse 核对：

- `jgzk-langfuse-clickhouse` 容器健康，`traces` / `observations` 表可查询。
- 查询 `强梁弱柱` 相关输出，找到 2026-04-24 多条 `llm.stream` / `tutorbot.llm.stream` 证据；部分最终摘要已使用中文双引号，说明目标格式可行。
- 查询中文单引号/JSON 输出，找到题目生成链路里 fenced JSON 与中文引号混用的历史证据；因此本批选择后端 Markdown 出口规范化并保护 JSON/代码块，而不是在小程序 renderer 中粗暴全局替换。

阿里云部署与验证：

- selective sync to `/root/deeptutor` for Batch C changed files and tests.
- `bash scripts/server_restart_aliyun.sh` rebuild / restart succeeded; container `deeptutor` became healthy.
- readiness: `http://127.0.0.1:8001/readyz` and `https://test2.yousenjiaoyu.com/readyz` both returned `ready=true`.
- live container normalizer smoke confirmed `‘强梁弱柱’ -> “强梁弱柱”` while preserving fenced JSON / JSON-like text.
- remote source Node tests via `docker run --rm -v /root/deeptutor:/app -w /app node:22-slim ...`:
  - `node wx_miniprogram/tests/test_chat_feedback_interaction.js`
  - `node wx_miniprogram/tests/test_profile_feedback_entry_contract.js`
  - `node yousenwebview/tests/test_package_chat_feedback_interaction.js`
  - `node yousenwebview/tests/test_package_profile_feedback_entry_contract.js`

剩余风险：

- 阿里云源码同步发生在 DevTools 发现 `[object Object]` 后续 hardening 之前；若要把云端源码也更新到最终状态，需要再同步 `chat.js` 与复制 authority 测试并跑远端 Node 回归。
- 当前 provider API key `*486e` 无效，阻塞真实 AI 正常答案的 DevTools E2E，因此中文引号只能确认到后端单测、live container normalizer smoke 和 Langfuse 历史证据，尚未确认到用户可见正常答案。
- 微信开发者工具中产品级 `open-type="feedback"` 入口可见但未弹出原生面板；需要真机环境确认微信原生反馈面板。
- 实时流式 token 仍可能先显示未规范化片段；终态和历史入库会走 `normalize_markdown_for_tutorbot`。若要做到实时显示也完全一致，下一步应让小程序在收到 canonical `result.response` 时替换最终消息，而不是前端自己做标点规则。
- 如果产品要求把“意见反馈”进入内部 BI，而不是微信原生反馈，需要另立 `feedback product contract`；当前最小方案故意不新增后端概念。

## 2026-04-25 Two-Item Batch D 验收标准

Source: Top10 issue register #2 and #10.

1. #2 充值/支付：余额和套餐必须来自唯一账户/套餐 authority；如果真实支付链路不存在，页面必须明确说明不可用原因，不能把一个占位 toast 伪装成“立即充值”。
2. #10 成就/学情/扩展能力：成就必须优先读后端 badge catalog；点击成就要能解释获得条件；诊断图在深色和浅色模式都可读；未接入的联网搜索、图片/文档分析、思维导图必须有统一可用性状态，不继续制造假入口。

## 2026-04-25 Two-Item Batch D 实施记录

Status: Implemented locally; backend package-authority fix selectively synced to Aliyun and `deeptutor` restarted healthy; automated backend/Node tests passed except one pre-existing date-sensitive member list test in the wider suite; WeChat DevTools simulator verified profile capability truth, badge modal, and billing package/disabled-payment state.

Root-cause gate:

- 一等业务事实：充值、余额、成就和扩展能力入口都必须告诉用户真实系统状态；不能让用户点一个看似可用但没有后端 authority 的入口。
- 单一 authority：余额读 `/api/v1/billing/wallet`；套餐默认值由 `MemberConsoleService._default_packages()` 投影到 wallet payload；成就读 `/api/v1/profile/badges`；小程序只负责展示能力可用性，不新增支付/上传/思维导图后端概念。
- Competing authorities：充值套餐曾在根小程序 4 档、佑森分包 3 档、后端 4 档、以及已持久化的旧 `member_console.packages` 快照之间漂移；成就曾由前端本地 catalog 和后端 `/profile/badges` 同时表达；雷达图颜色曾只按深色背景设计，浅色模式可读性不足。
- 修法类型：收权和降级。真实微信支付缺少 `create order -> wx.requestPayment -> payment callback -> wallet grant ledger` 主链路，本批不伪造支付，只把 UI 状态改为真实不可用并收敛套餐 authority。

代码入口：

- `deeptutor/services/member_console/service.py`
- `tests/services/member_console/test_service.py`
- `wx_miniprogram/pages/billing/billing.js`
- `wx_miniprogram/pages/billing/billing.wxml`
- `wx_miniprogram/pages/billing/billing.wxss`
- `wx_miniprogram/pages/profile/profile.js`
- `wx_miniprogram/pages/profile/profile.wxml`
- `wx_miniprogram/pages/profile/profile.wxss`
- `wx_miniprogram/pages/report/report.js`
- `wx_miniprogram/tests/test_billing_payment_availability.js`
- `wx_miniprogram/tests/test_profile_badges_authority.js`
- `wx_miniprogram/tests/test_profile_capability_status_contract.js`
- `wx_miniprogram/tests/test_report_radar_palette_contract.js`
- `yousenwebview/packageDeeptutor/pages/billing/billing.js`
- `yousenwebview/packageDeeptutor/pages/billing/billing.wxml`
- `yousenwebview/packageDeeptutor/pages/billing/billing.wxss`
- `yousenwebview/packageDeeptutor/pages/profile/profile.js`
- `yousenwebview/packageDeeptutor/pages/profile/profile.wxml`
- `yousenwebview/packageDeeptutor/pages/profile/profile.wxss`
- `yousenwebview/packageDeeptutor/pages/report/report.js`
- `yousenwebview/tests/test_billing_packages.js`
- `yousenwebview/tests/test_package_profile_badges_authority.js`
- `yousenwebview/tests/test_package_profile_capability_status_contract.js`
- `yousenwebview/tests/test_package_report_radar_palette_contract.js`
- this plan document and Top10 issue register

修复内容：

1. 套餐 authority：后端默认套餐从旧 4 档 `9.9/39/79/169` 收敛到已拍板的 `9/99/199 -> 100/1200/2600` 三档；根小程序默认套餐也改为同一三档；前端 billing 会优先采用 wallet payload 里的 `packages`。
   - 2026-04-25 DevTools 复测发现远端 wallet payload 仍在覆盖前端默认值，真实页面继续显示旧 4 档。补充修复：`_load_unlocked()` 读取 member console 存储时强制把 `data["packages"]` 投影为 `_default_packages()`，避免历史 JSON 快照继续争夺套餐 authority；新增 `test_load_replaces_stale_persisted_packages_with_canonical_three_packages` 覆盖该根因。
2. 支付入口：两套 billing 的 `onRecharge()` 不再只显示“充值功能即将上线” toast；在 `paymentAvailability.enabled=false` 时弹出明确说明“充值通道正在接入微信支付”，并把按钮文案展示为“暂未开放”。
3. 成就：两套 profile 优先调用 `api.getBadges()`，使用后端 badge catalog/earned 状态；接口失败时才回退 `auth/profile.earned_badge_ids`；成就点击弹窗展示获得条件。
4. 扩展能力：两套 profile 增加统一 `capabilityItems`，把联网搜索、图片/文档分析、思维导图明确展示为“未开放”，点击说明原因，避免用户误以为入口缺失是卡住。
5. 雷达图：两套 report 的 canvas 绘制增加深色/浅色 palette，网格、轴线、边线、点和标签按主题切换，修复浅色模式看不清。

本地验证：

- `pytest tests/services/member_console/test_service.py::test_load_replaces_stale_persisted_packages_with_canonical_three_packages tests/services/member_console/test_service.py::test_production_bootstrap_starts_without_demo_members -q`
- `node wx_miniprogram/tests/test_billing_payment_availability.js`
- `node wx_miniprogram/tests/test_billing_navigation.js`
- `node yousenwebview/tests/test_billing_packages.js`
- `node wx_miniprogram/tests/test_profile_badges_authority.js`
- `node yousenwebview/tests/test_package_profile_badges_authority.js`
- `node wx_miniprogram/tests/test_profile_capability_status_contract.js`
- `node yousenwebview/tests/test_package_profile_capability_status_contract.js`
- `node wx_miniprogram/tests/test_report_radar_palette_contract.js`
- `node yousenwebview/tests/test_package_report_radar_palette_contract.js`
- `node wx_miniprogram/tests/test_report_radar_authority.js`
- `node yousenwebview/tests/test_report_radar_authority.js`
- `node yousenwebview/tests/test_report_snapshot_dedupe.js`
- `node yousenwebview/tests/test_profile_points_sync.js`
- `node wx_miniprogram/tests/test_profile_feedback_entry_contract.js`
- `node yousenwebview/tests/test_package_profile_feedback_entry_contract.js`
- `node wx_miniprogram/tests/test_report_layout.js`
- `node wx_miniprogram/tests/test_report_radar_fallback.js`
- `node yousenwebview/tests/test_report_radar_fallback.js`

阿里云与 DevTools 验证：

- 远端发布前备份：`/root/deeptutor/data/backups/deeptutor-data-user-20260425-143147Z.tar.gz`。
- selective sync：`deeptutor/services/member_console/service.py` 和对应测试同步到 `Aliyun-ECS-2:/root/deeptutor/`；`docker cp` 到容器后 `docker compose restart deeptutor`。
- 容器健康：`docker inspect -f '{{.State.Health.Status}}' deeptutor` 最终返回 `healthy`。
- 公网 ready：`https://test2.yousenjiaoyu.com/readyz` 返回 `ready=true`。
- 远端容器内 wallet authority smoke：`MemberConsoleService().get_wallet('student_demo')["packages"]` 返回 `[('trial','9',100), ('advance','99',1200), ('sprint','199',2600)]`。
- WeChat DevTools simulator：`packageDeeptutor/pages/profile/profile` 显示扩展能力 `联网搜索 / 图片/文档分析 / 思维导图` 均为 `未开放`；点击成就弹出获得条件；`packageDeeptutor/pages/billing/billing` 复测显示三档套餐 `100/1200/2600` 和按钮 `暂未开放`。DevTools 在复测中有自动热重载回首页，未作为业务失败处理。

更宽回归：

- `pytest tests/api/test_mobile_wallet_identity.py tests/services/member_console/test_service.py -q` 跑到 63/64 通过；唯一失败是 `test_list_members_supports_expiry_window_and_operational_flags`，测试数据把 `expire_at` 固定为 `2026-04-25T00:00:00+08:00`，当前日期已是 2026-04-25，导致“7 天内未过期”窗口变成已过期。判断为日期敏感测试，不是本批套餐/支付/成就改动引起。

剩余风险：

- 真实微信支付仍未完成，因为仓库没有下单、预支付、支付回调、幂等入账 contract。根治需要新增 `POST /api/v1/billing/orders`、微信支付参数生成、回调验签和 `wallet_service.grant_points(..., idempotency_key=order_id)`。
- 图片/文档分析和思维导图本批只做 availability truth，不做上传/解析/渲染能力。若要开放，必须另立 chat attachment contract，继续复用统一 `/api/v1/ws`，不能新增专用聊天 WebSocket。
- Root `wx_miniprogram` 还没有像 `yousenwebview/packageDeeptutor/utils/flags.js` 那样的 feature availability helper；本批只收敛用户可见状态，没有引入新的 feature gate 层。

## 2026-04-25 Two-Item Batch E 验收标准

Source: Top10 issue register #7 and #8.

1. #7 摸底/练题合同：题库只有 5 道唯一源题时，系统不能复制题目伪装成 20 道；后端必须返回 requested/delivered/question_bank/shortfall 事实，前端以 delivered questions 为答题 UI authority。
2. #7 批改 authority：公开题卡为了隐藏答案而 redacted 的 `followupContext` 不能反向覆盖 session 内部 active object 中的正确答案和解析。
3. #8 取消/超时：用户主动停止和 idle timeout 都必须回到统一 `/api/v1/ws` 的 `cancel_turn`，不能只在前端关闭 socket 留后端继续跑。
4. #8 修改问题：正在生成时点编辑用户消息，应该先停止当前 turn，并保留文本供用户修改重发。

## 2026-04-25 Two-Item Batch E 实施记录

Status: Implemented locally; automated backend/Node tests passed; Aliyun and WeChat DevTools E2E still pending for this batch.

Root-cause gate:

- 一等业务事实：练题 artifact 必须诚实维护“请求多少、实际交付多少、答案何时隐藏、提交后由谁批改”；长 turn 必须维护“同一个 authoritative turn 可取消并进入 terminal outcome”。
- 单一 authority：摸底题数由 `MemberConsoleService.create_assessment()` 写入和返回；批改答案由 session active object / internal followup context 持有；取消由 `TurnRuntimeManager` 和统一 `/api/v1/ws cancel_turn` 持有。前端只负责展示和投递意图。
- Competing authorities：旧实现把 5 道 `_ASSESSMENT_BANK` 循环扩展成 20 个 `question_id`，让 UI 以为交付了 20 道；公开题卡 redaction 后的空 `correct_answer` 可能作为 explicit context 抢掉内部批改 authority；idle timeout 过去只关闭小程序 socket，后端 turn 不一定被取消。
- 修法类型：收权。删除“复制题库凑数”的伪 authority；redacted explicit context 只携带用户答案，缺正确答案时由 stored active object 回补；超时和停止统一发 `cancel_turn`。

代码入口：

- `deeptutor/services/member_console/service.py`
- `deeptutor/services/session/turn_runtime.py`
- `tests/services/member_console/test_service.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `wx_miniprogram/pages/assessment/assessment.js`
- `wx_miniprogram/pages/assessment/assessment.wxml`
- `wx_miniprogram/pages/assessment/assessment.wxss`
- `wx_miniprogram/pages/chat/chat.js`
- `wx_miniprogram/utils/ws-stream.js`
- `wx_miniprogram/tests/test_assessment_contract.js`
- `wx_miniprogram/tests/test_ws_stream.js`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- `yousenwebview/packageDeeptutor/utils/ws-stream.js`
- `yousenwebview/tests/test_package_assessment_contract.js`
- `yousenwebview/tests/test_ws_stream_auth_refresh.js`

修复内容：

1. `create_assessment(count=20)` 在当前 5 道唯一源题库下返回 5 道题，并返回/持久化 `requested_count=20`、`delivered_count=5`、`available_count=5`、`question_bank_size=5`、`unique_source_question_count=5`、`shortfall_count=15`；不再循环复制同一源题。
2. assessment 页面消费后端题数事实，答题卡和进度以实际 `questions.length/delivered_count` 为 authority；短缺时显示“题库当前可用 X 题，本次先完成 Y 题”。
3. `turn_runtime` 在 explicit `followup_question_context` 已 redacted、但 candidate stored context 有 reference answer 时，用 stored context 回补正确答案/解析，只把 explicit context 里的 `user_answer` 合并进去，避免 public projection 污染 internal grading authority。
4. 小程序和分包 `ws-stream` 的 idle timeout 先发送 `{type:"cancel_turn", turn_id}`，展示“响应超时，正在停止本轮分析…”，再等待 `cancelled/done`；用户主动停止也复用同一 helper。
5. `onEdit` 在 streaming 中点击用户消息时，会先把原问题放回输入框，再发停止当前 turn 的意图，让“修改问题”不再静默失败。

本地验证：

- `pytest tests/services/member_console/test_service.py -k "assessment" -q`
- `pytest tests/api/test_mobile_router.py -k "assessment or start_turn" -q`
- `pytest tests/api/test_unified_ws_turn_runtime.py::test_redacted_public_followup_context_does_not_override_grading_authority -q`
- `node wx_miniprogram/tests/test_ws_stream.js`
- `node yousenwebview/tests/test_ws_stream_auth_refresh.js`
- `node wx_miniprogram/tests/test_assessment_contract.js`
- `node yousenwebview/tests/test_package_assessment_contract.js`
- `node yousenwebview/tests/test_chat_send_surface_telemetry.js`

剩余风险：

- 本批尚未同步到阿里云，也尚未在微信开发者工具里走真实慢请求/停止/修改问题 E2E；下一步必须做 selective sync、重启后端、远端 Node/pytest smoke，并在 DevTools 里用中文真实问题验证“超时取消”和“编辑后重发”。
- 练题结构化 config 仍未完全收敛。当前小程序练题入口仍有自然语言 prompt 表达“5 道题/不要答案”的路径；根治应在下一组把 `num_questions/question_type/reveal_answers/reveal_explanations` 明确送入 `deep_question` config，而不是继续依赖 router 从文本猜。

## 2026-04-25 Three-Item Batch F 验收标准

Source: `曾美婵-鲁班智答问题反馈(1)(1).pptx` slides 4-6.

1. 响应慢/暂停无反应/不能修改：用户点击停止时必须绑定到同一个 authoritative turn，不能只关闭前端 socket；停止过程必须有可见状态。
2. 学情诊断维度图不完整：报告页必须展示后端诊断维度的完整列表；雷达图不能在小屏固定 280px 导致裁切或不可读。
3. 历史 8 道题但学情统计 30 道题：实际完成题数和每日目标不能混成同一个 `total`；学习统计必须区分 actual attempts 与 target。

## 2026-04-25 Three-Item Batch F 实施记录

Status: Implemented locally; automated backend/Node tests passed; WeChat DevTools simulator verified report dimension display. Chat cancel UI E2E was attempted in DevTools but not fully completed because the simulator input/button focus did not trigger a send in this session, and the current provider key still returns `Authentication Fails`.

Root-cause gate:

- 一等业务事实：长分析 turn 必须可停止、可见、最终进入 terminal outcome；学情诊断必须展示全部 authoritative dimensions；练习统计必须把真实作答数和每日目标拆开。
- 单一 authority：取消由 `/api/v1/ws` + `TurnRuntimeManager` 持有；真实作答数由 `MemberConsoleService.learning.chapter_stats` 持有；目标只作为 `daily_target/target`；报告维度由 report API profile/radar 派生出的 `dimList` 展示。
- Competing authorities：旧小程序生成了 `clientTurnId` 但 `start-turn` 没传给后端，早停时拿不到 authoritative `turnId`；旧 `get_chapter_progress()` 用 `max(30, done, 1)` 把 target 冒充 total；host 分包已计算 `dimList` 但 WXML 没渲染，导致用户只能看到残缺雷达图。
- 修法类型：收权和减法。让 start-turn 接收并保存 `client_turn_id`，早停等待 authoritative `turnId` 后通过统一 WS 发送 `cancel_turn`；统计返回 real `done/total`，另给 `daily_target/target`；报告页直接渲染已有 `dimList`，不新增第二套诊断模型。

代码入口：

- `deeptutor/api/routers/mobile.py`
- `deeptutor/services/member_console/service.py`
- `tests/api/test_mobile_router.py`
- `tests/services/member_console/test_service.py`
- `wx_miniprogram/pages/chat/chat.js`
- `wx_miniprogram/pages/report/report.wxss`
- `wx_miniprogram/tests/test_report_layout.js`
- `wx_miniprogram/tests/test_ws_stream.js`
- `wx_miniprogram/utils/ws-stream.js`
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- `yousenwebview/packageDeeptutor/pages/report/report.wxml`
- `yousenwebview/packageDeeptutor/pages/report/report.wxss`
- `yousenwebview/packageDeeptutor/utils/ws-stream.js`
- `yousenwebview/tests/test_report_layout.js`
- `yousenwebview/tests/test_ws_stream_auth_refresh.js`

修复内容：

1. mobile `start-turn` request 增加 `client_turn_id`，并写入 turn config；小程序和分包 `ws-stream` 把前端已生成的 `clientTurnId` 传给 `start-turn`。
2. 早停逻辑不再在拿到 `turnId` 前直接 `aborted`；用户点击停止后先显示 `cancelling` 状态，等 `start-turn` 返回 authoritative `turnId` 后订阅统一 `/api/v1/ws` 并发送 `cancel_turn`。
3. `cancelled` 被视为 terminal-safe outcome，清理 timer/socket，触发 `onStatusEnd/onDone`，避免 UI 长时间停在分析中。
4. chat 页面 `_stop({ cancelTurn: true })` 会把当前 AI 消息更新为“正在停止本轮分析…”和“停止中”，让用户有明确反馈。
5. `get_chapter_progress()` 返回真实 `done/total`，并把 30 题目标改为 `target/daily_target`；provisional mastery 仍可用 daily target 做估算分母，但不污染完成题数。
6. host 分包报告页新增“各维度详情”列表，直接展示 `dimList` 的排名、名称、进度条和百分比；root/host 雷达图尺寸改为响应式 `560rpx; max-width: 100%`。

本地验证：

- `pytest -q tests/services/member_console/test_service.py -k "chapter_progress or report_analytics or chat_learning or submit_assessment"` -> `4 passed, 53 deselected`
- `pytest -q tests/api/test_mobile_router.py -k "start_turn_writes_requested_response_mode or followup_question_context"` -> `1 passed, 47 deselected`
- `node wx_miniprogram/tests/test_ws_stream.js` -> `PASS test_ws_stream.js (14 assertions)`
- `node yousenwebview/tests/test_ws_stream_auth_refresh.js` -> `PASS test_ws_stream_auth_refresh.js (10 assertions)`
- `node wx_miniprogram/tests/test_report_layout.js && node yousenwebview/tests/test_report_layout.js && node wx_miniprogram/tests/test_report_radar_authority.js && node yousenwebview/tests/test_report_radar_authority.js` -> all PASS

WeChat DevTools simulator:

- Project: `yousenwebview`
- Path verified: `packageDeeptutor/pages/report/report`
- Evidence: bottom tab `学情` opens report page; simulator displays `诊断维度` and newly rendered `各维度详情`; scrolling shows dimension rows `建筑构造 / 地基基础 / 主体结构 / 施工管理 / 防水工程` and `掌握分布` below.
- Existing DevTools console noise: `routeDone with a webviewId ... is not found` appeared during page route transitions, while the report page ultimately rendered correctly. Treated as DevTools route flake, not business failure.
- Chat cancel E2E: attempted to use simulator chat input/send, but focus/click did not trigger a real send in this run. The current environment also has provider auth failure (`api key ... invalid`), so real long-answer cancellation still needs a valid provider key and a stable simulator/phone run before it can be claimed complete.

剩余风险：

- 本批尚未同步到阿里云；不要把本地测试通过误报成线上完成。
- “完整诊断维度”当前按后端 `dimList`/chapter mastery 展示。如果产品要求固定 8 维能力模型，需要新增明确 learner analytics contract；不能用前端硬编码 8 维图治标。
- Chat stop/cancel 的 authority 链路已有自动化覆盖，但真实慢请求 + 用户点击停止仍需在有效模型 key 下做 WeChat DevTools 或真机复验。

## 2026-04-25 Two-Item Batch G 验收标准

Source: Top10 issue register #1 and #3.

1. #1 登录入口：已登录用户从主登录、手动登录、注册页进入时，不能再等 profile 请求决定是否跳转；本地 token 过期时也不能被误判为已登录。
2. #1 短信验证码：60 秒冷却必须由后端在调用阿里云 SMS provider 之前判定，重复点击不能继续拖慢或打到短信通道。
3. #3 页面路由：宿主包 `returnTo` 只能指向鲁班包内已知页面；宿主页或未知路径必须回 fallback，不能原样透传造成 404。
4. #3 深入口登录：无 token 被重定向登录时必须保留当前 package route，登录后回到用户原本要去的学习页。

## 2026-04-25 Two-Item Batch G 实施记录

Status: Implemented locally, selectively synced to Aliyun, backend restarted healthy, automated backend/Node tests passed locally and on Aliyun, and WeChat DevTools simulator verified the freeCourse -> chat -> history route path. Public mobile-login smoke passed for auth/session continuity, but the model provider key is still invalid, so AI answer quality is not closed by this batch.

Root-cause gate:

- 一等业务事实：入口要维护“用户是否真的有未过期登录态”和“登录后应该去哪里”这两个事实；路由层只承认鲁班包内合法目标。
- 单一 authority：登录态由 `auth_token + auth_token_exp` 判定；短信发送由 `MemberConsoleService.send_phone_code()` 决定冷却和 provider 调用；宿主包内跳转目标由 `packageDeeptutor/utils/route.js` 归一化。
- Competing authorities：旧 `isLoggedIn()` 只看 token 字符串；manual/register 继续用 profile 请求当跳转 gate；旧 `send_phone_code()` 先打短信 provider 再检查冷却；旧 `resolveInternalUrl()` 放行任意 `/pages/...`。
- 修法类型：收权。把过期判断收回 auth util，把冷却判断前置到 provider 之前，把 returnTo 白名单收回 route util。

代码入口：

- `deeptutor/services/member_console/service.py`
- `tests/services/member_console/test_service.py`
- `wx_miniprogram/utils/auth.js`
- `wx_miniprogram/pages/login/manual.js`
- `wx_miniprogram/pages/register/register.js`
- `wx_miniprogram/tests/test_auth_token_expiry.js`
- `wx_miniprogram/tests/test_login_token_preserve.js`
- `yousenwebview/packageDeeptutor/utils/auth.js`
- `yousenwebview/packageDeeptutor/utils/route.js`
- `yousenwebview/packageDeeptutor/utils/runtime.js`
- `yousenwebview/packageDeeptutor/pages/login/manual.js`
- `yousenwebview/packageDeeptutor/pages/register/register.js`
- `yousenwebview/tests/test_auth_token_expiry.js`
- `yousenwebview/tests/test_login_token_preserve.js`
- `yousenwebview/tests/test_route_authority.js`
- `yousenwebview/tests/test_runtime_auth_return_to.js`

修复内容：

1. 两套小程序 `auth.isLoggedIn()` 改为检查 `auth_token_exp`，过期时清理 token 并返回未登录。
2. 两套 manual/register 页面已登录时直接跳 chat/returnTo，不再先请求 profile；profile 失效仍由目标页/API 401 统一处理。
3. `send_phone_code()` 先读取本地验证码记录并计算冷却；冷却期内直接返回“请等待 N 秒后再试”，不调用 `_send_sms()`。
4. 宿主包 `resolveInternalUrl()` 增加已知包内页面白名单；`/pages/report/report` 这类鲁班页 alias 会归一到 `/packageDeeptutor/...`，宿主页 `/pages/freeCourse/freeCourse` 和未知包路径回 fallback。
5. `runtime.checkAuth()` 无 token 跳登录时携带当前 package route 作为 `returnTo`。

本地验证：

- `pytest tests/services/member_console/test_service.py -k "phone_code or send_phone_code" -q` -> `6 passed, 52 deselected`
- `pytest tests/api/test_mobile_router.py -k "auth_send_code or auth_verify_code or wechat_login or wechat_bind_phone or auth_login" -q` -> `11 passed, 37 deselected`
- `python -m compileall deeptutor/services/member_console/service.py`
- `node wx_miniprogram/tests/test_auth_token_expiry.js`
- `node yousenwebview/tests/test_auth_token_expiry.js`
- `node wx_miniprogram/tests/test_login_token_preserve.js`
- `node yousenwebview/tests/test_login_token_preserve.js`
- `node yousenwebview/tests/test_route_authority.js`
- `node yousenwebview/tests/test_runtime_auth_return_to.js`
- `node yousenwebview/tests/test_deeptutor_entry_bridge.js`
- `node yousenwebview/tests/test_cross_home_navigation.js`
- `node yousenwebview/tests/test_workspace_shell_navigation_authority.js`
- `node yousenwebview/tests/test_login_primary_wechat_authority.js`
- `node yousenwebview/tests/test_wechat_login_resilience.js`
- `node yousenwebview/tests/test_wechat_bind_phone_authority.js`

阿里云验证：

- Backup: `/root/deeptutor/data/backups/deeptutor-data-user-20260425-152522Z.tar.gz`
- Selective sync: 本批代码和测试同步到 `Aliyun-ECS-2:/root/deeptutor/`；后端 `service.py` 已 `docker cp` 进 `deeptutor` 容器并 `docker compose restart deeptutor`。
- Health: 容器状态恢复 `healthy`；公网 `https://test2.yousenjiaoyu.com/readyz` 返回 `{"status":"ok","ready":true,...}`。
- Remote Node: 在阿里云 `node:22-slim` 容器内跑本批 auth/route/runtime 以及入口导航相关测试，全部 PASS。
- Remote SMS cooldown smoke: 容器内第一次 `send_phone_code('13955556666')` 返回 `sent=True, delivery=sms`；第二次立即调用返回 `sent=False, retry_after=60, message=请等待60秒后再试`，且 `provider_calls=1`，验证冷却发生在 provider 之前。
- Public mobile-login smoke: `scripts/run_mobile_login_smoke.py --api-base-url https://test2.yousenjiaoyu.com --register ...` 返回 `Passed: True`，最新 `run_id=mobile-login-smoke-1777131334`，conversation cleanup 成功。

WeChat DevTools simulator:

- `pages/freeCourse/freeCourse` 点击“开始答疑”进入 `packageDeeptutor/pages/chat/chat`，聊天首页为中文界面。
- 底部点击“历史”进入 `packageDeeptutor/pages/history/history`，页面显示 `20 条对话` 和历史记录列表；本轮未再出现 `invoke getPhoneNumber too frequently`。
- 历史页左上“对话”触发 route 回到 `packageDeeptutor/pages/chat/chat`；复核后页面已正常渲染中文聊天首页，判定前一次白屏为 DevTools 渲染延迟。

剩余风险：

- 公网 smoke 仍暴露模型 provider 返回 `Authentication Fails, Your api key: ****486e is invalid`，因此“登录后真实 AI 正常中文回答”和“历史记录不出现 raw provider error”还不能声明闭环；这属于下一轮 terminal truth / provider authority 修复，不应混同为 #1/#3 已彻底完成。
- 真机物理返回仍受微信 `reLaunch` 清页面栈影响；本批收紧了自定义返回和 returnTo authority，但“手机系统返回不退出小程序”需要单独真机策略，不宜用更多页面特例伪装根治。

## 2026-04-25 Two-Item Batch H 验收标准

Source: Top10 issue register #5 and #8.

1. #5 provider / SDK / raw backend error 不能进入用户可见 content、result response 或历史 assistant message；后台日志和 trace 仍保留原始错误用于排障。
2. #5 阿里云运行时 LLM provider authority 必须和实际可用 provider 一致；不能继续把 `deepseek-v4-flash` 绑到无效 DeepSeek official key 上。
3. #8 idle timeout 或用户停止后，前端必须先向统一 `/api/v1/ws` 的 authoritative turn 发送 `cancel_turn`，并等待 canonical terminal outcome；不能由页面二次 timeout 抢先给“响应超时”。
4. #8 取消等待状态必须有中文可见状态，避免用户误以为按钮无效。

## 2026-04-25 Two-Item Batch H 实施记录

Status: Implemented locally, selectively synced to Aliyun, backend restarted healthy, public mobile-login E2E passed with normal Chinese answer. WeChat DevTools page-level Chinese UI was inspected, but manual chat send was not closed because the simulator/console was polluted by an old localhost debug script and request-domain errors.

Root-cause gate:

- 一等业务事实：用户正文和历史只允许展示 public final answer；取消/超时只允许由同一个 authoritative turn 给出终态。
- 单一 authority：用户可见错误降噪由 `coerce_user_visible_answer()` 与 `TurnRuntimeManager._persist_and_publish()` 的 public event 边界持有；运行时模型 provider 由阿里云 `/root/deeptutor/.env` 加容器 env 持有；取消由 `/api/v1/ws cancel_turn` 加 TurnRuntime terminal status 持有。
- Competing authorities：`openai_compat_provider._handle_error()` 把 provider raw error 包成普通 `LLMResponse(content="Error: ...", finish_reason="error")`；`tutorbot/agent/loop.py` 把它当 final content；旧小程序 `ws-stream` 在发出 cancel 后仍可能第二次 idle timer 抢先 `failStream("响应超时，请重试")`；阿里云 `.env` 把可用的 DashScope `deepseek-v4-flash` 错绑到 DeepSeek official endpoint。
- 修法类型：收权。把 public terminal event 入库/推送前统一降噪；把阿里云 LLM provider 切回真实可用的 DashScope compatible endpoint；前端 cancel 后进入“等待终态”状态，不再让页面 timeout 抢 authority。

代码入口：

- `deeptutor/services/user_visible_output.py`
- `deeptutor/services/session/turn_runtime.py`
- `tests/services/test_user_visible_output.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `wx_miniprogram/utils/ws-stream.js`
- `wx_miniprogram/tests/test_ws_stream.js`
- `yousenwebview/packageDeeptutor/utils/ws-stream.js`
- `yousenwebview/tests/test_ws_stream_auth_refresh.js`

修复内容：

1. 用户可见输出 guard 新增 `Authentication Fails`、`authentication_error`、`invalid_request_error`、`api key ... invalid`、`Error code: 401` 识别，统一降级为“暂时未生成适合直接展示的答案，请重试一次。”
2. `TurnRuntimeManager._persist_and_publish()` 在 public content/result 事件持久化和推送前，对 `event.content`、`metadata.response`、嵌套 `metadata.metadata.response` 统一做 `coerce_user_visible_answer()` + TutorBot markdown normalizer，避免 WS 和历史消息绕过最终 message guard。
3. 两套小程序 `ws-stream` 在 idle timeout 时先发 `{type:"cancel_turn", turn_id}` 并展示“响应超时，正在停止本轮分析…”；发出 cancel 后后续 idle tick 展示“已发送停止请求，正在等待本轮结束…”，不再立即报页面级超时。
4. 用户主动停止和早停继续复用 authoritative turn id；socket close / cancelled terminal event 进入同一收口路径。
5. 阿里云 `.env` 运行时修正为 DashScope compatible provider：`LLM_BINDING=dashscope`、`LLM_MODEL=deepseek-v4-flash`、`LLM_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1`、`LLM_API_KEY` 使用现有 DashScope key；随后 `docker compose up -d --force-recreate deeptutor` 使容器 env 生效。

本地验证：

- `pytest tests/services/test_user_visible_output.py -q` -> `5 passed`
- `pytest tests/api/test_unified_ws_turn_runtime.py -q -k "provider_raw_error or provider_auth_error_returned_as_result or cancel"` -> `3 passed, 66 deselected`
- `node wx_miniprogram/tests/test_ws_stream.js` -> `PASS test_ws_stream.js (20 assertions)`
- `node yousenwebview/tests/test_ws_stream_auth_refresh.js` -> `PASS test_ws_stream_auth_refresh.js (17 assertions)`
- `python -m compileall deeptutor/services/user_visible_output.py deeptutor/services/session/turn_runtime.py`

阿里云验证：

- 旧 runtime 证据：容器日志反复出现 `Authentication Fails, Your api key: ****486e is invalid`，直接请求 DeepSeek official endpoint 返回 HTTP 401。
- provider authority probe：同一台阿里云机器上用现有 DashScope key 请求 compatible endpoint，`deepseek-v3.2` 与 `deepseek-v4-flash` 均返回 HTTP 200。
- 部署：本批后端文件和小程序 stream 文件 selective sync 到 `/root/deeptutor`；重建容器后运行时 env 显示 `LLM_BINDING=dashscope`、`LLM_MODEL=deepseek-v4-flash`、`LLM_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1`。
- Health: `https://test2.yousenjiaoyu.com/readyz` 返回 `ready=true`。
- Remote Node: 在阿里云 `node:22-slim` 容器内执行 `node wx_miniprogram/tests/test_ws_stream.js` 和 `node yousenwebview/tests/test_ws_stream_auth_refresh.js`，均 PASS。
- Public E2E: `scripts/run_mobile_login_smoke.py --api-base-url https://test2.yousenjiaoyu.com --register --username-prefix batchh --first-message '请只回复：登录入口回归第一轮。' --second-message '继续上一轮，请只回复：登录入口回归第二轮。' --timeout-seconds 180`
  - run_id: `mobile-login-smoke-1777133044`
  - result: `Passed: True`
  - conversation_id: `tb_e6dfda38335d4a0ab29c5177`
  - first assistant: `收到，登录入口回归第一轮。`
  - second assistant: `登录入口回归第二轮。`
  - cleanup: `deleted=true`
- Current public E2E recheck: `scripts/run_mobile_login_smoke.py --api-base-url https://test2.yousenjiaoyu.com --register --username-prefix batchhnow --first-message '请只回复：当前公网第一轮正常。' --second-message '继续上一轮，请只回复：当前公网第二轮正常。' --timeout-seconds 180`
  - generated_at: `2026-04-26 00:19:19`
  - run_id: `mobile-login-smoke-1777133959`
  - result: `Passed: True`
  - conversation_id: `tb_dfb2b701d8534b0092e236ed`
  - first assistant: `当前公网第一轮正常。`
  - second assistant: `当前公网第二轮正常。`
  - cleanup: `deleted=true`

WeChat DevTools simulator:

- 已在 `yousenwebview` 微信开发者工具进入中文鲁班智考聊天页，页面路径为 `packageDeeptutor/pages/chat/chat`，可见 `chenyh2008, 凌晨好`、今日焦点、中文输入提示和对话/历史/学情/我的 tab。
- 使用 Computer Use 对 textarea 输入中文时，DevTools 可访问性层不能稳定写入小程序 textarea；改用 Console 调用页面方法时，历史残留 debug 脚本把 `apiUrl/gatewayUrl` 改回 `http://127.0.0.1:8001` 并跳到 `packageDeeptutor/pages/report/report`，触发微信 request 合法域名错误。
- 因此本批不能把 DevTools 聊天发送链路声明为完整通过；真实服务器端到端已由公网 mobile-login smoke 闭环，DevTools 环境污染需要先清空控制台残留和本地 base fallback 后再复测。

剩余风险：

- 生产容器没有 `pytest`，远端 Python 单测未在服务容器内运行；云上验证以公网 HTTP/WS、容器 env、provider probe、remote Node tests 为准。
- #8 已覆盖 idle timeout 和用户停止的前端 authority 流，但真实慢请求手动点击停止仍需要在干净 DevTools 或真机里复测。
- 本批代码已同步到 `/root/deeptutor` 并 `docker cp` 进当前容器；正式发布时仍应从源码重新构建镜像，避免运行容器热拷贝和镜像内容产生漂移。
