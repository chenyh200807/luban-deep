# production-workflow.md · 动画学习卡量产 workflow(LLM 发挥 + 评审迭代)

> 范式纠偏(2026-06-19):**不是事前锁死 LLM,是【事实层 anchor 防漂移 + 表现层放开创造 + 事后多轮评审迭代收敛】**。借鉴 openmaic 的"LLM 产结构化 IR / renderer 确定性渲染"思路(只借思路不引其库,AGPL+太重,见 openmaic 评估)。

## 0. 为什么(纠正"为控制而控制")
- **分两层**:【事实层】考点/数值/采分点/构造正确性 → anchor 回母题(master/variants/scoring/source)+规范,**不放开**;【表现层】视觉/运镜/布局/交互/reveal/分镜 → **LLM 尽情发挥**。
- 旧错:用事实约束绑死了表现创造;且 60 卡几何不让 LLM 做 = 人手写 60 套渲染器 = 无法量产。
- 正解:LLM 生成结构化**动画 IR(storyboard)**发挥创造力 → renderer 渲成 HTML/SVG/Remotion 保稳定 → 评审→反馈→改 IR 迭代保质量。

## 1. openmaic 借来的技巧(逆向其代码所得)
1. LLM 只产**结构化中间表示**(action/text 扁平 JSON 数组 或 内嵌 config JSON),不画像素。
2. **枚举白名单 + schema 锁** action 种类/参数;renderer 纯 `switch` 确定性渲染(创造在编排层、稳定在图元层)。
3. 放开自由 HTML 处,**强制内嵌 `<script type=application/json id=card-config>{nodes,edges,revealOrder}</script>`** 当唯一结构化真源,生成后抠出(= 鲁班"卡为唯一源"的实现手法)。
4. **三段式分次生成**:卡(含 config)→ 从 config 派生旁白/讲解动作 → 离线配音(每段独立可重跑可校验)。
5. 易错**几何用 few-shot 代码喂死**(如边连接算法),不靠 LLM 现算坐标。
6. **"绝不报告动作、只产结果"** + 角色化 prompt + 字数配额控节奏(对齐"~1 分钟精简")。
7. **坑(eval 命中)**:跨 LLM 调用共享的 selector 约定若靠 prompt 默契、不强制,会 `#id` 悬空(生成 HTML 用 class 无 id)。→ 鲁班:可点元素一律 `data-id`,生成后断言每个 config.node.id 在 DOM 命中,否则回炉。

## 2. 量产 workflow 架构

> 2026-06-19 落地修正:不再新建独立 `LubanLessonIR` 或 `stage_shell.py`。现有
> `luban_teaching_animation.v0` 的 `*.lesson.json` 就是当前动画 IR,在
> `teach.beats[]` 内演进 `animation_action[]` 白名单字段;`render_archetype_journey.py`
> 等现有 renderer 负责确定性渲染。

```
一次性建库:统一 learning stage 合同 + 6+1 fixture/golden + gate.sh 串门
每卡 loop:
 P0 母题就绪(讲义_v8 选考点→归6+1→authority)  ← 事实层在此【冻结】
 P1 LLM 生成/修订 lesson beats + animation_action[](camera/highlight/reveal/keycard)★表现放开★
      约束:claim:true beat 必 anchor 回卡;IR 禁含 x/y/width/#id(几何归 renderer)
 P2 渲染(确定性 renderer 吃 lesson/master → journey/rendered.html + practice.html)
 P3 自动门 gate.sh(schema→action schema→timing_sync→render→data-id→runtime→practice→cdp_shot)
 P4 评审(LLM-as-judge 多视角[镜头/叙事/采分] + 人审[创造力/教学品味/anti-patterns])
 过关? NO→ P5 结构化反馈喂回 → 回 P1 改 IR(只改表现,anchor 不动) / YES→ P6 学员门(KPI 正确率)
```
**铁律:循环只在 P1↔P5(改表现 IR),P0 母题事实永不进循环。**

## 3. 多 agent 量产 60
Orchestrator 按 6+1 原型分桶(同原型共享 fixture/golden)→ fan out worker(5-8 张/波)→ 每 worker 独立 **loop-until-pass**(N=4 上限,超限标 `needs_human`,worktree 隔离只写本卡)→ 机器门+judge 全绿 → **人审批次异步扫截图墙**(cards.html 风格),只退人审 FAIL 的卡再转。

## 4. 反馈结构化喂回(让循环真收敛)
- 机器门 FAIL message(已是 `LEVEL file check: msg` 三段式)→ `gate_failures[]`。
- LLM judge 必须按固定 schema 出:`{verdict, issues:[{axis, anti_pattern, beat_id, fix, severity}]}`。
- 合并成修订指令喂回 P1,钉死"**只改被点名的 beat/字段,anchor 与 scoring_point_binding 不许动**"。

