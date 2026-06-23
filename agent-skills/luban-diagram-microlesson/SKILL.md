---
name: luban-diagram-microlesson
description: Use when authoring, rendering, redesigning, or reviewing 鲁班 diagram micro-lessons or video-first 深母题学习卡 under artifacts/luban_case_family_assets/diagram_microlesson/, especially card JSON, master data, renderers, Remotion, narration, practice pages, mobile player UX, student-safe boundaries, or prototype/template selection.
---

# 鲁班图解微课 / 深母题学习闭环 (diagram_microlesson)

> **权威位**:本 skill 是造法的单一权威(已从 artifacts/.../skill_design 提升至此;skill_design 已退役)。
> **实现物料**全部在 `artifacts/luban_case_family_assets/diagram_microlesson/`(渲染器/脚本/样板卡/母题),本 skill 只装"怎么造"的规则,物料是 thin wrapper。
> **唯一目录**:`artifacts/luban_case_family_assets/diagram_microlesson/`。不新建第二套目录 / 第二个 schema_version / 第二份 skill。
>
> 配套实现(均在上述唯一目录):`SCHEMA.md`(schema 脊柱)、`render_card.py`/`render_network_card.py`/`render_contrast_card.py`/`render_decision_card.py`(原型渲染器)、`render_master_view.py`(深母题 deck 闯关)、`render_teaching_animation.py`(PPT 教学动画·讲懂幕引擎)、`render_archetype_journey.py`(**完整学习闭环·一镜到底**)、`render_network_video_first.py` + `remotion_demo/src/N01NetworkVideoFirst.tsx`(**N01 video-first 当前样板**)、`F16_qigu.animation_ir.v0.json` + `render_animation_ir_preview.py` + `remotion_demo/src/AnimationIrRenderer.tsx` + `remotion_demo/src/F16AnimationIrPreview.tsx`(**OpenMAIC-style animation_ir.v0 新引擎样板:通用 renderer + F16 thin wrapper**)、`validate_schema_drafts.py`(schema 校验门)、`validate_lesson_source_workflow.mjs`(**成品 MD→source_card→lesson 连贯性门**)、`validate_animation_action_schema.py`(v0 beat action 白名单门)、`validate_animation_ir_contract.mjs`(**渲染前 IR contract 门:scene/action/visual_library/Remotion 同源**)、`validate_animation_ir_preview.mjs`(**渲染后 IR→HTML 等价/真实视口/遮挡/触控/闯关解锁门**)、`validate_challenge_theater_practice.mjs`(**独立闯关页真实视口/文字可读/图元标签适配门**)、`validate_timing_sync.mjs`(timing/sync_keyword 门)、`validate_data_id_targets.mjs`(action target→DOM 命中门)、`validate_video_first_preview.mjs`(video-first/IR 静态预览合同门)、`validate_learning_stage_runtime.mjs`(学习舞台真实视口运行时门)、`build_workflow_review_packet.mjs`(**机器门/截图墙/root-cause 回炉包**)、`gate.sh`(J01 当前确定性门串联)、`build_card_narration.mjs`(单卡旁白派生)、`build_lesson_narration.mjs`(教学动画/双人配音+防漂移闸)、`cdp_shot.mjs`(零依赖手机截图)、脚手架卡 `F16_qigu.json`(①)/`N01_network_keypath.json`(③)/`C01_*contrast*.json`(⑤)/`J01_*argumentation*.json`(④)、讲懂脚本 `*.lesson.json`、母题样板 `M_*.master.json`(标 sample.v0,**生产 case_family 待 schema 登记**)。
> 晋级实现(2026-06-23 起必须跟随):`capture_remotion_ir_review_stills.mjs` 是 `workflow_candidate/student_ready` 的 Remotion still 截图与质量门 authority;`validate_workflow_promotions.mjs` 是批量 manifest 中 `promoted/preserved_by_batch` 的晋级验收 authority;`build_animation_ir_batch.py` 必须保留已晋级卡,不得用粗糙批量草稿覆盖。
> references:造卡读 `style-guide.md` + 对应 `type-*.md`;**造 video-first / decision-first 动画学习卡、Remotion、独立闯关页先读 `animation-production-director.md` + `learning-stage-shell.md` + `workflow-review-loop.md` + `video-first-pressure-tests.md` + `anti-patterns.md`**;有声卡读 `narration-spec.md`;完整母题闭环/教学动画读 `teaching-animation-journey.md`;web-view 承载读 `wechat-webview-sandbox.md`;手机截图/DOM 断言读 `zero-dep-cdp-harness.md`。

## 这套 skill 解决什么

建筑实务考点很多,但**认知结构只有 6+1 种**。任何考点先归一个**展现原型**,再套该原型的 UI/SVG/交互 + 锚 authority 填 schema。**展现层站在成熟手艺的肩膀上(每原型有"祖师爷"),护城河在内容层(采分点/错因/authority)。**

**N01 之后的当前默认路线**:母题引擎数据 → 识别 6+1 原型 → 设计 video-first 讲解动画(先 hook 为什么学,再纠错/推演/采分) → 独立闯关页(每题有图/变化图,选项统一成"对象/路径 + 结果 + 判断依据",含采分句输出题) → 看穿/暖反馈。不要回到"静态卡 + 几个按钮"或"旁白播客 + 画面翻页"。

## video-first 路由(2026-06-19)

本文件只做入口路由,不再复制完整导演手册。造或修 video-first 动画学习卡时必须按顺序读:

1. `references/animation-production-director.md`:量产导演、旁白、运镜、练习、手机播放器、验收分层。
2. `references/learning-stage-shell.md`:稳定学习舞台模板、slot 边界、横竖屏/theater 运行时验收。
3. `references/workflow-review-loop.md`:机器门、截图墙、LLM/human 评审、root-cause triage 和回炉修订格式。
4. `references/video-first-pressure-tests.md`:跨 6+1 原型的压力场景,防止把 N01 网络图外形当万能模板。
5. `references/anti-patterns.md`:N01/S01 已踩坑的反例、根因、修法和 gate。

`N01_network_video_first.rendered.html` 的价值是**导演方法**,不是网络图 UI。后续 F16/J01/C01/D01/S01 等不同原型继承的是:母题数据先行、先 hook、先打错觉、Remotion 真动画、音画同步、orientation-adaptive 响应式学习舞台、独立闯关页、每题配图、采分句输出、自然收尾、预览合同门。具体视觉必须换成本原型的剖面、判断树、对照图、答案扫描或诊断图。

### v0 typed action 路线(2026-06-19)

当前不新建 `LubanLessonIR`。现有 `luban_teaching_animation.v0` 的 `*.lesson.json` 就是动画 IR,只在
`teach.beats[]` 内演进 `animation_action[]`:

