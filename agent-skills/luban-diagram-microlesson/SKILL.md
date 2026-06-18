---
name: luban-diagram-microlesson
description: Use this whenever you author, render, redesign, or review a 鲁班 diagram micro-lesson under artifacts/luban_case_family_assets/diagram_microlesson/ —— 单卡(F16 起鼓割补 / N01 网络计划 / C01 对照 / D01 诊断 / J01 判断)、**video-first 动画学习卡(Remotion/HTML,首屏hook→讲解视频→独立闯关)**或完整深母题学习闭环(讲懂教学动画→闯关→看穿)。触发于:新增 template_type / 卡 JSON / 母题 master / 讲懂 lesson;改 render_*.py/Remotion;做教学动画、运镜、配音、闯关变题、采分句输出题、看穿;修"一上来讲内容/画面静止翻页/没有声音/音画不同步/题目混在讲解页/练习没图/没有手机体验"。核心边界:动画内容和数据基础必须来自母题引擎(master/card/variants/scoring/misconception),renderer/Remotion 只表达不造权威;candidate 不冒充签发;学生端别露 source_ref/P编号/schema/candidate;看穿读 master signal 不另造。声明卡/母题/动画"做完了"之前必读。
---

# 鲁班图解微课 / 深母题学习闭环 (diagram_microlesson)

> **权威位**:本 skill 是造法的单一权威(已从 artifacts/.../skill_design 提升至此;skill_design 已退役)。
> **实现物料**全部在 `artifacts/luban_case_family_assets/diagram_microlesson/`(渲染器/脚本/样板卡/母题),本 skill 只装"怎么造"的规则,物料是 thin wrapper。
> **唯一目录**:`artifacts/luban_case_family_assets/diagram_microlesson/`。不新建第二套目录 / 第二个 schema_version / 第二份 skill。
>
> 配套实现(均在上述唯一目录):`SCHEMA.md`(schema 脊柱)、`render_card.py`/`render_network_card.py`/`render_contrast_card.py`/`render_decision_card.py`(原型渲染器)、`render_master_view.py`(深母题 deck 闯关)、`render_teaching_animation.py`(PPT 教学动画·讲懂幕引擎)、`render_archetype_journey.py`(**完整学习闭环·一镜到底**)、`render_network_video_first.py` + `remotion_demo/src/N01NetworkVideoFirst.tsx`(**N01 video-first 当前样板**)、`validate_schema_drafts.py`(校验门)、`build_card_narration.mjs`(单卡旁白派生)、`build_lesson_narration.mjs`(教学动画/双人配音+防漂移闸)、`cdp_shot.mjs`(零依赖手机截图)、脚手架卡 `F16_qigu.json`(①)/`N01_network_keypath.json`(③)/`C01_*contrast*.json`(⑤)/`J01_*argumentation*.json`(④)、讲懂脚本 `*.lesson.json`、母题样板 `M_*.master.json`(标 sample.v0,**生产 case_family 待 schema 登记**)。
> references:造卡读 `style-guide.md` + 对应 `type-*.md`;**造 video-first 动画学习卡/Remotion/独立闯关页先读 `animation-production-director.md`**;有声卡读 `narration-spec.md`;完整母题闭环/教学动画读 `teaching-animation-journey.md`;web-view 承载读 `wechat-webview-sandbox.md`;手机截图/DOM 断言读 `zero-dep-cdp-harness.md`。

## 这套 skill 解决什么

建筑实务考点很多,但**认知结构只有 6+1 种**。任何考点先归一个**展现原型**,再套该原型的 UI/SVG/交互 + 锚 authority 填 schema。**展现层站在成熟手艺的肩膀上(每原型有"祖师爷"),护城河在内容层(采分点/错因/authority)。**

**N01 之后的当前默认路线**:母题引擎数据 → 识别 6+1 原型 → 设计 video-first 讲解动画(先 hook 为什么学,再纠错/推演/采分) → 独立闯关页(每题有图/变化图,选项统一成"对象/路径 + 结果 + 判断依据",含采分句输出题) → 看穿/暖反馈。不要回到"静态卡 + 几个按钮"或"旁白播客 + 画面翻页"。

## N01 video-first 经验(2026-06-18,当前动画样板)

这轮 `N01_network_video_first.rendered.html` 的实际开发经验要成为后续默认标准:

