# 双轮 spike 体验版上传 checklist（main2 小程序 → 微信体验版）

> 把 main2 worktree 的小程序（学习×复习双轮 + card-fit UI）经微信开发者工具（DevTools）上传到**体验版**的 step-by-step。
> Date: 2026-07-07 · 上位契约：双轮设计 v3.2 §12 阶段 1 · 配套：[GO 阈值预登记](2026-07-07-luban-spike-go-threshold-preregistration.md)、[spike 执行计划](2026-07-02-luban-spike-execution-plan.md)
>
> **边界铁律（先读，防误判「上线了」）**：DevTools 上传体验版 ≠ 后端已部署。见 §4。

---

## 0. 前置事实（点开工具前先核对）

- **DevTools 项目根 = `yousenwebview`**，不是 `packageDeeptutor`。`packageDeeptutor` 是分包（`app.json:21` `"root": "packageDeeptutor"`），单独打开分包目录会导致路由/分包解析错乱。**打开的必须是 `yousenwebview/` 这一层**（含 `app.json` 的目录）。
- 双轮相关页均在 `packageDeeptutor` 分包下（`app.json:40-47`）：`pages/luban/{stations,review,station,handoff,retest,concept-cards,errorbank,gauntlet}`。
- 当前分支 = `release/card-fit`（main2 worktree）。上传前确认 worktree 是要发的那份代码。

---

## 1. 清陈旧编译缓存（**必做，逐字执行**）

> 已知坑（memory `wechat-devtools-stale-cache-and-automator-ground-truth`）：DevTools 的 **188M `WeappCache` 跨重启复用**，改了代码看不见 / 体验版仍是旧版白屏，根因就是它。清它才生效。**改动后如果页面没变、白屏、或明明改了却看不到，先做本节再排查别的。**

步骤（逐字）：

1. **退出 DevTools**（完全退出，不是关窗口）。
2. 删除该项目的三个编译缓存目录：
   ```bash
   rm -rf <项目hash>/{WeappCache,Weappdest,WeappMiniCode}
   ```
   `<项目hash>` = DevTools 为 `yousenwebview` 项目分配的缓存目录（在 DevTools 用户数据目录下，按项目路径哈希命名）。
3. **重开 DevTools**，重新打开 `yousenwebview` 项目，等其**全量重新编译**（首次会比平时慢，属正常——正是因为缓存被清）。

---

## 2. 上传前 flag / 入口核对

### 2.1 需要打开的 flag（后端侧，env）

| flag | 作用 | 本轮 spike 状态 |
|---|---|---|
| `LUBAN_REVIEW_MODULE_ENABLED` | 复习轮：`postStationCompleted` 到期调度、次日复习到期清单。**关时服务端拒收（400），交接/复测的次日到期信号静默丢失** | **必须 ON**（`env_registry.yaml:134`，默认 false；出处 `handoff.js:47-53`、`retest.js:164-165`） |
| `doubleWheelLandingEnabled`（前端 flag，非后端 env） | Task C 入口收权:登录后落地由问鲁班(chat)翻到学习双轮(learn)。默认关=host 逐字节不变 | **spike cohort 需 ON**。这是**前端** flag（`flags.js` DEFAULT_FLAGS，`login.js:_reLaunchAfterAuth` 单一收口），经 **host 运行时 flags**（`hostRuntime.getWorkspaceFlags()`）下发，不在后端 `env_registry.yaml`。关时走既有入口(落 chat)；开时仅翻 chat→learn、不动其它深链。上传前确认 host 已对 spike cohort 下发该 flag=true |
| `WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST` | 次日复测订阅模板 ID | 未配置 → 订阅降级红点（`service.py:84-85`）。**不阻塞上传**，但订阅授权率读不出（见 GO 预登记 §4 G4） |

> flag 的**实际生效**是后端部署侧的事（Aliyun 里程碑），不是 DevTools 能验的（见 §4）。此处只登记「体验版行为要对，后端必须已 ON 这些 flag」。

### 2.2 双轮入口路径（真机 smoke 走这条）