- `type` 白名单:`camera` / `highlight` / `reveal` / `keycard`。
- `target` 必须是 `data-id:<id>`。
- renderer 输出必须提供 `[data-card-id]`、`[data-stage-shell]`、`[data-beat-id]`、`[data-action-id]`、`[data-visual-node-id]`、`[data-practice-id]` 和 `window.__LUBAN_LESSON_MANIFEST__`。
- `data-id:<id>` 只能命中 renderer 合同内的 `data-*` hook,不得靠普通 DOM `id` 假通过。
- 学生 HTML 中的 manifest 只暴露 presentation action wiring;不得包含 `schema_version`、`source_ref`、`scoring_point`、`candidate`、E-code、P-code 等制作侧/内部 token。
- 默认校验是 optional-present:旧 v0 lesson 没有 `animation_action[]` 不能因此失败;具体 MVP 卡需要 action 时由 `--require-actions` 或 `gate.sh` 显式要求。
- J01 当前确定性门:

```bash
artifacts/luban_case_family_assets/diagram_microlesson/gate.sh J01
```

该门已覆盖 schema/action/timing/render/practice/data-id/runtime/bundle manifest,不生成 MP4;practice 或 timing.audio 缺失会在 gate 中失败。runtime gate 必须通过真实 `[data-theater-toggle]` 入口进入 theater,不得在 gate 里直接给页面加 `.theater` 假通过。timing gate 必须验证 `sync_keyword` 命中对应 timing 段文本/keycard,不能只看字段存在。

### animation_ir.v0 路线(OpenMAIC-style,2026-06-19)

当页面出现叠层、比例漂移、横竖屏细微变化就坏,说明问题不在某个 CSS 细节,而是 renderer 在累积页面状态。后续新引擎默认走:

```
母题数据(master/card/lesson/timing/practice)
→ animation_ir.v0(scene/focus/enter/hold/exit/layout/camera/visible_nodes/keycard/coach/actions/visual_library)
→ pre-render gate(validate_animation_ir_contract.mjs)
→ HTML preview renderer(确定性 switch/scene/action)
→ Remotion renderer(吃同一份 IR;topic wrapper 必须薄)
→ post-render gate(静态 + 真实 DOM)
```

### 生成前视觉原型闸(必须先于 IR)

**先判认知结构,再写动画 IR。** 每张卡在 `source_card` 后、`practice_blueprint` 前必须生成 `visual_archetype_decision`,并写入后续 lesson/IR/review packet:

```json
{
  "primary_archetype": "process_step_reveal|section_or_spatial_reveal|calculation_structure|decision_branch_reveal|contrast_reveal|scoring_diagnosis_reveal|value_memory_card",
  "secondary_archetype": "...optional...",
  "visual_primitive": "process_flow|layer_stack|roof_section|site_plan|network_graph|formula_chain|decision_tree|contrast_pair|answer_scan|memory_table",
  "motion_grammar": "step_trace|layer_explode|path_growth|branch_eliminate|wrong_then_right|scan_hit_partial_miss|table_flash",
  "why_this_visual": "它解决哪个认知难点",
  "why_not_text": "纯文字为什么讲不清",
  "must_show_domain_objects": true,
  "domain_visual_plan": [
    {
      "scene": "hook|map|rule|trap|score",
      "domain_objects": ["本考点必须看见的工程对象/现场对象/资金对象/图结构对象"],
      "visual_action": "这些对象如何进入、退出、移动、分层、命中或被淘汰",
      "why_object_not_box": "为什么不能只用文字框/判断框替代"
    }
  ],
  "pure_text_allowed": false
}
```

硬门槛:

- **默认 `pure_text_allowed=false`**。只有原型确认为 `(七) value_memory_card` 且内容本身是定义/数值/参数记忆时,才可置 true;即便如此也优先做 `memory_table / number_line / flashcard`,不是段落讲稿。
- ①–⑥ 任何卡不得以“安全/合同/管理类不好画”为理由退回纯文字。安全验收要画结构/失稳链/判断树;合同计价要画资金链/公式链;平面布置要画 site plan;质量通病要画病灶/对照/诊断图。
- `pill / note / answer_box / dialogue_box` 只是辅助提示。若主视觉由这些文字容器承担,即使页面看起来有框,也按**文字卡伪图示**失败。
- `visual_archetype_decision` 缺失、`visual_primitive` 与 6+1 不匹配、`why_not_text` 为空、或 `domain_visual_plan` 为空时,不得生成 IR、不得配音、不得进入批量卡成品目录。
- **工程对象图是精品卡硬门,不是加分项**:①–⑥ 每张卡至少 4 个主讲 teaching scene 必须出现本考点的 domain objects,如吊机/吊钩/重物/风速表/试吊高度、屋面基层/卷材/鼓泡/蓄水、网络节点/箭线/总时差、资金流/公式口径、验收对象/检查项/放行门。只有抽象 `decision_tree`、`process_flow`、`answer_box`、`threshold_meter` 但没有 domain objects,按**抽象框图伪图示**失败。
- **顶尖视觉解析必须声明 `visual_excellence_profile`**:`workflow_candidate` 或 `student_ready` 不再只看 schema/gate 绿,必须在 IR 顶层写明参考视觉范式、必须展示的工程对象/阈值/对照/规则卡、motion 标准、layout guards 和 release_bar。用户给出的危大工程阈值图是当前参考标准:深色工程蓝图底、真实构件线稿、尺寸/高度轴、黄色危大线、红色超规模线、底部规则卡。不同考点可以不用同款外观,但必须达到同等清晰度:对象可测量、阈值可对照、危险/超限状态被动画击中、规则依据最后落成可背可写的卡片。
- **图示主导必须有 IR 层和成片路径证据**:`workflow_candidate/student_ready` 除 HTML/手机截图墙外,还必须跑 Remotion still review。`validate_animation_ir_contract.mjs` 必须证明每个主讲 scene 有非文字 domain diagram 主图达到 `min_visual_dominance_ratio`;A02/S02 的 blueprint-poster 样板阈值是 0.62,实测每幕 0.744。`capture_remotion_ir_review_stills.mjs` 产出的 manifest 必须进入 review packet,且 `quality_gate.required=true`、`quality_gate.pass=true`、`quality_gate.flags=[]`;否则只能保留为结构草稿。A02/S02 当前采用 `blueprint_poster` 作为工程蓝图式样板:大画板解释材料验收/起重阈值,字幕和规则卡只做辅助。它不是所有卡唯一外观,但同级“第一眼是图示动作,不是文字讲稿”的密度是硬门槛。
- **S02 反例必须记住**:起重吊装安全不能只画“四道门”文字框。合格版本必须至少画出吊机/吊钩/重物、10kN/100kN/300kN/200m 门槛、6级风或 9.0m/s 停工、90% 试吊离地 200-500mm 四查、限位装置禁令、答题纸采分句。否则即使 schema/gate 绿,也不能进 `finished/`。
- 用户给出的 6+1 表是本 workflow 的原型选择 authority:按**认知结构**选表现方式,不按教材章节名、文件名或既有样板外形套模板。

