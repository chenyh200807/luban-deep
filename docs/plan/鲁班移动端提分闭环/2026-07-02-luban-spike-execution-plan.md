# 最小双轮 spike 执行计划（阶段 1 留存实验本体）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development，步骤用 `- [ ]` 追踪。
> Status: **Ready-to-ignite，点火顺延**——owner 2026-07-02 拍板「五模块全量 IA 先行」（第 10 轮定稿，见 `artifacts/luban_five_module_design/`）：阶段 2 的 tabBar/IA 迁移闸由 owner 提前解除，spike 以五模块形态点火。本计划的四页 spike 壳升级为五模块中的对应屏，链路/埋点/红线不变。（P6 透明登记：与 v3.2 顶部落地闸的偏离系 owner P7 拍板，非工程自行放闸）
> Date: 2026-07-02 · 上位契约: [双轮设计 v3.2](2026-07-02-luban-learn-review-double-wheel-design.md) §12 阶段 1

**Goal:** 用已就绪件组装最小「学习×复习」双轮，对真实一建在职考生小样本跑 D1/D7 留存实验。

**Architecture:** 全链 thin 投影——manifest 绿灯(5 包)→lesson viewmodel(fail-closed)→小程序壳页+web-view 卡→native 交接时刻(订阅红点降级)→次日变体复测(75 池确定性抽取)→错因银行(既有判分链路投影)。零新 authority、零运行时生成。

**Tech Stack:** FastAPI read-model（`/api/v1/luban`）· 小程序 packageDeeptutor · Animation IR 静态卡（web/public/luban-preview）· surface telemetry（TurnEventLog/BI 既有通道）。

## Global Constraints（每个任务隐含）

- v3.2 §8：AI 只投影不生成；变体只从编译期池抽取；禁二次归因/AI 调度。
- §3：掌握态只由客观复测产生；spike 复测结果只进 telemetry 不写学情（M0 reality-lock）。
- 文案铁律：全程禁「看穿/识破/揭穿/检验/考验/露馅」，只用"帮你变强"基调。
- 阶段 2 内容（完整 SR 引擎/tabBar 迁移/40 站量产/会员深度层）一律不进本 spike。
- 部署仅 test2；生产变更=P7 硬闸。

---

## 已就绪件清单（核验数字随行，不重做）

| 件 | 状态 | 核验 |
|---|---|---|
| 签发包（内容弹药） | ✅ main 绿灯=5（S05/N01/J01/A01/C02） | `_pack_manifest.json` projection_green；#333/#337/#339 |
| lesson viewmodel + 投影门 | ✅ PR #341（E1+扩展） | 10 域测试 passed；route allowlist 34 registered |
| 讲懂卡+闯关页（5 包） | ✅ `web/public/luban-preview/{pack}/` | 63-77KB/卡、0 内嵌字体（11MB 事故不在此管线） |
| 变体池（次日复测弹药） | ✅ `_S05_variant_bank.v0.json` 75 个 | 一致性门 75/75=100%；retest 投影幂等/回绕已测 |
| 订阅消息（明天见钩子） | ✅ 代码侧四件+红点降级（7 tests） | 模板 ID 未到→红点形态跑（不阻塞） |
| 埋点通道 | ✅ surface telemetry→observability→BI | D15 事件清单见任务 3 |
| D1 基线 | ✅ 6.2%/4.6% 双口径（并行窗口实测） | 判据两案见点火包 |

**选站裁决（3 站，按弹药密度分层如实标注）：**
- **S05 临时用电**（旗舰全闭环站）：讲懂 65KB + 闯关 46KB 全量 + 75 变体池复测——唯一完整双轮站，D1 钩子主测站。
- **A01 检验批验收**（全量闯关站）：讲懂 65KB + 闯关 39KB 全量；无变体池（复测降级为普通回看）。
- **N01 网络计划**（讲懂站，owner 建议保留）：讲懂 63KB + 闯关薄（3KB 单题）；如实标注，不假装全量。

