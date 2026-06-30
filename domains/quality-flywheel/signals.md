# Signals · quality-flywheel

> shared-brain signals 层。charter = `domains/quality-flywheel/README.md`。
> bug 模式的**去重 + 频次**视图。源（single authority）=
> `agent-skills/tutorbot-student-army-eval-loop/SKILL.md §7 模式库`（逐条带状态）。
> 本文件把 §7 的同病异形**按根因家族归并**，加 `复发次数`（live 复现/独立出现计数）
> 与 `domain` 标签，用频次驱动**边际杠杆排序**——频次高 + 未根治的家族优先治本，
> 频次高 + 已根治的留作回归清单（防复发）。
>
> 维护：每次 eval / fix 后，先回写 skill §7（症状/根因/落点/状态一行），再回此处更新
> 对应家族的 `复发次数` 与 `状态`。不在此处新增第二份 bug 台账。

## 家族级 signals（频次驱动优先级）

频次口径 = §7 中该根因家族下「live 复现 / 独立新形态」标记的累计条目数（结构信号，
非满意度均值）。`映射维度`=该家族对应 `accuracy_gate` 的哪一维。

| # | 信号（根因家族） | 映射维度 | 复发次数 | 当前状态 | domain |
|---|---|---|---|---|---|
| S1 | **判分对象 / 提交态 authority 失守**（凭空判分、串到别题、自造题成判分对象、质疑轮误触阅卷、no-evidence 编造学情） | sev_regression / forward_liveness / content_truth | 9+ | 多数本地 TDD+contract 已修，部分 live 待复验；提交态收口 #212 live GO，残 whack-a-mole | quality-flywheel |
| S2 | **回指 / active-object 承接**（"刚才那题"串别题、编造作答记录、stale active object 未降级、invalid 选项 follow-up） | huizhi / forward_liveness | 7+ | 多条本地 TDD+contract 已修 live 待复验；回指 SEV-1 仍是强收口红线 | quality-flywheel |
| S3 | **倒诬 / 判分用题库字母非当前题面**（选项重排判分倒诬学生） | daowu / sev_regression | 2 | M4(i) PR#286 确定性 canonical re-present 根治，live 验持久化终态 | quality-flywheel |
| S4 | **未答隐式求助 / 出题答案泄露**（隐式求助 fall-through 自由 LLM 推答案、显式"先别告诉答案"仍泄、A-E 越权出题） | leak_boundary | 4+ | 确定性结构化提示短路（动作1）+ #231/#228/#229 已修 live 验证 | quality-flywheel |
| S5 | **内部 meta / 学情 profile 泄露**（〔N〕孤儿注脚、工具命令 meta、长期画像提示、钓鱼攻击索内部 title/profile） | leak_boundary / content_truth | 5+ | 统一 `coerce_user_visible_answer` 单 sink + PR#250 攻击 3/3 无泄露已部署 | quality-flywheel |
| S6 | **fabrication 编造**（规范条文号、采分点、背景数字"中标价1.7亿/罚款2020修订"、自强化幻觉循环） | content_truth / sev_regression | 4+ | 写入侧断环 PR#204 + content-truth 核验闸 PR#302（编号核不到诚实降级）live 5/5 | quality-flywheel |
| S7 | **拒判 / 该 ACT 没 ACT**（批量作答漏判、Dim1 陈旧 active-set 出新题后 bare 答案拒判） | forward_liveness | 2 | S1 PR#299 turn-START demote carve-out，batch+裸答 0/6→3/3 | quality-flywheel |
| S8 | **topic precision drift / 题源忠实度**（出题考点漂移、逐字重复出题、相对 topic 当裸 topic） | content_truth | 3+ | goal2+3 PR#300 生成器科目锁 + 单一 normalizer，live 18/18 全建筑；仍需扩样本 | quality-flywheel |
| S9 | **terminal read-model drift**（public stream 已判但 DB result/assistant message 落回旧题/fallback 覆盖） | sev_regression / forward_liveness | 4+ | `turn_runtime` 持久化前强制 result 对齐已捕获 stream，本地 TDD+contract 已修 live 待复验 | quality-flywheel |
| S10 | **并发 / WS 捕获稳定性**（5 并发 ConnectionClosedError、跨 worker 流式死） | （稳定性专项，非内容维） | 2 | PR#190 store-tail 单一事件权威已修；harness 逐 turn JSONL 对账；并发压测仍需 live | quality-flywheel |

## 杠杆排序解读（对齐 satisfaction-drags-map 边际杠杆法）

- **最高杠杆（频次高 + 仍是强收口红线）**：S1 提交态 / S2 回指。复发次数最高、且 §7 里
  仍带「强收 = 回指 SEV-1 复发」红线——这两条是飞轮 metrics 最该盯的「红」。
- **已根治转回归清单（频次高但已闭环）**：S3 倒诬 / S4 泄露 / S5 meta 泄露 / S6 编造 —
  保留作回归断言（防复发），metrics 上应稳定 `GO`，一旦 `BLOCK` 即回归告警。
- **长尾内容缺口（→ 回灌内容飞轮）**：S8 topic drift / S6 fabrication 的「现编」= 内容
  补全信号，按 plan §V2「接内容飞轮」回灌 `scoring_point_compile.v1` / 教材 `*_v8`。