硬规则:

1. AI/LLM 可以充分发挥,但只发挥在 `animation_ir.v0` 的编排层;不得直接画像素、不得输出自由 HTML 当唯一真相。
2. 每个 beat/scene 必须显式写 `scene`、`focus`、`enter`、`hold`、`exit`、`layout`、`camera`、`visible_nodes`、`keycard`、`coach`。
3. **scene 只是页面边界,action 才是动画**。OpenMAIC 的关键不是"把整页换得更顺",而是 action 队列串行执行。`animation_ir.v0` 必须继续演进 `micro_actions/actions[]`:每个 action 明确 `target(data-id)`、`kind(reveal/highlight/camera/annotate/exit/speech)`、`start/end`、`enter/exit`。renderer 只能消费这些 action,不能凭历史 DOM 状态猜下一步。
4. renderer 只认 IR,每个时刻只渲染当前 scene 和当前 action 集;禁止靠 `reached-*`、历史 class、已播放节点数组来累积画面。
5. `visible_nodes.length <= render_contract.max_visible_nodes`。F16 这类工序/构造卡默认拆成多 scene:起鼓病因、割开放气、干燥清基、附加封严、蓄水检验、答题纸采分句、闯关桥接。
6. HTML preview 是产品评审入口,不是 Remotion 成片。它必须模拟 action playback、字幕、拖动、theater 交互;正式成片时 Remotion renderer 必须吃同一份 IR。预览阶段不生成 MP4。
7. **前面先审**:IR 生成后、任何 renderer 运行前先跑 `validate_animation_ir_contract.mjs`。它必须证明 scene 时间不重叠、visible_nodes 有 visual_library backing、action kind/target/timing 合法、student-safe 文本无内部 token、Remotion wrapper 导入当前 IR 并委托通用 `AnimationIrRenderer`。没过不要渲染,更不要调 CSS。
8. post-render gate 至少覆盖:IR schema/必填字段、scene 不重叠、IR→HTML preview data 等价、当前屏最大可见信息数、keycard 不累积、字幕存在、字幕 live region、theater 默认隐藏控制层且点击浮出、theater 有闯关入口、无 `reached-*`、student-safe、真实 DOM 只有一个 active scene、scene 后段至少有一个节点经 action/progressive reveal 可见。不要只抽 scene 中段;很多拥挤/叠层只在全 reveal 后暴露。
9. 手机 preview gate 必须跑真实视口矩阵:360/390/430 竖屏 + 844/932 横屏;断言播放器不遮挡 `.visual`/字幕/教练卡/CTA、控件命中盒 >=44px、无横向 overflow、闯关 CTA 在采分句前 locked、采分句后 enabled、seek 到旧时间不残留 off-scene 节点。
10. **SVG 文本安全是 renderer/gate 合同,不是单卡坐标问题**:所有图元必须自带安全文字策略(pill fit、多行、徽标占位、箭头从标签后起笔、必要时图例化)。post-render gate 必须检查 pill label padding、SVG text/text 碰撞、flow_arrow label 与箭头线间距。截图发现文字贴边/压线/跑出白板时,优先改 primitive renderer + gate,不要只改当前卡 x/y。
11. **练习页也必须是 runtime 产品面,不是附属 HTML**:独立闯关页必须跑 `validate_challenge_theater_practice.mjs` 或同级 gate,覆盖 360/390 竖屏、844 横屏和至少一个宽屏/桌面视口;检查文字不裁切、SVG/图元标签不挤压、底栏不覆盖、题干/依据默认渐进展开、触控 >=44px。没有这道门,不得说 practice 合格。
12. **截图证据是验收的一部分**:机器门 PASS 后还要用 `cdp_shot.mjs` 截目标视口。若用户反馈来自某个截图/设备比例,该比例必须加入下一轮 gate 或截图证据。禁止只看 390x844 或只看 DOM 指标就判合格。
13. **机器门之后必须形成 review packet**:按 `workflow-review-loop.md` 记录 gate 输出、目标截图墙、judge/human 发现、root-cause triage、修复层级和回炉字段。若人眼发现问题但没有新增 gate/anti-pattern/triage,不得把本轮标为 workflow improvement。
14. `construction-whiteboard-director` 作为 P0.5 导演/质检硬门使用:每张卡先写 teaching spine、5-8 beat sheet、每 beat 一个 visual action + 一句字幕/旁白 + 下个 beat 前退出什么。它不是内容权威,也不是 renderer authority;最终权威仍是母题数据 + `animation_ir.v0` + deterministic renderer。
15. **6+1 原型必须落成图示 primitive,不能只落成文案分类**:生成器识别 `process_step_reveal / section_or_spatial_reveal / calculation_structure / decision_branch_reveal / contrast_reveal / scoring_diagnosis_reveal / value_memory_card` 后,必须写入 `render_contract.archetype_visual_required` 并在 `visual_library` 命中对应 primitive(`process_flow / layer_stack|roof_section / network_graph|formula_chain / decision_tree / contrast_pair / answer_scan / memory_table`)。这只是底线,不是合格线。主讲 teaching scenes 默认是 `hook / map / rule / trap / score`;其中至少 4/5、量产生成器默认 5/5 必须包含非文字图元。`score` 场景必须用答题纸/诊断图(`answer_scan` 或同级 primitive)把视觉结果落成采分句,不得退化成三条 `answer_box`。`pill / answer_box / dialogue_box / note / flow_arrow / threshold_meter` 只能辅助字幕、提示、问答和少量标注,不得作为主教学图示。contract gate 必须 fail-closed 拦截 text-container-only IR 和“有一个图元但主讲仍像文字卡”的 IR。
16. **图示 primitive 还必须会“解释动作”,不能只是静态图**:用户要的是动画解释知识,不是文字解释知识,也不是“整块图淡入”。`process_flow` 必须 step/trace 工序路径;`layer_stack|roof_section` 必须逐层分离/显现;`network_graph|formula_chain` 必须沿路径/算链生长;`decision_tree` 必须根节点→分支→淘汰/命中;`contrast_pair` 必须先错后对/左右对照;`answer_scan` 必须逐句扫描 hit/partial/miss。`memory_table` 属于(七)数值/记忆,默认别动画化。HTML preview 必须输出 `data-primitive-step`,Remotion 通用 renderer 必须有 `PrimitiveStep`;`validate_animation_ir_contract.mjs` 看到这些可动画 primitive 时必须检查两端内部动画能力。没有内部 step 的图示仍按“静态图伪动画”处理。
16a. **图示必须是“领域对象在动”,不是“文字框在动”**:判断树/流程图只是认知骨架,不是最终画面。每个主讲场景必须先问“学生应该看见哪个真实对象/工程对象发生了什么变化”。对象进入 IR 时至少写 `domain_objects[]` 或使用领域 primitive,并在旁白中用对象解释判断。只有“第一道门/第二道门/条件/采分句”这种抽象框,即使有 reveal/highlight,仍按失败处理。
16b. **每个 scene 必须按本句文案重新设计图,不能一套模板图贯穿多数页面**:在写 `visual_library` 前,逐 beat 先读 `bridge/exam_task/visual_explanation/answer_move` 和旁白句,再回答“这一句要学生看见什么对象、对象怎么变、为什么现在要换图”。同一个 `process_flow`/四图组合/判断树外形连续复用超过 2 个主讲 scene,默认按**模板图贯穿伪动画**失败;除非 storyboard 写明同一对象发生了实质状态变化(进入/移动/分层/命中/淘汰/trace/扫描/退出),且截图中能看出来。精品卡至少 4 个主讲 scene 的主图要有不同的领域对象组合或不同的对象状态,不能只换标题、标签和旁白。
16c. **旁白必须说清“这道题到底是什么”,不能用内部编号或文件 ID 当解释**:老师开场和主讲不得说“A02 不是让你……”这类只有制作方懂的编号式句子;可以在 kicker/制作物料里保留 `A02/P40_A02` 追溯,但学生旁白必须展开为真实考试任务,例如“这类案例题问的是材料进场前要怎么验收、哪些材料要复验、隐蔽工程覆盖前要留什么验收记录”。旁白中的 `A02/F16/J01/P40`、`pack`、`source_card`、`IR`、`scene`、`primitive` 等内部词若直接进入学生语音,按**编号式旁白/内部黑话**失败。
17. **单卡质量闭环优先于批量生成**:40 pack / 60 pack 批量脚本只能产 `coarse_draft_requires_single_card_review`,用于发现覆盖面、缺数据和 renderer/gate 问题;不得把 39/39 PASS 或 5/5 diagrammatic 当成学员可用。每张精品卡必须单独走 `母题数据→teaching spine→图示 storyboard→IR→renderer→gate→手机截图墙→Remotion still quality gate→人工/LLM review→回炉`。只有当前一张在手机截图和 Remotion still 中都确实做到“图示动画解释知识、文字只是辅助、闯关可读”后,才进入下一张。批量扩张前至少要有 2-3 个不同原型单卡样板通过同一质量门。已晋级 `workflow_candidate` 只能通过 workflow packet PASS + Remotion quality gate PASS + `validate_workflow_promotions.mjs` 进入 batch manifest,并必须标 `preserved_by_batch=true`;批量生成器不得覆盖它。
18. **讲清楚优先,5 分钟以内都可接受**:动画不是短视频 KPI,而是让学生围绕一个考点能做题、能写采分句。复杂知识点允许 2-5 分钟;不得为了压短删掉因果解释、视觉推演、答题纸落点或真实 QA。但长时长必须靠 `actions[]`/运镜/图示逐步解释,不能变成长口播或整页翻片。
19. **source_card 必须从成品 MD 提炼教学脊柱**:每张精品卡在 lesson/IR 前必须有 `source_refs.pack_markdown` 指向 `docs/原始数据/考点原料/成品/<ID>_*.md`,并有 `main_exam_action`、`wrong_idea`、`teaching_spine[]`。`teaching_spine[]` 每步写 `state/anchor_md/visual_fact/bridge_from_previous/answer_move`;lesson 每个 beat 写 `bridge/exam_task/visual_explanation/answer_move`。`validate_lesson_source_workflow.mjs` 未过,不得配音、不得生成 IR。

