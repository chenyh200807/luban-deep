---
name: luban-learning-pack-factory
description: Use when batch-producing Luban 教研测一体 learning packs, high-frequency mother-topic cards, teaching animations, variants, or mastery-discrimination checks. 鲁班"教研测一体"学习包的批量生产线总纲与质量闭环;造法细节调用 luban-diagram-microlesson,本 skill 不重复它。
---

# 鲁班教研测一体学习包生产线

> **定位**:本 skill 是"教研测一体"内容的**批量生产总纲 + 质量闭环**(怎么高效高质量地大批量造)。
> **造法库**(一张卡/一个母题的 6+1 原型、schema 脊柱、确定性渲染器、防漂移闸、anti-patterns)= `luban-diagram-microlesson`(agent-skills/),本 skill **调用它、不重复它**——避免两份漂移(单一权威)。
> **实现物料**在 `artifacts/luban_case_family_assets/diagram_microlesson/`;**选题源**在 `docs/原始数据/2026_副本/讲义/*_v8/`。

## 0. 一个 pack = 一个高频考点 = 教研测一体

最小生产单位是 **1 个高频可命题考点 / 深母题 = 1 个学习包**,三件共享同一份母题事实 authority:

| | 内容 | 事实来源(不许 LLM 编) |
|---|---|---|
| **研** | 母题:R2 不变量、变题库 variants、采分点、误解模型、source 溯源 | 讲义 `_v8` chunk + 真题 + 规范;采分点必带 `kind` + 候选后缀,溯源到 `page`。**造法=SOP「启动咒语」** |
| **教** | 讲懂动画:hook → 判据/工序逐点 → 结论 → 采分词;PPT 板书 + 运镜 | 旁白事实 anchor 回母题/卡字段;表现层 LLM 放开 |
| **测** | 闯关:同工程换数值分档 + 换工程迁移;看穿:真懂 vs 背过 + 暖反馈 | 变题=`variants`;看穿判定只读 `mastery_discrimination` signal,不另造 |

**"测"两模态**:【识别/判断】= 闯关分档 + 看穿(上表);【写作答】= 案例题作答训练(写完整答案 → 按采分点批改 → 作答错因 → 间隔复测),造法调 `luban-case-answer-layer`(agent-skills/),本 skill 不重复。**一建实务案例题(5 道写完整答案)走作答模态**——把 pack 的 R5/R6 可写化+训练化成作答能力,依附已 signed pack 加层、不造第二 authority。

**不是"知识点单卡题库"**:学习单元是考点(~55-60 高频,P0~20),不是 1976 个 taxonomy 叶,也不是整章。前台不卖"覆盖率",按盲点驱动。

## 1. 核心范式(高效高质量的来源,MVP 已验证两轮红到绿)

> **不为控制而控制,也不放任不可控。事实钉死,表现放开,质量靠事后评审迭代。**

```
研(事实冻结) -> 教/测 LLM 放开生成结构化 IR(发挥创造力) -> 确定性渲染
  -> 机器闸 + 独立 judge(必查项) -> 结构化反馈 -> 定向修订(只改被点名的)
  -> loop-until-pass(MVP:2 轮收敛) -> fan out 批量
```