## 5. 门/judge/人审三分(anti-patterns 15 条)
- **~9 条全自动机器门**:schema / animation_action 白名单 / 旁白 anchor / student-safe / 章节语义 / practice / 真实视口 / timing sync / data-id selector 命中 / 视觉快照。
- **LLM judge**:镜头是否筛注意力、叙事一线贯穿、错觉真实。
- **3 类纯人审**(教学品味):镜头调度、箭头层级、采分表达质量。
- **已落地两道硬门**:`validate_timing_sync.mjs`(总时长 + `sync_keyword` 命中对应 timing 文本/keycard)、
  `validate_data_id_targets.mjs`(lesson `animation_action[].target` → rendered DOM 命中)。
  它们由 `artifacts/luban_case_family_assets/diagram_microlesson/gate.sh` 串联,在
  `contracts/registries.yaml` 以 `operational` 登记,不误升为全仓 PR gate。

## 6. MVP → 60 的路径
- **MVP(先 1 卡,不 fan out)**:选已有母题卡(J01/④ 或 F16/①),手工跑完整 loop。**验收 = "改表现字段三轮内从红到绿"**(证闭环收敛),不追 60 张。
- **扩到 60**:复用 learning stage 合同 + 6 `fixture/golden` → 每原型各 1 张样板验证 → fan out 60。
- **量产 gated on retention**:先用 MVP 那张过 P6 学员留存,再铺量。
- 最小件状态:`validate_timing_sync.mjs`、`validate_data_id_targets.mjs`、`render_archetype_practice.py`、`build_card_bundle_manifest.py`、J01 `gate.sh` 已落地;
  judge+修订 prompt 模板仍是后续补齐项。

## 6.1 J01 确定性切片(2026-06-19)

J01 已证明一条最小可交付链:

```bash
artifacts/luban_case_family_assets/diagram_microlesson/gate.sh J01
```

当前 PASS 范围:

- `validate_schema_drafts.py`:9/9 OK。
- `validate_animation_action_schema.py --require-actions`:J01 beat action 白名单 OK。
- `validate_timing_sync.mjs --max 151`:150.0s + claim `sync_keyword` 存在且命中对应 timing 文本/keycard。
- `render_archetype_journey.py`:复用现有 renderer 产 `M_danger_work_expert_argumentation.journey.html`。
- `render_archetype_practice.py`:从 master variants/scoring terms 产独立 `M_danger_work_expert_argumentation.practice.html`。
- `validate_data_id_targets.mjs`:所有 `animation_action[].target` 命中 rendered DOM。
- `validate_learning_stage_runtime.mjs`:390 竖屏 / 844 横屏 / 1024 宽屏 / 真实 `[data-theater-toggle]` theater 入口全 PASS。
- `validate_video_first_preview.mjs`:decision-first journey + independent practice gate PASS(1 warn:旧壳未内嵌 `lessonData`,不阻塞)。
- `build_card_bundle_manifest.py --require-practice`:生成 non-authoritative bundle manifest,记录 master/lesson/timing/rendered/practice/audio asset hash,路径为 bundle-root 相对路径。

未覆盖范围必须明说,不能偷换成全计划完成:

- N01/S02 还未接入同一套 gates。
- judge 修订 prompt 模板和 learner evidence 仍待后续。

## 7. MVP 验证(2026-06-19)+ judge 必查项

用 J01(危大)跑通单卡 generate→judge→revise 闭环,**两轮从红到绿**(优于"三轮内"验收):
- 轮1:生成 agent 自由生成 v1(发挥了 hook/运镜/keycard)→ 独立 judge = **红**(2 CRITICAL + 2 HIGH)。
- 轮2:按结构化反馈定向修(没改坏对的)→ judge 复核 = **绿 PASS**(必修项真修好,仅 1 MED 留渲染收)。

**最重要的发现:防漂移闸"全绿"是假绿。** `build_lesson_narration` 的闸只查 `anchor 路径是否存在`,**查不出"旁白念出来的事实有没有被那条 anchor 真覆盖"**。所以光靠机器闸不够,**LLM-as-judge 这层是量产质量的必需环**,不是可选。

**judge 必查项(闸查不出、必须 judge/人查的隐性漂移)**:
1. **anchor 覆盖检查**:读 anchor 字段【实际内容】比对旁白,确认"念的事实被覆盖",不是只查路径存在(踩过:gate1_act 念"危大→编方案"却锚到含"无需论证"的中间档结论)。
2. **claim:false 软事实扫描**:`claim:false` 段最易夹带【无出处软事实】——统计("一半考生")、频次("几乎每年都考")、时长("90秒")、任何数字断言。grep `\d+秒|一半|每年|%|考生.*数` 辅助。
3. **采分词逐词有 SP anchor**:念出的每个采分词都要有对应 scoring_point anchor(踩过:念四词只锚 SP_scale,漏 SP_conclusion);必要时拆 beat 分锚。
4. **数量/前向引用对齐**:"等下给你四道题"这类数量声明要么软化、要么与实际变题/练习数对齐(踩过:说"四道题"但母题有 5 变题)。
5. **表现层 anti-patterns**:hook/main_exam_action/运镜/采分表达/收尾(见 §5 + 反例总表)。

**结论**:闭环机制成立——生成层放开发挥、judge 层用上述必查项出结构化反馈(`{axis,anti_pattern,beat,fix,severity}`)、生成层定向改、2 轮收敛。fan out 到 60 卡即每卡跑此 loop-until-pass。**外部产线(Codex 端 skills)接法 = 当生成层,产物回这套 judge + 门;不复制 skill。**