60 张卡量产的核心目标:每次 F16/N01/S01/A01 暴露的问题,都要优先沉淀到 `animation_ir.v0`、renderer、gate 或本 skill,而不是只修单卡 CSS。单卡能看只是样例;可复用 workflow 才是交付物。
如果某次修复选择只改 card CSS,必须在复盘中写明为什么不是 stage shell / renderer / gate 问题;否则默认返工。

当前最小样板:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_animation_ir_contract.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.animation_ir.v0.json

python artifacts/luban_case_family_assets/diagram_microlesson/render_animation_ir_preview.py \
  artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.animation_ir.v0.json

node artifacts/luban_case_family_assets/diagram_microlesson/validate_animation_ir_preview.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.animation_ir.v0.json \
  artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu.animation_ir_preview.html

(cd artifacts/luban_case_family_assets/diagram_microlesson/remotion_demo && \
  npx tsc --noEmit && \
  npx remotion still src/index.ts F16AnimationIrPreview out/f16-animation-ir-preview-score.png --frame=2460 --scale=0.5)
```

### decision-first 修正(2026-06-19)

`video-first` 不是所有考点的入口权威。对 `decision_branch_reveal`、安全放行、验收判断、危大分档这类"会不会判"的考点,普通入口默认改成 **decision-first**:

- 首屏先给一个最小判断题/错觉题,让学生先作答或表态,再播放讲解纠错。
- 动画/音频是教练反馈,不是主路径本身;学生不用全屏也能完成判断、得到反馈、进入闯关。
- 横屏/宽屏优先使用"左侧大图/判断树 + 右侧教练反馈/选项/采分原子",不要把内容锁成竖屏视频。
- `video-first` 仍可用于计算推演、构造演示、流程动画,但不能压过该原型的核心认知动作。

## Phase 流程(每造一张卡走一遍)

```
Phase 0  选考点【优先从讲义 _v8 chunk 选,别靠 taxonomy 树猜/真题 stem 印证】→ 归原型(7 选 1,见下表)→ 混合考点走兜底(见下)→ 查 authority 覆盖(采分点签发/候选?)
         讲义源 = docs/原始数据/2026_副本/讲义/<本>_v8/<本>_v8.json:per-chunk 挂 taxonomy.topic(教研编排的考点级 topic,《主体结构》就有 ~69 个)+ 首页"近五年分值排布"= 教研认证考点 + 频次,这才是"考点→知识点"指导地图(8 本全有 _v8)
Phase 1  锚 authority + 弹药从讲义 chunk 取:R1 source_ref=讲义 chunk(带 source_meta.page_num 溯源,满足"采分点必须教材原文溯源")、采分点→exam_matrix.grading_keywords(R5 候选)、误区→exam_matrix.trap_alert(R8)、memory_hook→exam_matrix.mnemonics、数值→key_parameters(numeric_value)、讲懂正文→content_markdown/knowledge_cards
         讲义=教研【candidate】源:每个 scoring_point 必带 kind + 候选后缀,official_score_allowed 不得 true,定稿数值/条文号回规范/教材核(讲义不是签发)
         错因→ERROR_CODE_REGISTRY、知识→canonical taxonomy、前置/易混→live knowledge graph;采分点只在 scoring_points[] 定义一次,body 用 *_binding 引用(reference-not-duplicate)
         注:tutorbot/skills/lecture-* 是 TutorBot【对话答疑】侧的讲义专题 skill(prose 导航·数值回 RAG),与母题引擎解耦——母题引擎吃 _v8 chunk,不吃 lecture-* skill;但其易错/答题导航可当选题/挑误区的人工交叉验证
