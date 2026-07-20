# 公开练习页服务端判分收权 · 设计说明（2026-07-20）

> 战役：根治鲁班公开练习页答案键泄露——判分从客户端收权到服务端唯一权威。
> 分支：`feat/luban-practice-server-grading-seam`（基于 origin/main e30b19ab4）。

## 1. 病灶与根因（root-cause frame 摘要）

- **一等业务事实**：学员在公开练习页一次作答的判定结果（对错 + 逐项解析 + 学习证据）。
- **唯一权威**：`RetestWritebackService.complete()`（服务端按签发 sidecar 重判）。
- **争夺者（修复前）**：42/43 公开页内嵌 `ok:true/tempt/lose/fix/model` 答案键、
  43/43 页 ask-AI payload 用 `keycard` 携带 model answer、11 页 `q.opts[s].ok`
  客户端判分——查看源码即得全部答案，且构成事实上的第二 grader。
- **first wrong point**：`transform_compiled_practice_html` 把源题块逐字节嵌回公开页。
- **修法（先收权再补逻辑）**：删客户端答案数据面与本地判分路径，复用既有 seam；
  不新建第二 grader、不加平行端点协议。

## 2. 方案（Codex 方案 A 为主，B 保留为小程序环境首选路径）

### 2.1 嵌入数据 = 零答案键安全投影（发布器内核）

- `_sanitize_practice_block`：源题块按**字段分级重建**——
  - 答案字段 `{model, c, ana}` 与选项内 `{ok/ok2/code/tempt/lose/fix}` 一律不落公开页；
  - 选项数组直接从签发 authority item 的 `options[].text` 重建（与服务端判分同一行、同一序，单一真相）；
  - 呈现字段（`tag/typeHint/stem/fig*/sheet/diag/dep/...` 白名单）逐字保留；
  - **未分级新字段 fail-closed 拒发布**（register-before-embed），未来新增字段必须显式分类，杜绝静默把答案带回公开页；
  - a02（bank 格式）`ana` 特殊处理：渲染路径读 `cur.ana[actual]`，保形状清内容（等长空对象数组）。
- 母版作者注释里的答案键示例（`ok:true` 教学注释）发布时整块移除。
- 发布自检：`_PRACTICE_PUBLIC_LEAK_PATTERNS` 在 transform 末尾兜底扫描，命中即
  `practice_publish_answer_leak:*` 拒发布；独立副本 tripwire 在
  `tests/scripts/test_luban_practice_public_no_answer_key.py`（CI 门）。

### 2.2 播放器母版（统一注入桥 v2）

- `renderVals` 改名 `__dtBaseRenderVals` 后由注入包裹：提交前按钮语义改为
  「下一题 / 交卷 · 看服务端判分」；**提交前 UI 无任何可判对错信息**。
- `submit()` 覆写为「记录本题作答 → 前进」；本地逐题揭底（`sub/revealed`）永不触发。
- `setState` 拦截 `finished:true / phase:'result'`：本地结算屏被降权删除，任何
  终局路径都汇入 `__dtSubmitRound`（fail-closed：公开页不存在本地结果渲染）。
- `__dtSubmitRound`：小程序环境优先 `__dtRedirectEvidence` 走既有认证 retest 流
  （方案 B 原路径，零改动）；否则 `__dtServerSubmit` POST 交卷。
- `__dtOverlayResult`：判定 + 逐项解析（selected/correct option、采分句、
  诱因/丢分点/怎么改）**全部渲染服务端返回**，页面自身无真值。
- 失败态友好且禁假成功：网络失败/5xx → 「重试判分」（同一 `completionId` 幂等重放，
  不重复计分）；401 → 身份过期回小程序；无票且不在小程序 → fail-closed 提示。
- ask-AI（问追AI 带题目）：只带题面（题干/选项/我的选择），`keycard` 与
  正确答案拼装逻辑从发布器 ask 方法整体移除。

### 2.3 API：`POST /api/v1/luban-preview/practice-submit`（薄适配器）

鉴权/归一化/转发三件事，零判分零证据语义：

1. `contextId` → `_resolve_published_card`（只认已发布 card-hosted pack，fail-closed）；
2. `entryTicket` → `resolve_luban_card_entry_ticket`（站点签发短时 capability，绑 learner+pack；无票 401）；
3. `projectionReceipt` → `build_retest_items(mode=forward, projection_receipt=...)`
   （receipt 精确解析到当前签发 artifact，题集身份唯一权威）；
4. 服务端自算 `day_index`（UTC+8，客户端不自算）、自签 `issue_retest_selection`
   （同请求内签发即消费，客户端拿不到第二判分入口）；
5. `complete(completion_id="h5:"+clientId, ...)` —— 判分与全部 learning-evidence
   append 只发生在这一个 seam；响应原样返回（含 score/items/feedback）。