- **表现放开**:讲懂动画的视觉/运镜/布局/reveal/hook/keycard、变题的情境包装——LLM 尽情发挥,产**结构化 IR(storyboard/lesson.json)**,不画像素也不被锁成填空。
- **事实钉死**:考点/数值/采分点/判据/构造正确性 -> anchor 回母题与规范,防漂移闸 fail-closed。
- **几何归确定性渲染**:坐标/布局/selector 由渲染器算(LLM 只填数据,IR 禁含 x/y/width/#id)。
- **质量靠迭代**:独立 judge 出结构化反馈 -> 定向改 -> 收敛;**不是事前锁死 prompt,也不是一次性自审**(自审有盲点)。

## 2. 质检闭环(高质量)——三层,缺一不可

**① 机器闸(全自动 fail-closed)**:防漂移 anchor 闸(`build_lesson_narration.mjs`:claim 段 anchor 解析不到即报错)、schema 校验(`validate_schema_drafts.py`)、student-safe + 静态合同(`validate_video_first_preview.mjs`)、视口/全屏(`validate_learning_stage_runtime.mjs`)、待补两道:`validate_timing_sync.mjs`(音画时长)、`data-id` selector DOM 命中断言。

**② 独立 judge(LLM-as-judge,必查闸查不出的隐性漂移)——这层不可省**:
> MVP 铁证:防漂移闸"全绿"是**假绿**——它只查 anchor 路径存在,查不出"念出来的事实有没有被 anchor 真覆盖";且自审有盲点。必须独立 judge(与生成 agent 不同的 agent)。
> **judge 必查项**(逐条):
> 1. **anchor 覆盖**:读 anchor 字段【实际内容】比对旁白,确认"念的事实被覆盖"(非仅路径存在)。
> 2. **claim:false 软事实扫描**:`claim:false` 段禁夹带无出处统计/频次/时长/数字断言(踩过"一半考生""90秒""每年都考");`grep '[0-9]+秒|一半|每年|%'` 辅助。
> 3. **采分词逐词有 SP anchor**:念出的每个采分词都要锚到对的 scoring_point(踩过念四词只锚一组);必要时拆 beat 分锚。
> 4. **数量/前向引用对齐**:"等下给你 N 道题"要与实际变题数对齐或软化。
> 5. **看穿判定**:只读 master signal(关键鉴别题=边界档+下限档/迁移档),不另造标准;标"鉴别候选·非正式判定"。
> 6. **闯关不泄阈值**:同工程分档题题干+选项不出现判据阈值数字(答后 feedback 才讲透);换工程迁移题可给该工程阈值但需讲懂铺垫。
> 7. **表现 anti-patterns**:hook 先讲丢分场景、main_exam_action 一线贯穿、每幕一点非翻页、采分表达"对象/路径+结果+判断依据"、自然收尾、先讲后问。
> judge 输出结构化:`{verdict, red_or_green, issues:[{axis, anti_pattern, beat_id, problem, fix, severity}]}`。

**③ 人审(机器/judge 都判不了的教学品味,只剩 3 类)**:镜头调度、箭头层级、采分表达质量。批次异步扫截图墙,不卡 worker。

anti-patterns 15 条:~9 条机器门、3 类 judge、3 类人审(详见 `luban-diagram-microlesson/references/anti-patterns.md`)。

## 3. 批量编排(高效)——loop-until-pass + fan out

```
Orchestrator:读高频考点清单 -> 按 6+1 原型分桶(同原型共享 fixture/golden,缓存高)
  -> fan out worker(5-8 张/波;dispatching-parallel-agents;worktree 隔离只写本卡)
  -> 每 worker 独立 loop-until-pass(N<=4 轮,超限标 needs_human,不污染其余):
       生成 IR -> 渲染 -> 机器闸 -> 独立 judge -> 反馈喂回改 -> 全绿 break
  -> 机器+judge 全绿后,人审批次一次性扫截图墙,只退人审 FAIL 的卡再转
```
- **反馈结构化喂回**:机器门 FAIL message + judge 的 `issues[]` 合并成修订指令,钉死"**只改被点名的 beat/字段,anchor 与 scoring_point_binding 不许动**"(防越改越散 + 防动事实层)。
- **生成 agent 与 judge agent 必须是不同 agent**(独立评审才有效,自评无意义)。

## 4. 选题与"够用"标准

- **选题源 = 讲义 `_v8` chunk**(教研编排考点 topic + 首页近五年分值表 = 教研认证考点+频次),不靠 taxonomy 树猜/真题 stem 印证。每 chunk 还给 R1-R8 弹药:`content_markdown`(讲懂)/`exam_matrix.grading_keywords`(R5 采分)/`trap_alert`(R8 误区)/`mnemonics`(hook)/`key_parameters`(数值)/`page_num`(R1 溯源)。
- **覆盖度三台阶(够用=指标不是数量)**:过及格线≈ 18-20 高频考点(P0)/ 护城河≈ 55-60 案例高频考点 / 讲全这门课≈ 500 教研考点(天花板,不卖)。**先 P0,gated on retention。**

## 5. 红线(违反即返工)

1. **事实层防漂移**:`claim:true` 必 anchor 回母题/卡/`master:R2`;采分点必带 `kind`+候选后缀+`page` 溯源,`official_score_allowed` 不得 true。
2. **几何不让 LLM 画**:坐标/构造正确性归确定性渲染器;LLM 只产数据/IR,IR 禁含 x/y/#id。
3. **独立 judge 不可省**:自审有盲点、机器闸会假绿;每个 pack 必过独立 judge 必查项。
4. **看穿读 master signal 不另造**;**闯关分档题不泄阈值**;**暖不毒舌**(先捧->就差一步->我相信你)。
5. **单一权威 / 解耦**:不抢评分(grading artifact)/学情(LearnerState)/错因(ERROR_CODE_REGISTRY);母题引擎=离线造+预存+学生自助,与 TutorBot(Nexus/RAG 对话答疑)解耦,不调其 runtime。
6. **不重复造法**:6+1 原型/schema/渲染器/闸调用 `luban-diagram-microlesson`,不在本 skill 另起一套(单一权威)。
7. **量产 gated on retention**:首样板未过学员留存证明前不批量铺第 2 个母题包;前台不卖"覆盖率/已做卡数"当 KPI。
8. **关键样板过 Codex 对抗**(`codex exec --sandbox read-only`);调试钩子 URL 门控不留生产。

## 6. 启动(批量第一步)——先证闭环,再 fan out

> **本节是「教/测」动画卡的启动。「研」层深母题 pack(R1-R8 事实)的启动咒语在 `docs/原始数据/考点原料/SOP-深母题pack生产-v2.md` 的「启动咒语」段——复制即跑、进版本管理;两个生产对象,别混。**

1. **MVP**:选 1 张已有母题卡(J01 危大,数据最全)跑完整 loop——生成 IR -> 机器闸 -> 独立 judge -> 反馈喂回改 -> **验收=改 IR 三轮内从红到绿**(MVP 已达成两轮)。证明闭环收敛。
2. **建库**:抽 `stage_shell`(壳=合同/几何=参数)+ 6+1 `fixture.json`/golden + `gate.sh`(串机器闸)+ 固化 judge/修订 prompt 模板;补两道缺门(`validate_timing_sync.mjs`、`data-id` selector 断言)。
3. **每原型先各 1 张样板**验证 6+1 都走通同一循环。
4. **fan out 到 P0 20**:按原型分桶 + loop-until-pass + 人审批次。
5. 先用 MVP 那张过 **学员留存门**(`F16_qigu_product_validation_plan.md` 复用),再扩量。

> 详细方法见 `luban-diagram-microlesson/references/`:`production-workflow.md`(本闭环完整版+MVP 记录)、`teaching-animation-journey.md`(讲懂->闯关->看穿)、`anti-patterns.md`(15 反例+稳定化范式)、`narration-spec.md`(旁白两模型)、`type-*.md`(6+1 原型)。本 skill 是它们的**生产线编排入口**。