Phase 2  读 references/style-guide.md + 对应 references/type-<原型>.md → 填 schema(luban_diagram_microlesson.v1)
         旁白【不手写】,只在 narration.voice_hint 配音色(旁白由 Phase 3 从字段派生)
Phase 3  旁白预生成(do-once,见 references/narration-spec.md):node artifacts/luban_case_family_assets/diagram_microlesson/build_card_narration.mjs <card>.json
         → 按总纲从卡字段【派生】旁白(默认精简:点错 loss_display + 采分表达 scoring_expression)
         → 离线配音 + 朗读规范化 + ffprobe 量时长 → 预存 mp3(走 CDN,gitignore)+ timing.json(入库)
         生产换云 TTS 只改配音一环;运行时不实时合成。先 --print 校稿再配音
Phase 4  渲染:render_<原型>_card.py → 自动接同名 timing → 有声交互卡(旁白播放器 + <audio> + 时间轴同步:
         播到某段高亮/reveal 对应锚点 why/item/scoring/wrap)。数据驱动型参数→自动 SVG;构造/工序型用图元/手作 SVG
Phase 5  验收门:validate_schema_drafts.py 过 + video-first 静态预览合同门(validate_video_first_preview.mjs <topic>.rendered.html <topic>.practice.html)+ 学习舞台运行时门(validate_learning_stage_runtime.mjs <topic>.rendered.html,覆盖 390 竖屏/横屏/宽屏/theater)+ 闯关页运行时门(validate_challenge_theater_practice.mjs <topic>.practice.html,覆盖文字不裁切/SVG 标签不挤压/底栏不覆盖)+ 目标视口截图(cdp_shot.mjs,至少 390 竖屏 + 844 横屏 + 用户反馈视口)+ student-safe(不漏
         source_ref/E-code/采分点 id/schema/candidate)+ 采分点绑定对 + 不文生图 + 旁白派生自白名单字段