1. **首屏先抓人,不是直接讲内容**:第一帧必须有完整 hook("为什么值得学 / 考试怎么拿分 / 常和哪些题连在一起"),poster 可读,中央播放按钮清楚。学生还没点播放就知道为什么要看。
2. **讲解页 video-first,练习页独立**:讲解页负责看懂;练习页负责闯关。不要把做题混在视频下面导致认知目标混乱。
3. **必须有声音和旁白节奏**:老师主讲用稳定音色,学生答疑另一个音色;音频离线生成,页面只播放。音画不同步时优先调画面节奏,让关键视觉略早于/贴合旁白关键词。
4. **Remotion 承担真实动画,HTML 壳承担交互**:动画要有推近、聚焦、暗化非重点、多页面/场景切换、答题纸 reveal;HTML 翻页或 CSS 假动效不够。
5. **运镜服务理解**:讲到 C 就推近 C,讲到路径就沿路径 trace,讲到采分句就切到答题纸;不要大箭头乱飞或一直锁在同一画面。
6. **练习题每题必须有图**:原图题有原图高亮,变化题有变化图,采分句题有答题纸/关键路径图。没有图的题会退化成传统刷题。
7. **选项统一成考试表达**:不是 A/B/C 短词,而是"路径/对象 + 工期/档位/结果 + 判断依据"。学生是在练答题语言。
8. **题目要递进**:原图识别 → 错觉鉴别 → 换数重算/迁移 → 时差/边界辨析 → 采分句输出。最后必须逼学生写出能拿分的一句话。
9. **播放结束后 CTA 变主行动**:讲完后顶部/底部主入口自动切到"开始闯关";未听完可保留次级入口,但不能抢主线。
10. **手机验收是硬门**:390px 首屏、播放、ended CTA、未答阻断、采分句判定、结果页都要跑。只看桌面浏览器不算完成。

细则读 `references/animation-production-director.md`;N01 是 ③计算/图结构原型的 video-first 样板,不是一次性实验。

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
Phase 5  验收门:validate_schema_drafts.py 过 + 手机 390px 无横滚(artifacts/luban_case_family_assets/diagram_microlesson/cdp_shot.mjs 截图)+ student-safe(不漏
         source_ref/E-code/采分点 id/schema/candidate)+ 采分点绑定对 + 不文生图 + 旁白派生自白名单字段
Phase 6  学员验证门:复用 artifacts/luban_case_family_assets/diagram_microlesson/F16_qigu_product_validation_plan.md,KPI=同类题正确率提升;不过不铺量
```

## 原型选择指南(7 选 1,按"难在哪"而非章节)

| 原型 | 何时选(认知结构) | reference 文件 | schema body |
|---|---|---|---|
| ① 时序/工序 | 有先后顺序的流程/工序/验收 | `references/type-process_step.md` | `steps[]` |
| ② 构造/空间 | 节点/剖面/层次/空间关系 | `references/type-section.md` | `layers[]`(待定) |
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
21. **练习页独立且每题配图**:闯关不要混在讲解页里;每道题有原图/变化图/诊断图/答题纸,选项统一"对象/路径 + 结果 + 判断依据",最后至少一道采分句输出题;未答不能下一题。

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
- **视觉结构 = 9:16 Remotion + frame-driven camera + spotlight/dim + 多场景切换 + poster**。
- **闯关结构 = 独立页面 + 每题 mini diagram/variation diagram + 递进题 + 采分句输出题 + 暖结果页**。
- **验收结构 = Remotion stills + full render + ffprobe + 390px Playwright/CDP**。

### 学习闭环 + 教学动画 → 见 `references/teaching-animation-journey.md`

卡之上的**完整学习旅程**(讲懂→闯关→看穿·一镜到底)+ **PPT 式教学动画**(讲懂幕)的完整规范、数据结构、操作步骤,沉淀在 `references/teaching-animation-journey.md`(造母题闭环时读它)。一句话路由:

- **闭环 = 单视图三幕·无缝流动自动推进**(讲完自动浮现闯关、答完自动滑入下一题、平滑滚动不跳顶);`artifacts/luban_case_family_assets/diagram_microlesson/render_archetype_journey.py` 读 master(顶层)组装,`render_master_view.py` 退为只闯关 deck。
- **讲懂幕 = 老师主讲 PPT 教学动画**(关键词卡逐条飞入成板书 + SVG 随旁白动)+ 先讲后问双人答疑;`artifacts/luban_case_family_assets/diagram_microlesson/render_teaching_animation.py` + `lesson.json` 的 `teach.beats[]` + `artifacts/luban_case_family_assets/diagram_microlesson/build_lesson_narration.mjs` 双人配音。
- **三条硬约束**(详见红线 13–16):教学动画旁白事实必 anchor 回卡(防漂移闸)/ 看穿判定只读 master signal 不另造 / 基础闯关同工程递进+题干不泄阈值。

## 混合考点兜底(Phase 0 引用)

很多考点不是干净的单原型(如"基坑支护"=构造②+判断④;"质量通病"=对比⑤+诊断⑥)。**不要为了凑 7 选 1 把考点硬切碎。** 规则:

1. **定主原型**:看"这题最难的那一步靠什么认知结构过"——它定 body(`steps[]` / `contrast_items[]` / `diagnosis[]` 三选一,互斥)。
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