学习 tab（`pages/learn/learn.js`）为双轮入口：
- 今日任务 = `light_practice` → `retest` 页 **forward** 模式：`/packageDeeptutor/pages/luban/retest/retest?pack_id=<pack>&mode=forward`（`learn.js:173-181`）。
- 下一站卡 → 站点页：`/packageDeeptutor/pages/luban/station/station?pack_id=<pack>`（`learn.js:145-155`）。
- 完整路线 → `pages/luban/stations/stations`（`learn.js:159-160`）。
- 复习到期条 → 复习页 `route.lubanReview()`（`learn.js:164-165`）。

### 2.3 上传前编译核对

- [ ] DevTools 编译**零报错**（陈旧编译白屏须先做 §1 重启）。
- [ ] 文案铁律 grep（0 命中）：
  ```bash
  grep -rn '看穿\|识破\|揭穿\|检验你\|考验\|露馅' yousenwebview/packageDeeptutor/pages/luban/
  ```
- [ ] 双轮八页均可达（`app.json:40-47` 列的分包页）。

---

## 3. 冒烟清单（体验版真机走一轮，学习 tab 为起点）

按双轮闭环顺序，逐步核「不白屏、无 JS 报错、埋点进店」：

1. [ ] **学习 tab → 今日任务**：今日任务卡渲染（`learn.js` todayTask）。
2. [ ] **2 分钟轻练（forward）**：点今日任务 `light_practice` → `retest?mode=forward`；5 题本地判分（选择==expected_ok，`retest.js:116-137`）；每题发 `retest_item_answered{practice_mode:forward}`，完成发 `learning_action_completed{object_type:retest, practice_mode:forward}`（`retest.js:169-176`）。
3. [ ] **讲懂 → 闯关站**：下一站卡 → `station?pack_id=<pack>`（两幕 web-view 卡）。
4. [ ] **交接时刻**：`handoff` 页曝光发 `handoff_rendered`（`handoff.js:55-60`）；点「明天提醒我」→ `subscribe_prompt_result{result:granted|red_dot}`（`handoff.js:84-90`，模板未配置时应为 red_dot 页内提示、不弹窗不重试）。
5. [ ] **次日换皮复测（review）**：模拟次日（改本地 `luban_retest_due_<pack>` / storage 或直进 retest 页）→ `retest?mode=review`；发 `retest_item_answered{practice_mode:review}` + 完成 `learning_action_completed{practice_mode:review}`——**这条 review 事件就是 GO 主信号 G1 的来源**。
6. [ ] **错因银行**：交接页「错因银行」入口 → `errorbank` 可见复测销账（`handoff.js:103-107`）。

> 埋点活体核验：真机走完后，服务端按 `event_name` + `practice_mode` 拉 `product_behavior_events` 计数，逐事件 ≥1 贴真数字（口径见 GO 预登记 §2）。**practice_mode 必须能把 forward / review 分开**——分不开则 D1 留存读不出。

---

## 4. 诚实边界（防「上传=上线」误判）

1. **DevTools 上传体验版 ≠ 后端已部署**。体验版只换了小程序前端包；后端 read-model / flag 生效 = **Aliyun 里程碑**（走 `deeptutor-aliyun-release` skill：build+sync、容器内 grep 核 SHA、公网烟测），不是 DevTools 能确认的。§2.1 的 flag ON 状态必须在后端侧单独验证。
2. **后端 flag-on 验证 = Aliyun 里程碑**，不是本 checklist 的范围。体验版真机看到「行为对」不等于生产后端已 ON `LUBAN_REVIEW_MODULE_ENABLED`——两者要分别验。
3. **真机留存要 cohort + 天数流逝**。D1/D7 GO 信号需要真实用户 cohort 招募（归 owner）+ 日历推进 ≥7 天（GO 预登记 §1）。上传当天 = 0 数据，读不出成败。
4. **DevTools ≠ 真机 ≠ 部署**：三者独立。DevTools 预览、体验版真机、生产部署各自验证，任一绿不代表另两者绿（memory `wechat-devtools-stale-cache`）。
