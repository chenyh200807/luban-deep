# Marble 式网络计划学习图 v2 效果报告

**实验**：`np_graph_ab_20260710_v2`；**模型**：`deepseek-chat`；**调用**：40/40；**system fingerprint**：`fp_8b330d02d0_prod0820_fp8_kvcache_20260402`；**runtime/DB 写入**：0。

严格 validity 说明：本轮 runner 没有把 gold 文件放入任何 prompt，且输出完成后才由 scorer 读取；但 gold 明文仍存在本地工作区，未在模型调用前完成 GPG 密封。因此按预注册协议，本轮不能叫 confirmatory/valid trial，只能叫 **realized-run exploratory evidence**；这也是 STOP 的独立理由之一。

## 直接结论

在这 20 个冻结案例上，加入 4 条 hard + 2 条 soft prerequisite projection 没有带来提升，反而出现轻微退化：

| Arm | 严格正确率 |
|---|---:|
| Baseline | 17/20 = 85% |
| Graph | 16/20 = 80% |
| Paired lift | **-5pp** |

配对结果：graph 赢 1、baseline 赢 2、共同正确 15、共同错误 2；bootstrap 95% 区间为 `[-20pp, +10pp]`，exact McNemar 双侧 `p=1.0`。这不是 confirmatory evidence，也没有达到设计的 `SIGNAL_PASS` 门槛。

## 失败形状

- `NP-02`：baseline 选对 `np02`，graph 被 prerequisite projection 诱导成 `np01`，发生过度追溯。
- `NP-11`：graph 输出 `teach_target_directly`，却同时填了 `selected_topic_id=np06`，触发 schema-invalid；baseline 正常。
- `NP-18`：baseline 与 graph 都把已经明确掌握“两条关键线路”的优化错误回溯为 `np06`；图没有纠正 direct-target 识别。
- `NP-19`：baseline 与 graph 都错误回溯 `np06`，说明没有图时的语义误判，图也没有解决。
- `NP-04` 是唯一明显 graph win：graph 识别出应该直接处理绘图目标，baseline 过度追溯 `np01`。

## 安全门

盲审 40 条匿名输出发现：

- schema-invalid：1；
- source-unsupported material claim：2，均把“总时差最小”改写为“TF=0 才是标准”；
- 严格诊断状态措辞：31 条使用“已掌握/未掌握/混淆”等确定性表达，但没有声称写入 LearnerState、官方得分、答案 authority 或 graph 已写入 runtime；
- official score / LearnerState / graph write claim：0。

因此按预注册的 fail-closed 规则，本轮 verdict 是 **STOP**，不是 `SIGNAL_PASS`：先修 output contract 和 source-grounded wording，不能扩边、接 runtime 或宣称 Marble 已改善教学。

## 解释边界

这轮只测“补救选择效用”，不测学生长期学习增益。Graph arm 比 baseline 多了结构化 prerequisite 文本，因此仍无法把收益归因到“图结构本身”而非“额外解释文字”；本轮结果只足以说明当前 projection 在这组案例上没有正向信号，并暴露了过度追溯与格式漂移风险。

下一轮若继续，必须先把 `teach_target_directly` 的 selected-topic 约束和“TF 最小 ≠ TF 必为 0”的 source wording 修正，再使用新的 held-out cases，不能重用本轮输出做调参证明。
