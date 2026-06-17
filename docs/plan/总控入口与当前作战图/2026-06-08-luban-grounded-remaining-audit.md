# 鲁班 "全部完成" 接地气真实剩余审计（2026-06-08）

> **方法**：逐条把计划声称的 gap 对照**代码 + 测试 + artifacts** 核实（不信过时文本）。每项标【已建待激活】/【部分建成】/【真未建/缺代码】/【缺外部依赖】+ 证据。三路并行审计 + B#6/B#7/M32 已单独核实。
>
> **总结论**：**代码远比计划文本靠前。** 早先基于计划文本列的"剩余工程"大半已建成，只是 gated 关闭。真正剩下的 = ①一批**激活授权决策**（代码已建，差你拍板）②两个**小代码缺口**（publish 函数 / canonical 生产 override）③**D 类长期分析**（真正未建的自主工程）④**G2/G4 的外部依赖**（教师/eval infra/key，我造不出）。

## A. 已核实"其实已完成/已建待激活"（早先误列为缺口）

| 项 | 早先以为 | 真实状态 | 证据 |
|---|---|---|---|
| B#6 开放世界接 live WS followup | 未接入 | ✅ **已建+测试**（M27） | `deep_question.py::_attach_open_world_diagnostic`(4095) 流式下发；`test_luban_m27_open_world_ws_integration.py` 2/2 过 |
| B#7 governed objective 接 runtime | 仍 formative | ✅ **已建+测试**（M31），release-truth 就绪，默认 gated | `_maybe_attach_m31_governed_objective`；`test_luban_m31_governed_objective_ws.py`（cohort 命中=release_truth、非 cohort 拦） |
| C#9 full compiler→sign→runtime 闭环 | 未产品化 | ✅ **已建待激活** | `full_knowledge_compiler.py`(M30, 4 lane) + `objective_runtime_adapter.py`(M31) + `run_luban_full_knowledge_compiler_m30.py`；production flip NO-GO(授权) |
| C#10 questions_bank 全量签名 | 抽样 600/2659 | ✅ **已全量签 2640/2655**（14 rejected+1 conflict），bundle 已持久化 | M30 manifest + `v3_objective_records_released_m31/...json`(2.6MB)；"未持久化"是 M31.12 虚警，M31.13 已纠 |
| C#11 source-backed 采分点 ≥50 | 仅 ~23 | ✅ **70 > 50 已超目标** | M30 case_rubric：textbook 23 + logic 30 + calc 3 + list 14 = 70 |

> **含义**：C 类（编译/签名）**基本全部建成**，不是自主工程缺口；剩的是"激活"（A 类授权）。

## B. A 类生产/canonical 激活门（逐门真实判定）

| 门 | 代码 | 默认 | 翻开关机制 | 缺什么 |
|---|---|---|---|---|
| G1 limited default(qa_/operator_) | ✅ 已建 | test2 **已激活**(本轮) | `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED` | — 已做 |
| B#7/M31 governed objective cohort | ✅ 已建 | gated(flag+cohort) | flag + `LUBAN_M31_GOVERNED_OBJECTIVE_COHORT` | **缺授权** |
| G2 broad default(全量真实学员) | ✅ 已建(代码路径完整) | OFF | 扩 cohort / 去限制 | **缺授权 + 缺外部**(准确率 eval infra、GPT5.5 key) |
| G3 published registry | ❌ **缺代码** | 仅 release_candidate/canary | 无 publish 流程 | **缺一个 `publish()` 小代码**(release_gate 只到 canary，无 published=true 签发) |
| G4 canonical learner-truth write | 🟡 已建但生产硬挡 | 生产 dry-run | `service.py::write_compiled_learning_truth` 被 `is_production_environment()` 挡 | **缺生产 override 代码 + 缺外部**(teacher-final/real-retest 证据链) |
| G5 远端/Aliyun 写 | ✅ 已建 | 就绪 | `redeploy_aliyun_fast.sh`/`sync_to_aliyun.sh`(§3.7 护栏) | **缺运维授权 + 目标确认**(test2/prod) |

## C. D 类长期分析（真正剩下的自主工程）

| 项 | 状态 | 证据 / 缺口 |
|---|---|---|
| 时间衰减/遗忘曲线 | 🟡 **部分建成** | `mastery_estimator.py` 有 DECAY_PROFILES + 指数 forgetting_risk（单知识点）；缺跨周期学生画像衰减 |
| 复测变化曲线 | 🟡 **部分建成** | `revalidation_queue.py` 单次复测调度；缺多次复测趋势投影 |
| 错因稳定性(时间序列) | ❌ **真未建** | 仅 `(concept,error_code)` ≥2 计数；无 occurrence_timeline/重现间隔分析 |
| 学生可见长期报告 | ❌ **真未建** | `learning_report_read_model.py`(2640行) 全是最近 N 快照；0 处 trend/evolution；无学生端长期趋势页 |

## D. 修正后的"全部完成"路线图

```
【已完成】 M5-M32 底座 + B#6(M27) + B#7(M31) + C 类编译/签名(M30/M31) + G1(test2)
【我能自主做(真未建工程)】
  D 类: 错因时间序列 + 学生可见长期报告(真未建) → 时间衰减/复测曲线(补全)
  A 类小代码: G3 publish() 函数 + G4 生产 override flag(代码层, 默认仍关)
【需你授权(代码已建, 翻开关)】
  B#7 governed cohort 启用 / G2 broad default / G5 远端 prod 部署 / G3 实际 publish / G4 实际 canonical write
【需外部依赖(我造不出)】
  G2: 大样本准确率 eval infra + ground-truth 标注 + GPT5.5 key
  G4: 真实人类教师终审 / 真实学员跨时间复测证据
```

## E. 诚实底线

- **"全部完成"≠ 我一个人写完代码**：大半已建（待你授权激活），真未建的自主工程集中在 **D 类长期分析** + 两个 A 类小代码（publish/override）。
- **G2/G4 的最终翻转有硬外部依赖**（教师、eval infra、API key），不是工程能补齐的——这是对真实学员负责的必然门槛。
- **建议下一步自主工程**：D 类"学生可见长期报告 + 错因时间序列"——真未建、用户可感知、不依赖外部、可独立验证；或 G3 `publish()` 小代码（让 published registry 从"缺代码"变"待授权"）。