错误映射：409 `{"error":"content_updated_retake"}`、409 `{"error":"practice_not_released"}`
（含灰度旗标关——诚实「未开放」而非伪装数据漂移）、400 `practice_submit_answer_set_mismatch`、
409 冲突/进行中、401 身份过期。rate limit：`luban_preview_practice_submit` 10 次/60s。
契约登记：`contracts/index.yaml` 与 `deeptutor/contracts/index.yaml` 双拷贝同步
（prefix reason 更新 + 新测试注册进 learner_state domain test_files）。

## 3. 在途会话 `content_updated_retake` 语义梳理（验收 ⑤）

**receipt 是「客户所见题集」的身份输入，不是资格真相。** 资格真相始终在当前签发
artifact 的 eligible/non-revoked 集合。

- **正常轮**：页面 bake 时嵌入 receipt R1；交卷时 `resolve_projection_receipt`
  与当前 `surface.projection_receipt` 逐字节比对一致 → 按 R1 的题集判分。
- **在途换发**：学员加载页面（R1）后、交卷前，该 pack 重签/重发布（receipt 变 R2，
  或题目被撤销/资格变化）→ 交卷时精确比对失败 → 409 `content_updated_retake` →
  播放器渲染「题目内容已更新，请刷新重做」并整卷重取（刷新拿到 R2 新页）。
  服务端**绝不按 index 重映射、绝不静默换题**——旧题集上的作答不能被翻译成新题集的证据。
- **与 `practice_not_released` 的分界**：供给未签发/灰度未开是「练习还没上线」
  （教研节奏问题），独立错误码 + 暖文案；绝不洗白成「题目已更新请重做」误导用户。
- **幂等重放窗口**：同一 `completionId`（服务端命名空间 `h5:` 前缀）+ 同一答卷重试
  返回同一判定（terminal hash = `{selection_id, answers}`），不重复计分；已 terminal
  的 completion 在其后发生换发时仍可重放历史判定（证据不可变），只有**新**提交被
  fail-closed 拦截。
- **跨午夜边界**：`day_index` 服务端按 UTC+8 日历日折算；未 terminal 的轮次跨午夜
  重试会生成不同 selection → 幂等哈希不一致 → 409 冲突 → 引导整卷重练。与小程序
  retest 流同构，接受（罕见边界，宁可重练不可错记）。

## 4. Deviations（保守选择，供主控收录 implementation-notes）

1. **公开页逐题即时反馈移除**：零答案键约束下，逐题本地揭底不可能不带真值；
   逐题服务端判分会造第二 grader 或 5 次半程 completion。选择整轮交卷后一次性
   渲染服务端逐项解析（与小程序 retest 语义同构）。
2. **selection 在同请求内自签自验**：不给 H5 增开两步 issue/complete 往返；
   `complete()` 的 selection 校验合同零改动。
3. **completion 命名空间**：服务端强制 `h5:` 前缀，隔离小程序 completion id 空间。
4. **bank 格式选项序**：`c` 字段移除后 a02 `start()` 的「正确项避开首位」随机交换
   自然失效，选项呈现序 = 源序 = 证据映射序（此前该交换与 optPerm 缺失存在潜在
   映射错位，收权后消除）。
5. **作者注释含答案键示例**：发布时整块移除注释而非改 43 份源（源是 authoring
   authority，不属于本战役改造面）。

## 5. 验收证据（2026-07-20 本 worktree）

- 门 ①：`tests/scripts/test_luban_practice_public_no_answer_key.py` 3 passed
  （43 页零 `ok:true`/`keycard`/答案字段字面量 + 服务端桥全在场）。
- 门 ②：`tests/api/test_luban_preview_practice_submit.py` 7 passed（N01 真签发
  supply 走真 `complete()`：3/5 判分、canonical `error_events` 形状、幂等重放、
  401/409/400 映射）；`tests/services/luban_lesson/test_practice_html.py` 25 passed
  （sanitizer 单测 + 全量公开页投影断言）。
- 门 ③：`tests/api + tests/scripts/test_publish_luban_preview_cards.py +
  tests/services/luban_lesson + tests/services/learner_state` 共 1882 passed；
  `scripts/check_contract_guard.py` exit 0；`check_rest_route_allowlist` passed；
  `publish --practice-only --check` exit 0。
- 门 ④：`scan_luban_practice_option_defects.py` 全量前后一致
  （641 items，correct_index 分布 {0:161,1:158,2:161,3:161}，源语料未动）。
- 补充：43/43 页 `node --check` 语法通过；Node 行为冒烟（a01/a02/s07/s01p3 三种
  格式）整轮作答无本地揭底、无本地终局、POST 5 答案 + receipt + completionId。
- live 端到端验证留主控集成后执行（本 worktree 无服务端）。
