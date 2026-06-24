# 残留判分质量 bug 修复计划 + 宏观根因裁决

> **状态**:Proposed（2026-06-24）
> **来源**:2026-06-24 端到端 eval（两窗口）发现 ~20 问题，修复并验证 7、代码已修待合并 3、查清非 bug 3，**仍开放 ~7**。本计划只处理仍开放的**行为型判分 bug**（#11/#12/#13/#14），不含已收口项与未来增量闸（闸-1 BLOCKING / 闸-2 / 闸-3）。
> **方法**:按 root-cause-debugging 的宏观指挥官 lens——先判这些是不是**同一架构病**，再排修复序，避免逐个打补丁。

## 0. 宏观根因裁决:不是一个病，是 3 个机制不同的判分质量病 + 1 个展示层病

| bug | 业务事实(应成立) | 断点(第一个错误点) | shared failure shape | 同病? |
|---|---|---|---|---|
| **#11 选项重排判分用题库字母** | 判对错应按**学生当前看到的选项面**比对（值/内容），不是题库存储字母 | `answers_match`（`question_followup.py:705/750`）直接比字母，未把双方投影到同一面 | `dormant authority / unconsumed island`——投影函数 `_project_to_query_option_surface`（`historical_questions.py:262`）存在但判分不消费 | **病 A：判分面** |
| **#12 简答判分被 MCQ 抢占，判 bot 自造题** | 判分对象应是**用户的真实题**，不是 bot 自己生成的 MCQ | 简答请求触发 MCQ 生成时 `active_object` 被 bot 自造题覆盖成判分目标 | `multi-writer on active_object`——判分对象有多个 writer，bot 生成踩掉用户真题 | **病 B：判分对象** |
| **#13 质疑轮 sycophancy 编造叙事** | bot 不应附和学生的未核断言、不应臆造支撑硬事实（"2020改罚款8%"） | 缺内容真相 + 附和倾向 → 编造规范修订叙事 | 大部分=闸-4 硬事实纪律域（已修）；残留=sycophancy 行为 + `内容真相病`（系统真不知道正确内容） | **病 C：硬事实/附和（≈闸-4）** |
| **#14 〔N〕流式闪烁** | 学生流式过程中不应看到内部 meta 标记 | token delta 为保空白跳过 coerce（`turn_runtime.py:545-548`） | 展示/传输层，与判分 authority 正交 | **病 D：展示层** |