Phase 6  学员验证门:复用 artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu_product_validation_plan.md,KPI=同类题正确率提升;不过不铺量
```

## 原型选择指南(7 选 1,按"难在哪"而非章节)

| 原型 | 何时选(认知结构) | reference 文件 | schema body |
|---|---|---|---|
| ① 时序/工序 | 有先后顺序的流程/工序/验收 | `references/type-process_step.md` | `steps[]` |
| ② 构造/空间 | 节点/剖面/层次/空间关系 | `references/type-section.md` | `steps[]`(当前 SCHEMA 登记的 layer_section_reveal 承载;专用 `layers[]` 未登记前不得另造 body) |
| ③ 计算/图结构 | 可计算的图/网络/时间约束 | `references/type-graph.md` | `question_data{activities,dependencies,expected}` |
| ④ 判断/分支 | 条件→判断→结论(5 mode:链/分类/全要件/择一/角色链) | `references/type-decision.md` | `decision`(✅ J01,render_decision_card) |
| ⑤ 对比/正误 | 对错做法/规范vs非规范/通病 | `references/type-contrast.md` | `contrast_items[]`(草稿,见 artifacts/luban_case_family_assets/diagram_microlesson/C01) |
| ⑥ 采分点/诊断 | 答案×采分点逐点判读 | `references/type-diagnosis.md` | `diagnosis[]` |
| (七) 数值/记忆 | 定义/规范数值/参数辨析 | `references/type-value_memory.md` | **不动画化**:静态卡/表格 |

**懒加载**:每次只读 `style-guide.md` + 当前原型那一个 `type-*.md`;造 video-first 动画学习卡 / Remotion / 独立闯关页时读 `animation-production-director.md`;造有声卡时再读 `narration-spec.md`(旁白总纲);造完整母题闭环 / 教学动画时读 `teaching-animation-journey.md`(讲懂→闯关→看穿 + PPT 动画 + 防漂移闸 + 变题设计的完整规范)。不读全部(规模化不变慢,借 diagram-design 范式)。

## 红线(违反即返工)

1. **不文生图画构造图**(构造正确性必须确定性 SVG/图元库,LLM 不画构造)。
2. **采分点候选不冒充签发**:每个 `scoring_points[]` 必带 `kind`(`candidate_teaching_prototype` / 签发后才升),候选 `source_ref` 加"(教研草拟·候选·未签发)"后缀,`official_score_allowed` 不得 true。**`diagram_microlesson_compile::` 这类 ID 看着像签发,必须靠 kind + 后缀拆穿**。
3. **student-safe 靠白名单,不靠自觉**:卡内显式列 `rendering_contract.student_safe_fields` / `internal_only_fields`;学生端只渲染白名单,内部字段(`source_ref` / `error_code`(E03/E06) / `scoring_point` id / `kind` / `P10`/`P11` / `schema` / `candidate` / 母题包)只进 HTML 注释或后台。错因给学生看 `loss_display` 汉语名(如"位置判据缺失"),**绝不露 E-code**。(参考实现:`artifacts/luban_case_family_assets/diagram_microlesson/C01_construction_joint_contrast.schema_draft.json`)
4. **不上运行时图谱 DB**(前置/易混查 live adjacency 表,O(1);见记忆)。
5. **先讲后测**:讲解(①–⑥步)在前,小练/复测在后,对新生友好。
6. **运行时不实时 TTS / 不写 learner_state / 不接生产判分**,直到学员验证门过。旁白用**离线预生成音频**(do-once 存档、运行时只拉取播放,见 Phase 3 + `references/narration-spec.md`),**不在运行时实时合成**——这才是"预存复用"。
7. **旁白不手写,从卡字段派生**(卡是唯一源,见总纲):手写旁白=双份 truth,改卡会漂移、不可量产。schema 只配 `narration.voice_hint`。
8. **每条动效通向一次练习/反馈**,否则只是"看爽了"非"学会了"。
9. **不分裂 schema_version**:body 待定的原型先用 `<原型>_draft` 的 `template_type` 收口,沿用 `luban_diagram_microlesson.v1`,绝不为草稿另起版本号(同 D01/C01 模式)。
10. **复测/变题答案用单一 `answer` id**(正确选项 id),不用 `options[].is_correct`——泄漏面更小;`practice_options` 兼容(无 answer 回退 is_correct)。`answer` 必须属于 options(校验门拦)。静态卡答案在前端=训练自检、**非防作弊**(诚实标注)。
11. **判断走向校验要"沿 verdict 路径求实际 outcome 对比声明"**,不只查"指向存在";**改 schema 字段必须同步改 renderer 所有读点**(Codex 抓到过:改 answer 后 master 错题高亮仍读已删的 is_correct)。
12. **关键样板上线前过 Codex 对抗**:`codex exec --sandbox read-only` 同步(别放后台——会话恢复会丢 task);自审有盲点。调试钩子(`window.__demo` 类)收到 URL 门控,不留生产。
13. **教学动画旁白的考点事实必须 anchor 回卡字段**(防漂移闸):`claim:true` 的 beat/答疑段缺 anchor 或解析不到 `derived_from` 卡的真实字段,`build_lesson_narration.mjs` 直接报错退出。讲解口吻/类比/PPT 是包装层(`claim:false`),**事实层不许自由发挥**。
14. **看穿判定只读 master signal,不另造标准**(单一权威):真懂/背过的档由 `mastery_discrimination`(V2 边界 + V4 下限是关键鉴别题)定,渲染器只展示;看穿是鉴别候选,标"非正式判定,终判归 LearnerStateService"。
15. **讲懂幕用教学动画(画面随旁白逐点构建),不是静态翻页、不是纯播客对话**:纯双人播客=错方向(画面死)。正解=老师主讲 + 关键词卡 PPT 板书 + SVG 动 + 先讲后问答疑;完整学习必须接闯关(让学员做题)+ 看穿,一镜到底,不止于"讲"。
16. **闯关变题:同工程分档 + 换工程迁移,都要(换工程是 R4 明文 can_vary,不是雷区)**。闯关既要 ① 同工程换数值分档(上限/中间边界/下限),又要 ② **换工程考判据链迁移**(基坑→模板→脚手架)——只考一种工程**测不出**"会判据链"还是"背了那两个数",换工程恰恰是 R4_variable_rules 要求的、考"掌握不变量"的必要题。**迁移题题干给【该工程】阈值是合理的**:定位=考判据链会不会迁移,不考背模板/脚手架阈值(那是另一考点);配套讲懂必须有**迁移铺垫 beat**("判据链通用、阈值随工程")否则换工程会突兀。同工程分档题则**答前不泄阈值、答后 `feedback` 讲透**(考分档要靠自己判)。**反面教训**:曾因被质疑"模板题突兀"就动摇删掉它 + 写下"绝不换工程"的错红线——而模板支撑 6m 是 R3.formwork(≥5m 危大)明文派生的合法题,删它=没回依据验证(见红线17)。
17. **依据驱动,被质疑先回依据验证,不动摇就改**(本 skill 最重要的方法论):深母题引擎的全部价值=生成物可追溯到依据。每个 `variants` 必带 `basis_ref`(指向 R3 模板 / 规范 / source_ref);讲懂事实 anchor 回讲懂卡或 `master:R2/R3`(build_lesson 支持 `master:` 前缀回母题验证)。**被质疑时的正确动作**:回依据(R3/R4/规范)验证 → 站得住就**用依据解释/辩护**、站不住才改。**禁止**"用户一质疑就顺着改"——那是看人脸色、不是用引擎(踩过雷:模板题被质疑即删,没查 R3/R4)。
18. **母题引擎 = 离线造 + 预存 + 学生自助闭环,与鲁班 TutorBot 解耦**(架构边界,别搞混):母题引擎的"运行"是**去造**知识点/动画/题目 → **造好预存**(HTML 交互卡 + mp3 配音 + timing,走 CDN)→ **学生随时打开自助走** 讲懂→闯关→看穿;判分/看穿是**预存的确定性逻辑**(前端 JS + master signal),**不实时调 LLM**。**它不是给鲁班用的**:鲁班 TutorBot 是 Nexus-like + RAG 的**对话答疑**线,母题引擎不调 TutorBot runtime、不抢 judging/learner_state/ERROR_CODE_REGISTRY 权威(看穿只是预存自助鉴别候选·非正式判定)。落地不依赖 TutorBot 集成:预存物料 + 静态托管 + 小程序 web-view 即可。
19. **动画内容和数据基础必须来自母题引擎**:动画层不自由造题、不自由编采分句、不自由判掌握。先读 `master/card/variants/scoring_points/misconception/source_refs`,再写 storyboard;Remotion/HTML 只负责表达、运镜、交互和验证。缺母题数据只能做视觉小样,不能标"深母题学习卡"。
20. **video-first 首屏必须有 hook + poster + 中央播放**:不能黑帧、不能一上来直接讲知识内容、不能只有一个静态卡片。学生点播放前必须看见"为什么值得学"和学习收益。
21. **练习页独立且每题配图,但不能做标签题**:闯关不要混在讲解页里;每道题有原图/变化图/诊断图/答题纸,选项统一"对象/路径 + 结果 + 判断依据",最后至少一道采分句输出题;未答不能下一题。题面必须来自母题 R3/R4/采分点的真实场景缺口,不得把 `key_points` 直接当选项或题图答案;答前题图不能高亮正确选项,左上角/阶段标签不能泄露答案。每个错误选项必须有专属解析,讲清“为什么会选它、为什么扣分、正确采分动作怎么补”。
21a. **practice_blueprint 是闯关题的唯一源,不是生成器临场发挥**:每张精品卡在生成 practice 前,必须先从成品 MD 提炼 `practice_blueprint[]`。每题至少写明 `scene_gap`(学生/现场哪里错)、`visual_items`(答前不泄答案)、`options`(完整采分动作)、`option_feedback`(错项诱因/扣分/补法)、`basis_anchor`(R3/R4/R6/R8 或 scoring group)。没有 `practice_blueprint` 时,只能产 `coarse_draft_requires_review`,不得标 student-ready。结果页、AI 答疑和补练按钮不能补偿一开始题干/解析不可读的问题。
22. **视频必须有自然收尾**:最后 8-15 秒要回扣本卡主线、总结采分动作、桥接闯关。不能在答疑后直接结束,不能只靠页面 CTA 代替旁白收束。
23. **学习舞台比例必须先对,但不能锁死 9:16**:普通窗口采用 `orientation-adaptive / responsive learning stage`,根据手机竖屏、手机横屏、桌面宽屏和小程序 web-view 容器自适应。竖屏手机可优先接近 9:16/4:5,但横屏和宽屏必须扩大有效教学画面,不能把内容缩成小竖片。全屏只显示学习内容,不是网页缩放;点击屏幕才浮出播放/暂停/静音/退出、可拖动进度和章节跳转;控制层必须避开字幕/讲解卡,并考虑 `safe-area`。
23a. **手机预览不能给 localhost**:用户说“手机看/扫码看”时,`127.0.0.1` 和 `localhost` 只属于电脑本机,手机打不开。预览服务必须监听 `0.0.0.0` 或实际网卡地址,交付时给 `http://<LAN-IP>:8800/<file>`;若换 Wi-Fi,先重新取 `ipconfig getifaddr en0`/实际网卡 IP,并确认端口仍在监听。小程序 web-view 或扫码预览也不得写死 `127.0.0.1`。
24. **章节节点必须有语义标签**:不要只给 1/2/3/8。节点应是"先学/错觉/读图/顺推/逆推/时差/线路/采分"这类学习阶段,让学生知道点它会去哪。
25. **练习页可读性是硬门,不是美术建议**:所有题图/流程图/判断图的文字必须在图元内可读,不得把 4 字以上标签硬塞进小圆/窄框;题干、学生答、选项、反馈在竖屏/横屏/宽屏都必须 wrap 而不是裁切。发现这类问题要改 renderer 图元/布局/gate,不要只调当前卡 CSS。
26. **重新生成媒体后必须破缓存**:本地/小程序 web-view 容易缓存同名 mp4/poster/mp3;HTML 引用要带 mtime/hash 版本参数,否则手机端可能仍在看旧片。
27. **预览评审不重新生成 MP4**:如果只是给用户看 UI/UX、排版、文案、交互或学习卡效果,优先改 HTML/CSS/数据并用 Remotion still、CDP/Playwright 手机截图验收;可以复用已有 MP4 做播放源,但不要每次 full render 新 MP4。只有音画同步成片验收、媒体内容变化、正式候选/发布、缓存验证,或用户明确要视频文件时,才执行 `remotion render` + `ffprobe`。
28. **默认声纹只作为离线 TTS 生成参数,不能和现有音频脱节**:新生成/重配音时,老师/旁白默认 `longanhuan_v3`(龙安欢 V3),学生模拟默认 `longlaotie_v3`(龙老铁,东北男孩)。已有音频未重新生成时,不要只改 metadata 造成"标的声音"和 mp3 实际声音不一致。
29. **学生问答要匹配龙老铁声纹的人设**:学生追问默认是东北男孩口吻,可以自然使用"老师,我这么写能拿分不?""这块是不是..." "那我直接..." "整明白了,但..."这类口语化短句;每问只放 1-2 个口语标记,不得为了东北味变成段子、捧哏或刻板方言,也不得牺牲考点对象/依据/采分边界的准确性。
30. **教学动画问答结构必须先讲后问**:学生追问只放顶层 `qa[]`,不得塞进 `teach.beats[]` 打断主讲;有 `qa[]` 时默认至少三问三答,集中处理真实边界问题。每组 QA 必须有明确 `state` 映射到 IR scene(如 `qa_boundary`),closing 必须能显式指定 state(如 `closing_challenge`)。
31. **口癖是人物质感,不是节拍器**:老师可在 hook 和 closing 自然使用"注意哈/最后收束一句哈"之类口语钩子,但不得每个知识点都加。生成器/审稿时若老师口癖超过两处,先改旁白结构,不要让 TTS 把机械感放大。学生的东北口语也同理:只服务真实困惑和声纹贴合,不能每句堆口头禅。
32. **讲解中必须预留上下文答疑入口**:动画卡不是封闭视频。preview shell 应提供轻量 `Ask AI` slot,点击后暂停讲解,自动打包 `context_id + 当前 scene/focus/keycard/coach + 当前字幕 + safe_summary/key_points`。学生 HTML 只暴露安全上下文;完整母题 MD/source/basis_ref 由小程序/TutorBot 后端按 `context_id` 解析,不得把 raw MD、`source_ref`、candidate、采分点内部 id 注入学生端。未接小程序前,HTML preview 必须提供本地 preview answer/fallback,用于快速验证"学员提问→带上下文回答"的交互体验;正式答案权威仍在 TutorBot/后端 fat skill。
33. **用户截图暴露的问题必须变成 gate 或 anti-pattern**:如果人眼发现某个比例下文字贴边、右栏裁切、舞台拥挤,下一轮必须把该比例加入 runtime viewport 或截图墙,并补对应 renderer/gate 检查。只改当前卡坐标而不补 workflow 约束,不算改进。
34. **单卡精品闭环先过,再做下一张**:量产阶段也必须逐张验收。当前卡如果还存在“图示不足、题目读不懂、解析看不懂、手机打不开、答题没反应、结果页太浅”任一问题,不得把批量脚本产物当已交付。下一张卡只能在上一张完成 `source_card/practice_blueprint → 图示 storyboard → IR → renderer → gate → 手机 URL/截图 → 人审反馈` 后推进。

