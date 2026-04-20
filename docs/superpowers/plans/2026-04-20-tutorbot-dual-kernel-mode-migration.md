# TutorBot Dual-Kernel Mode Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `smart / fast / deep` 收敛成“双内核三模式”，让 `deep` 改为 TutorBot deep policy，并让独立 4-step deep runtime 退出产品主路径。

**Architecture:** 保留 `Fast Kernel` 与 `TutorBot Kernel` 两种执行内核；`Smart` 只做选择，不再是一套独立运行时。迁移先从模式定义、路由入口和评测脚本收口，再逐步缩减旧 deep runtime 的主路径调用面。

**Tech Stack:** Python, FastAPI, TutorBot runtime, AgenticChatPipeline, unified turn runtime, pytest, long dialog retest harness

---

## 文件结构

- `deeptutor/tutorbot/response_mode.py`
  - 单一模式 authority；补齐 `fast/deep/smart` 的 policy 定义与 Smart 选择结果表示
- `deeptutor/capabilities/chat.py`
  - 顶层 `chat` capability 只负责把模式映射到 `Fast Kernel` 或 `TutorBot/Deep policy`
- `deeptutor/agents/chat/agentic_pipeline.py`
  - 旧重型 chat pipeline 的收缩点；逐步退出产品主路径
- `deeptutor/services/session/turn_runtime.py`
  - 顶层 capability 选择与 trace 字段一致性
- `scripts/run_long_dialog_v1_retest.py`
  - 统一输出 TTFT + full-turn latency
- `tests/scripts/test_run_long_dialog_v1_retest.py`
  - 评测脚本 TTFT 报告红绿测试
- `tests/core/test_chat_capability_mode_selection.py`
  - 模式路由与 deep 收敛回归

## Task 1: 固化评测口径，TTFT 进入 ARR 报告

**Files:**
- Modify: `scripts/run_long_dialog_v1_retest.py`
- Test: `tests/scripts/test_run_long_dialog_v1_retest.py`

- [ ] **Step 1: 写 TTFT 报告红测**
- [ ] **Step 2: 跑红测，确认 `ttft_ms` 尚未产出**
- [ ] **Step 3: 在 turn/case/global 三层补 `ttft_ms / avg_ttft_ms / p50_ttft_ms / p90_ttft_ms`**
- [ ] **Step 4: 跑测试确认通过**

## Task 2: 把 Deep 从重型四阶段先收成三阶段

**Files:**
- Modify: `deeptutor/agents/chat/agentic_pipeline.py`
- Test: `tests/core/test_chat_capability_mode_selection.py`

- [ ] **Step 1: 写红测，锁定 `deep` 不再调用独立 `observing` 阶段**
- [ ] **Step 2: 跑红测，确认旧实现仍会触发 `observing`**
- [ ] **Step 3: 最小实现：`deep` 走 `thinking -> acting -> responding`**
- [ ] **Step 4: 跑 chat pipeline 定向回归**

## Task 3: 把 Smart 收窄成选择器，而不是第三套 runtime

**Files:**
- Modify: `deeptutor/tutorbot/response_mode.py`
- Modify: `deeptutor/capabilities/chat.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Test: `tests/services/test_tutorbot_response_mode.py`
- Test: `tests/core/test_chat_capability_mode_selection.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 1: 明确 Smart 只返回 `fast/deep` 选择结果，不再带自己的重链路语义**
- [ ] **Step 2: 让入口 trace 区分 `requested=smart` 与 `effective=fast/deep`**
- [ ] **Step 3: 跑模式与入口定向回归**

## Task 4: Deep 收回 TutorBot authority

**Files:**
- Modify: `deeptutor/capabilities/tutorbot.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Modify: `deeptutor/runtime/orchestrator.py`
- Test: `tests/core/test_capabilities_runtime.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 1: 盘点当前 still-on-path 的独立 deep runtime 入口**
- [ ] **Step 2: 让 `Deep` 顶层模式优先落到 TutorBot deep policy**
- [ ] **Step 3: 保留旧 deep capability 代码，但从产品主路径去主控权**
- [ ] **Step 4: 跑统一入口回归**

## Task 5: 用小样品证明模式分工成立

**Files:**
- Modify: `scripts/run_long_dialog_v1_retest.py`（如需补充摘要字段）
- Verify: `tmp/long_dialog_v1_retest_*`

- [ ] **Step 1: 选固定小样品 case**
  - `LD_003,LD_009,LD_010 --turn-mode focus`
- [ ] **Step 2: 跑 `smart / fast / deep` 三模式**
- [ ] **Step 3: 对比 `TTFT / avg latency / semantic / satisfaction / hard errors`**
- [ ] **Step 4: 判断是否满足目标分工**
  - `Fast`: TTFT 最优
  - `Deep`: 语义/正确性不低于 Smart
  - `Smart`: 综合体验最优

## Task 6: 文档与概念纪律收口

**Files:**
- Modify: `docs/superpowers/plans/2026-04-19-tutorbot-mode-policy-unified-authority.md`
- Modify: `AGENTS.md`（仅在确需写入 repo 规则时）

- [ ] **Step 1: 明确写出“双内核三模式”结论**
- [ ] **Step 2: 标注独立 4-step deep runtime 退出产品主路径**
- [ ] **Step 3: 保证文档中不再暗示三套顶层 runtime 并存**

## 小样品验收标准

- `Fast` 的 TTFT 不得高于 `Smart` 超过 15%
- `Deep` 的语义理解分应不低于 `Smart`
- `Deep` 的平均 latency 应显著低于本轮改造前的 deep 基线
- 三模式都不得在小样品中出现系统性 aborted case

## 当前状态

已完成的先行切口：

- `run_long_dialog_v1_retest.py` 已输出 TTFT
- `deep` 已先去掉独立 `observing` 阶段

后续应继续按本计划推进，而不是重新长出新的 runtime 分支。