**结论（与既有计划和解后）**：
- **病 B（#12 简答被 MCQ 抢占）不是新病**——它已被另一窗口的 [判分态/作答提交单一权威收口计划](2026-06-24-grading-state-submission-authority-collapse-execution-plan.md) 明确列入 scope（该计划宏观病=`fast-path-as-authority, shielded-from-veto`，55 decider，症状含"简答被MCQ抢占"）。**本计划不为 #12 另立项**，归该计划；只需在其 Step 落地后 live 验证 g6 序列是否真消除，若残留则是**那个计划的残留**，不是新病。
- **病 A（#11 判分面）是真正独立、未被任何现有计划覆盖的第二病**——它不是 `fast-path-as-authority`（不是"把试探当提交"），是"判分比对用错了字母面"（dormant 投影权威未消费）。**本计划的唯一新增主体就是 #11。**
- **病 C 大部分已被闸-4 覆盖**（2026-06-24 已修），只差 live 验证 + sycophancy 残留 clause。
- **病 D 是独立展示层**，与判分无关，低优先。
- **净判断：开放 bug 的根因不是一个，是分属 3 个已有/已修战线 + 1 个真正未覆盖的独立病(#11)**。不要把它们当一个病一次性收口（跨机制巨型改动 + 撞另一窗口在飞收权）；#11 单独单点修，#12 归收权计划，#13 验闸-4，#14 展示层。

## 1. 病 A：#11 判分面投影未消费（最高优先）

**为什么最优先**：确定性复现（g1 T6 bot 自承"依据原题选项顺序"）、**会把答对判错=倒诬学生**（信任摧毁性最强）、且独立单点可修、收权没碰它。

- **one business fact**：一道 MCQ 的"哪个选项正确"在**学生当前题面**上的字母，是判分比对的唯一面。
- **one authority**：`_project_to_query_option_surface`（已存在的投影权威）。
- **修法**：判分前把 `correct_answer`（题库面）与学生作答**都投影到当前题面**再比，或让 `answers_match` 按"值/内容"而非字母比。落点 `question_followup.py:705/750` 的 `answers_match` 调用——消费已存在的投影函数（接通 dormant island），**不新建第二套**。
- **why not 老 pattern**：不是加正则识别"选项重排"，是把已有投影权威接到判分 reader。
- **验证**：构造选项重排题（值5%在题库是D、当前题面是A），学生选 A（值5%正确），断言判**对**；live ≥3 轮一致。

## 2. 病 B：#12 判分对象被 bot 自造题覆盖

- **one business fact**：当用户粘贴/指认一道真实题求批改，**那道题是唯一判分对象**，bot 后续生成的练习题不得成为判分目标。
- **one authority**：`active_object` 的判分目标维度——单一 writer。
- **断点**：简答判分请求 → 触发 MCQ 生成 → 生成的题写进 `active_object` → 判分锚到它（g6 T8 无视用户两道真题）。
- **修法**：判分对象的 writer 收口——用户真题（pasted/indicated）建立的判分目标，不得被"为练习而生成的题"覆盖（生成题进练习槽，不进判分目标槽）。复用 active_object 单写者收口思路（task#20 簇A 已对触发态收口，此处补对象维度），**不加第二套判分对象 authority**。
- **验证**：用户粘真题简答 → bot 不抢生成 MCQ 当判分目标；live 复现 g6 序列验证。

## 3. 病 C：#13 闸-4 覆盖度验证 + sycophancy 残留

- **现状**：闸-4（open-world 硬事实纪律）2026-06-24 已修并 live 验证（"4000万"消除）。g5 的"2020改罚款8%"属同类硬事实编造，**理论上已被闸-4 覆盖,但未单独 live 验证**。
- **修法**：①先 live 复现 g5 质疑轮序列，确认闸-4 是否挡住"2020修订"编造；②若残留 sycophancy（附和学生未核断言），在单一 `GROUNDING_CLAUSE` 加一句"不得附和/背书学生未经证据核实的事实断言"（单点，不在 directive 再加）;③`内容真相`残留（系统真不知道的）只能靠 grounded 检索或诚实 hedge，不在本计划强解。
- **验证**：g5 序列 live，断言无 conf=1.0 编造叙事。

## 4. 病 D：#14 〔N〕流式闪烁（低优先）

- 终态/历史已干净（[[meta-marker-leak-is-streaming-only-final-clean]]），只流式 delta 闪。delta 级剥 `〔N〕` 有跨 delta 边界复杂度。产品取舍，**非急需**，排最后。

## 5. 实施序（按"信任伤害 × 独立性 × 已部分覆盖"）

1. **P0 病 A（#11 判分面）**——独立单点、倒诬学生、确定性复现 → 先修。
2. **P0 病 B（#12 判分对象）**——收权残留对象维度，依赖 active_object 收口现状（先确认 task#20 簇A 收口边界，避免与另一窗口在飞收权撞）。
3. **P1 病 C（#13）**——先 live 验证闸-4 覆盖度，按结果决定是否补 sycophancy clause。
4. **P2 病 D（#14）**——流式剥离，低优先。

## 6. 红线 / 伪进展

- **别把 A/B/C 合成一次"判分大收口"**——三机制不同，合并=巨型改动 + 撞另一窗口在飞的收权。各自单点。
- **#11 别加"选项重排"探测正则**——投影权威已存在，接通它（dormant→consumed），不是新建识别层。
- **#12 别加第二套"判分对象" decider**——收口到 active_object 单写者，生成题进练习槽。
- **#13 别靠加更多对抗 LLM**——硬事实编造同源盲点已证；靠闸-4 grounding + 教材，sycophancy 靠单一 clause。
- 每条修完必 **live ≥3 轮一致**（eval-design），unit 绿 ≠ live 工作（本轮已多次实证）。

## 7. 相关入口
- `deeptutor/services/question_followup.py`（answers_match 判分比对 + active_question_set）
- `deeptutor/services/rag/historical_questions.py`（`_project_to_query_option_surface` 投影权威）
- `deeptutor/services/question_lifecycle_skills.py`（判分态收口，task#20 簇A）
- `deeptutor/core/grounding.py`（`GROUNDING_CLAUSE` 单一反编造权威）
- 关联 memory：[[mcq-grading-uses-bank-option-letter-not-presented-surface]]、[[single-authority-collapse-playbook]]、[[mcq-grading-routing-gap]]、[[compiled-scoring-library-clean-leak-is-runtime-improvisation]]
- 关联工单：`artifacts/student_army_eval_grading_2026-06-24.md`（g1-g6 原始发现）、`docs/plan/.../submission-authority-collapse-execution-plan.md`（task#20 簇A）