## 元规律(为什么这套成立)

所有成熟范例底层同一模式:**结构化 spec → 标注揭示参数 → 交互式逐步揭示**(爆炸图层参数 / 算法步进 / Grammarly span 标注 / scrollytelling step)。我们的 `schema → 确定性渲染 → reveal` 就是这个模式套到建筑实务。**别重新发明展现,重金投内容层。**

## 深母题层(卡 → 母题)

图解微课卡是**讲懂一个考点**的入口,**不是完整母题**。完整深母题 = 围绕一个考点的闭环,按《深母题数据标准 v1.0》(`docs/plan/鲁班移动端提分闭环/`)R1-R8 组织:

- **讲懂** `teaching_card_ref` 指向本卡(J01/F16…);**变题库** `variants`(同考点换工程/数值/判档,在 `variable_rules` 边界内);**误解模型** `misconception`(只发候选,终判归 `ERROR_CODE_REGISTRY`);**掌握鉴别** `mastery_discrimination`(看穿真懂 vs 背过,关键鉴别题=边界档+下限档;只发鉴别候选,不写 learner_state)。
- **运行时铁律**:只读 / 只发候选 / 不写结论——不抢评分(grading artifact)、学情(LearnerState)、错因(ERROR_CODE_REGISTRY)权威。
- **样板** `artifacts/luban_case_family_assets/diagram_microlesson/M_danger_work_expert_argumentation.master.json`(危大论证,首个完整深母题)。母题 `schema_version` 用 `*.sample.v0` **不冒充**生产 `case_family_structure.v1`(register-before-use:生产母题落 `artifacts/luban_case_family_assets/<id>/case_family.yaml`,待 schema 登记)。
- **量产扩包 gated on retention**(标准 §9):首样板未过留存证明前,不扩第 2 个母题包。首样板由 F16(防水)改为 **J01(危大论证)**,依据真题案例频次(危大第一高频)。

### video-first 动画学习卡 → 见 `references/animation-production-director.md`

N01 证明了一个更适合手机小程序预览的形态:先做**讲解视频首屏**(poster + 中央播放 + hook),用 Remotion 做真正动画和运镜,播放结束后再进入**独立闯关页**。它适用于后续所有需要"先抓注意力→讲懂→练会→采分表达"的考点。

- **数据权威 = 母题引擎**:master/card/variants/scoring/misconception/source 是内容源;动画只是可视化导演层。
- **讲解结构 = why hook → wrong idea → visual correction → process/logic → answer-paper score sentence → QA bridge**。
- **视觉结构 = 响应式学习舞台 + frame-driven camera + spotlight/dim + 多场景切换 + poster**。手机竖屏优先,但横屏/桌面要用两栏、侧栏、bottom sheet 等方式保住主教学焦点。
- **闯关结构 = 独立页面 + 每题 mini diagram/variation diagram + 递进题 + 采分句输出题 + 暖结果页**。
- **验收结构分两档**:预览评审=HTML/CSS + Remotion still/CDP 390px截图,不默认生成 MP4;成片验收=full render + ffprobe + 音画同步截图,只在音画同步、正式候选、发布或用户明确要视频文件时执行。