## Task 1: E2 客户端四页收尾核验（stations/station/handoff/retest）

**Files:** `yousenwebview/packageDeeptutor/pages/luban/*`（子代理产出）
**Interfaces:** Consumes E1 API 三端点；Produces 埋点事件（任务 3 清单）。

- [ ] Step 1: 主控逐文件审阅子代理 commit（文案铁律 grep：`grep -rn '看穿\|识破\|揭穿\|检验你\|考验\|露馅' yousenwebview/packageDeeptutor/pages/luban/` 期望 0 命中）
- [ ] Step 2: DevTools 编译零报错 + 四页可达（陈旧编译白屏须重启 DevTools——既有坑）
- [ ] Step 3: commit 已在 luban/lesson-adapter-e1 分支，随 PR #341 合入

## Task 2: 部署 test2（deeptutor-aliyun-release skill 全套）

- [ ] Step 1: PR #341 CI 全绿 → merge → `git show origin/main` 核实
- [ ] Step 2: 走 release skill（worktree 勿放 /private/tmp；build+sync）
- [ ] Step 3: 防假成功门：容器 just-now 创建 + **容器内** `grep -c build_retest_items /app/deeptutor/services/luban_lesson/read_model.py` ≥1 且镜像 SHA 对齐 release 标签
- [ ] Step 4: 公网烟测：`curl -s https://test2.yousenjiaoyu.com/luban-preview/s05/lesson.html -o /dev/null -w '%{size_download} %{time_total}'` 期望 <100KB；authed `GET /api/v1/luban/lessons` 返回 5 站

## Task 3: D15 埋点活体验证（无埋点=不可证伪，eval-design 红线）

事件清单（surface=wechat_yousenwebview，metadata 含 pack_id）：
`luban_station_enter` / `luban_practice_tier` / `luban_station_complete` / `luban_handoff_shown` / `luban_subscribe_result{status}` / `luban_retest_answer{variant_id,correct}` / `luban_retest_complete{total,correct_count}`

- [ ] Step 1: 真机走一轮后，服务端拉 surface event store 按 event_name 计数，逐事件 ≥1 贴真数字
- [ ] Step 2: BI/Prometheus `deeptutor_surface_event_total` 能见同批事件

## Task 4: 真机 true-entry 走通 ≥3 轮（memory 方法：automator+QA 账号）

- [ ] 每轮：stations→S05 station（讲懂→闯关）→handoff（红点降级路径）→（模拟次日：storage 改 due 日期或直接进 retest 页）→retest 5 题本地判分→错因银行页可见
- [ ] 3 轮全绿判据：零 JS 报错、埋点逐轮进店、复测题面跨"日"轮换生效

## Task 5: 静态样张人眼核清单（owner/教研过目后才对外）

- [ ] 三站讲懂卡真机截图：排版无溢出、字体回退可读、动画流畅
- [ ] 交接时刻文案过暖色铁律（逐句读）
- [ ] retest 反馈语（"对——你是真懂了"/"再看一眼就稳了"）过铁律
- [ ] S05 闯关页 52 选项抽 10 个核内容正确性（对照 pack 🟢 层）

## 度量与通过判据（预登记防挪门柱，具体阈值=P7 owner 拍板）

- 主指标：**D1 次日回访率**（基线两案：绝对底线 6.2%/4.6% 双口径 vs spike 首周自身）；辅助：变体复测完成率、交接曝光→订阅授权率（红点形态则记曝光→次日主动回访）、站完成率、档位分布。
- 全部由 D15 埋点派生，不可编造；样本：真实一建在职考生小样本（招募方式归 owner）。

## 非目标（刻意不做）

评分进学情、完整 SR 多跳阶梯、tabBar 迁移、40 站量产、会员计费改动、N01/C02/J01 变体池补产（产能报告已证可行，等 spike 数据再投）。
