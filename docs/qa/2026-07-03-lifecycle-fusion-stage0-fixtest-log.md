# 生命周期融合改造 stage0 — fix-test 日志（2026-07-03）

> 分支 `feat/lifecycle-fusion-stage0`（基线 origin/main ed1068a6d）。
> 计划单一真值：`docs/plan/鲁班移动端提分闭环/2026-07-03-luban-proactive-learning-lifecycle-fusion-plan.md` v1.1。

## 1. 排障记录（问题 / 根因 / 失败尝试 / 修法 / 验证 / 教训）

### 1.1 member_console 测试 3+4 个失败（批次 1b 期间）
- **问题**：全量跑 member_console 出现 7 failed；先 3 个（sparse mastery 系列）、修后又见 4 个（home_dashboard_learning_projection 系列）。
- **根因（两类，逐一定位非猜测）**：
  - 3 个 sparse 系列 = **共享磁盘 store 跨测试污染**：suite 内其他测试经真实 LearnerStateService 往 repo 内 `data/user/learner_state/student_demo/MEMORY_EVENTS.jsonl` 写事件（14:24 时间戳、git 未跟踪坐实）；我的 §6-2 改动让 radar/mastery 面第一次读到该 store。单测重跑仍红是因为污染文件残留在磁盘。
  - 4 个 projection 系列 = **origin/main 基线既有红**：在干净 detached worktree（ed1068a6d）上复跑同文件同样 4 failed 同名——与本分支改动无关。
- **失败尝试**：无（先清污染文件复跑分离两类原因，未走弯路）。
- **修法**：3 个 sparse 测试补显式 `_EmptyLearnerStateService` fake（声明"无学习证据"口径，防 CI 同进程复发）；4 个基线红不动（非本分支病）。
- **验证**：`rm -rf data/user/learner_state` 后 3 个单跑 3 passed；补 fake 后全量 member_console+report = 313 passed + 恰好 4 个基线既有红。
- **教训**：读侧新增 learner-store 依赖时，凡不 mock learner service 的既有测试都变成隐性共享磁盘消费者；"单文件重跑仍红"不能立刻判真回归——磁盘残留也会让单跑红，要先清 store 再分离。

### 1.2 deep_question 5 个失败（批次 1a 期间）
- **问题**：跑 tests/core/test_deep_question_submission_grading.py 5 failed（missing canonical turn_semantic_decision）。
- **根因**：origin/main 基线既有红（干净 worktree 复跑同样 5 failed 同名）。
- **修法**：不修（非本分支范围）；如实登记。

### 1.3 题→pack 编译首版两处假绿（批次 1e 期间）
- **问题①**：首版报 1187 链接 / 0 unmatched——100% 命中可疑。
- **根因①**：题库 chunk_id **跨年不唯一**（2022/2023/2024 均有 `EXAM_1A411001_P0001_01`），裸 chunk_id 键跨年互相覆盖 + 假共享（140 个 ">2 packs" 大半是跨年同名碰撞）。
- **修法①**：条目一律 `year:chunk_id` 复合键；(year,anchor) 一对多合法化（2017 案例一拆 P0009_01+P0010_04 两 chunk，fail-fast 首版误判为数据损坏，实为案例分问拆分）。
- **问题②**：修①后仍 0 unmatched，但 evidence 题号形态枚举出 '参考答案'/'第N页'/'问题N-N' 等 29 种——矛盾。
- **根因②**：题库 anchor 与 evidence 题号**同源提取**（同 PDF 解析），奇葩形态双侧一致所以真命中；但 '问题1' 类弱锚同年命中**多个不同案例**的 chunk = 真歧义，静默全收会错配。
- **修法②**：三分桶——唯一命中/案例N 合法拆分 → linked；弱锚多命中 → ambiguous（653 条如实待教研）；零命中 → unmatched。最终 985 linked / 653 ambiguous / 0 unmatched。
- **教训**：0 unmatched 这类"完美结果"必须反向审计（枚举输入形态全集 vs 输出）；歧义与未匹配是两种病，都不许硬塞。

