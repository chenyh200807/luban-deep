# 06 · 七确定性判分引擎 / Codex 异源对抗核修 26 真 bug

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §1限制①④。分支 `feat/luban-case-light-practice-p-1`。

**铁律**:计算/集合/CPM/DAG-ECF 判分**绝不走 LLM**;每个评分引擎用**真题金标**验(算出的==官方答案,非 self-test);每个派 **Codex 异源对抗核算法**(`codex-rescue`),它挑的 bug 治本修到绿。**算错=判分错=误判学员**,所以对抗核是唯一防线。

## 引擎清单

| 引擎 | 文件 | 金标 | Codex 核 |
|---|---|---|---|
| **C1 CPM**(关键线路/总时差) | `case_cpm_solver.py` `bb85b964a` | N01 网络逐工序 ES/EF/LS/LF/TF/FF 全对 rendered SVG;{2015} 型两条并列关键线路 T=25 | 修 1 bug:`_EPS=1e-9` 绝对容差把 TF≈5e-10 真非关键误判为关键 → 治本=**强制工期整数** + 精确 `tf==0`,源头除浮点歧义 |
| **C2 合取门**(找错∧改正) | `case_flaw_correction.py` `0d3950590` | 泛水判断改正型 | 修 4 bug(见下) |
| **C3 DAG+ECF**(计算图+误差传递) | `case_calc_dag.py` `bf7a23b1a` | 编译库 P0016_02 造价 6 步链官方值全对;ECF 上游错下游自洽给分 | 修 7 bug(见下) |
| **荷载组合**(集合精确匹配) | `case_load_combination.py` `b85aa2e2c` | 编译库 P0009_01 | 修 5 bug(dict 输入判满分/duck-typed 绕过/零宽/空 bin 等) |
| **工序排序**(拓扑序校验紧前) | `case_process_ordering.py` `8468c3a67` | 编译库 P0010_02 工艺流程 | Codex 修(环检测+零宽归一+None 守卫,`c3df7e1ed`) |
| **C4 拍照诊断**(读图↔判分解耦,非评分) | `case_photo_diagnosis.py` `5b283fecd` | 真 F16 采分点 + 模拟 OCR 误差 | 修 3 bug(required 全需/否定守卫/最高置信 span,`b71ffddcd`) |
| **C5 认→写阶梯**(铁律门,非评分) | `case_recognition_to_writing.py` `0602dade3` | — | 修 3 红线 bug(裸 int tier 绕铁律→`_require_tier`;`next_tier` 防跳档,`557341d87`) |

## C2 合取门 4 bug(记为通用教训)
① 跨题/跨小问 pair 绕过校验拿满分 → 校验同 qid/sub_qid/sub_no;② `score_conjunction_group` 跨题**同名组全局合并**把一题分拖成 0 → group key 按 `(qid, sub_qid, group)` **作用域**(⚠️**合取/组判分必须按题作用域,别用全局字符串 key**);③ 重复 point_id 一次命中满足两成员 → 输入去重 fail-closed;④ 负 max_score 满答得负分 → 构造期拒绝。

## C3 DAG+ECF 7 bug
① ECF 缺上游回落官方值(学员只填下游官方值拿分)→ 缺/非数字上游判错决不回落;② 未按上游 rounding 传播 → 按其步 rounding 归一;③ formula 引用未声明 step → 名一致性 fail-closed;④ inf/nan tolerance 拒;⑤ role 传字符串账目错分 → 必须 `CalcRole` 实例;⑥ 非数字学生值崩溃 → 判错不崩;⑦ 除零/溢出/Pow DoS/深表达式 → `CalcError`。安全 AST 求值(禁 eval/调用/属性/Pow,界深度)。schema `luban_case_calc_step.v1` 注册 T2 PINNED(闭包 214)。

## 汇总
**7 引擎 · Codex 异源对抗核共揪治本修 26 个会误判学员的真 bug**(CPM1/合取门4/DAG+ECF7/荷载5/排序 + 拍照3/认→写3/后续)。全套 case 测试 130 passed,闭包 CLOSED 215,`contract_guard --base origin/main` 全绿。