### 学习闭环 + 教学动画 → 见 `references/teaching-animation-journey.md`

卡之上的**完整学习旅程**(讲懂→闯关→看穿·一镜到底)+ **PPT 式教学动画**(讲懂幕)的完整规范、数据结构、操作步骤,沉淀在 `references/teaching-animation-journey.md`(造母题闭环时读它)。一句话路由:

- **闭环 = 单视图三幕·无缝流动自动推进**(讲完自动浮现闯关、答完自动滑入下一题、平滑滚动不跳顶);`artifacts/luban_case_family_assets/diagram_microlesson/render_archetype_journey.py` 读 master(顶层)组装,`render_master_view.py` 退为只闯关 deck。
- **讲懂幕 = 老师主讲 PPT 教学动画**(关键词卡逐条飞入成板书 + SVG 随旁白动)+ 先讲后问双人答疑;`artifacts/luban_case_family_assets/diagram_microlesson/render_teaching_animation.py` + `lesson.json` 的 `teach.beats[]` + `artifacts/luban_case_family_assets/diagram_microlesson/build_lesson_narration.mjs` 双人配音。
- **三条硬约束**(详见红线 13–16):教学动画旁白事实必 anchor 回卡(防漂移闸)/ 看穿判定只读 master signal 不另造 / 基础闯关同工程递进+题干不泄阈值。

## 混合考点兜底(Phase 0 引用)

很多考点不是干净的单原型(如"基坑支护"=构造②+判断④;"质量通病"=对比⑤+诊断⑥)。**不要为了凑 7 选 1 把考点硬切碎。** 规则:

1. **定主原型**:看"这题最难的那一步靠什么认知结构过"——它定唯一主 body,具体 body 以本表和 `SCHEMA.md` 当前登记为准,不得为了混合考点临时造第二套 body。
2. **次结构降级嵌入**:次要结构进辅助字段(如对比卡里嵌一句判断依据),不另开一套 body。
3. **真跨两类且都重**:拆成**卡组**("主卡 + 对比卡"按 `card_id` 串联),每张仍是单 body 的合法 v1 卡,而不是一张卡塞两套 body。

判据:一张卡 = 一个主 body。塞不下就拆卡,不是分裂 schema。

## 专家 panel 加固(2026-06-17)

三路只读专家(学习科学 / 单一权威+root-cause / 红队+生产边界)系统评审后,收敛出 6 个**真问题**(已按 less-is-more 过滤掉伪需求),修法已落到上面的 Phase / 红线,并由 `artifacts/luban_case_family_assets/diagram_microlesson/C01_construction_joint_contrast.schema_draft.json` 作为参考实现:

| # | 真问题(shared failure shape) | 修法落点 |
|---|---|---|
| ① | 混合原型无兜底——7 选 1 逼着把混合考点切碎 | Phase 0 + 上节"混合考点兜底"(主 body / 降级嵌入 / 拆卡组) |
| ② | student-safe 没机制保障(`dormant authority`:红线在,但无白名单兜它,renderer 照样漏 E-code) | 红线 3 改"白名单不靠自觉" + `rendering_contract` 双名单 |
| ③ | candidate 冒充签发(`source_ref` 像已签发;scoring_points 缺 kind) | 红线 2 + Phase 1:kind 必填 + 候选后缀 |
| ④ | 草稿 body 风险分裂 schema_version | 红线 8:`*_draft` template_type 收口,版本不动 |
| ⑤ | 采分点被 body / exam_binding 复制(第二份 truth) | Phase 1:scoring_points[] 定义一次,body 用 `*_binding` 引用 |
| ⑥ | ① 祖师爷 scrollytelling 水土不服(手机是 tab 不是长滚) | `references/type-process_step.md` 祖师爷已改 |

**代码 backlog 状态(把"纸面不变量"变成"运行时 fail-closed"):**

- ✅ **校验门去 dormant**:`artifacts/luban_case_family_assets/diagram_microlesson/validate_schema_drafts.py` 改**按 schema_version 内容自动发现**所有卡(删手维护清单),C01 不再被静默跳过——之前是 "3/3 OK" 假绿,现 4/4 真校验。
- ✅ **contrast 路径已 fail-closed**(对抗测试验证会咬):`detect_body` 认 `contrast_items` + body 四选一互斥;`check_contrast` 强制 `scoring_points[].kind` 必填 + `scoring_point_binding` 引用闭合(指向不存在的 id 即 FAIL)+ candidate 不得 `official_score_allowed`。
- ⏳ **render_card.py 学生端白名单**(接 renderer/接生产前必须清):学生端按 `rendering_contract.student_safe_fields` 渲染,错因输出 `loss_display` 汉语名而非裸 `error_code`(当前 F16 渲染路径会把 E-code 直渲到学生 HTML)。**无 contrast renderer 前不阻塞造卡**;在它落地前 student-safe 靠**人工对照 C01 的 `rendering_contract` 双名单**保障。
- ⏳ **kind/binding 校验推广到其它原型**(当前只在 contrast 路径强制;steps/network 仍按旧规则,避免误伤已绿的 F16/N01)。
- ✅ **decision 路径校验 fail-closed**(对抗验证):check_decision + render_decision_card.validate 沿 verdict 路径求实际 outcome 对比 reached_outcome + 通用 `practice.answer` 属于 options(篡改 reached_outcome/answer 均被拦)。
- ⏳ **master sample 独立校验**:validate_schema_drafts 只校验 `luban_diagram_microlesson.v1`,不校验 `*.master.sample.v0`(接生产前补 R1-R8 校验)。
- ⏳ **R1 原文 hash 锚定**:母题 `source_refs.content_sha256` 待补;阈值表量产前对规范原文逐条核(已标 candidate)。

## Codex 对抗加固(2026-06-18)

`codex exec --sandbox read-only` 同步对抗审查 ④判断渲染器 + 危大母题样板,找到 3 个**自审盲点**(均已修 + 对抗验证):

| Codex 发现 | 根因 | 修法 |
|---|---|---|
| 走向校验门有洞(篡改 reached_outcome / answer 仍过) | 只查"指向存在",没沿路径求实际 | 沿 verdict 路径求实际 outcome 对比 + answer 属于 options(红线 11) |
| master 错题高亮读已删的 is_correct | 改 answer 时漏改 renderer 读点 | 改读 `v.answer`(红线 11) |
| window.__demo 调试钩子留生产 | 截图钩子没清 | URL `?demo` 门控(红线 12) |

**教训**:自审会有盲点(走向校验我自己判 PASS,但没测"篡改 reached_outcome 是否被拦")→ 关键样板上线前**必过 Codex 对抗**,且用 `codex exec` 同步(codex-rescue 封装两次被截断/会话恢复会丢后台 task)。