### 1.4 revalidation queue 断言键名假绿（批次 3 期间）
- **问题**：`test_revalidation_queue_emits_zero_probe...` 一次全绿。
- **根因**：断言了不存在的键（`queue["due"]`/`active_probe`）——对 dict.get 恒真。实际输出键是 `items`/`source_status`。
- **修法**：改断言真实键 `items == []` + `candidate_count == 0`，并加 **weak 态对照臂**（必须真产出 1 probe）防恒真。
- **教训**：断言"零/空"前先跑一个必然非空的对照输入，确认断言路径真的在测。

### 1.5 lesson-progress 路由 guard 两连拦（批次 2 期间，均为闸门正常工作）
- rest-route-allowlist-guard 拦：新挂载未登记 → 登记 `contracts/index.yaml` http_routes（两份镜像同步）后 passed。
- contract-guard 拦：protected 文件（home_personalization/learning_state_projection/api.main）改动需 domain 测试更新——新测试文件是 untracked，不在 `git diff --name-only` 里，须把 untracked 一并传给 guard；同时把新测试登记进 turn/learner_state domain test_files。

## 2. 与计划的偏差登记（全部如实）

1. **`home_learner_signals.py` 不在 origin/main**（只在 codex/jiagou 分支）——计划 §6-2 的"collapsed:false 翻真"与 §2.3 折扣2（首页 review 路径接 prescription_outcomes）落在该文件上，本分支无法执行。已做替代：mastery 收口主体照做（三面接 estimate_mastery）；review 可达性经 home_next_step 接线部分兑现。**待 owner**：codex/jiagou 的 home_learner_signals 合 main 后补这两个子项。
2. **批次 1b 口径**：证据窗（event_limit=20）内无 attempts 的章节保持 legacy 分不 cap——与报告页 `_mastery_v2`（零 attempts 也跑 estimate、legacy cap 60）不同口径。理由：小窗造成的假 insufficient 不应降级摸底测评契约（learner-state.md Assessment Read Model #4）。完全统一口径需把窗口拉齐 report（limit 200），列为 rollout 期决定。
3. **段内重排器不存在**（v3.2 §5.1 每晚重排未实现）——前置过滤落点改为学序现 runtime 消费者（home_next_step learn 臂 + graph 内 `order_packs_with_prerequisites` 可复用函数）；重排器落地时直接复用同一函数。
4. **§1.2 真懂态判据**：远迁移变体属性（R4）尚未进事件流，投影 fail-closed 以 `L2_real_retest` rank 为真懂门槛（L2_confirmed 人工确认停在练过）；远迁移接线后升级判据。
5. **批次 4 活跃练臂**：首页暂无 active_training_intents 干净读源（PCP 归 report 链路），接线处传空并注释——flag 通电前须补（列待 owner 决策）。
6. **1d 落点**：primary_taxonomy_ref 机器可读化落为独立编译产物 `_pack_taxonomy_registry.v0.json`（60 slot 全量）而非逐个改 40 份 IR——单一机器可读源 + 可重跑，registry md 仍是人读权威。

## 3. 基线既有失败清单（origin/main ed1068a6d 上复核过，非本分支引入）

- tests/core/test_deep_question_submission_grading.py：5 failed（canonical turn_semantic_decision 缺失系列）
- tests/services/member_console/test_home_dashboard_learning_projection.py：4 failed（canonical members/deictic topics 系列）

## 4. 最终域测试数字（2026-07-03 收尾）

- 组合套件（learner_state + member_console + assessment + taxonomy + rag hermetic 4 文件 + scripts 2 守护 + api 2 端点 + capabilities writeback）：**929 passed, 5 failed**（15:07）。
- 5 个失败全部在 tests/services/member_console/test_home_dashboard_learning_projection.py：
  - 4 个 = origin/main 基线既有红（干净 worktree 复核过，见 §3）。
  - 第 5 个（write_persists_only_canonical_projection）= suite 内全局状态隔离污染：该测试自带 fake learner state 完全自包含，单独跑 1 passed——符合"单独 PASS=污染非回归"铁律，非本分支引入路径。
- qa_ cohort TestClient 冒烟：未认证 401 ✅ / qa_ 写入 200 ✅ / 同日 dedupe 折叠（同 event_id）✅ / 非法 watched_stage 400 ✅。
- contract-guard passed；rest-route-allowlist passed（35 mounts）；env-registry-guard passed；schema-registry-guard passed；luban-animation-taxonomy-alignment passed（registry_rows=60）。
