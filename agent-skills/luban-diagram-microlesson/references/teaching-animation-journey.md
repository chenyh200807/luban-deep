# teaching-animation-journey.md · 教学动画 + 完整学习闭环(讲懂→闯关→看穿)

> **这是"展现原型(6+1)"之上的一层:把一个考点造成一段【一镜到底的学习旅程】。**
> 单张图解微课卡只"讲懂一个考点";完整学习 = 讲懂 → 闯关(让学员做题)→ 看穿(真懂 vs 背过)。
> 配套实现:`artifacts/luban_case_family_assets/diagram_microlesson/render_teaching_animation.py`(讲懂幕引擎)、`artifacts/luban_case_family_assets/diagram_microlesson/render_archetype_journey.py`(闭环·一镜到底)、`artifacts/luban_case_family_assets/diagram_microlesson/build_lesson_narration.mjs`(双人配音+防漂移闸)、`artifacts/luban_case_family_assets/diagram_microlesson/J01_...lesson.json`(讲懂动画脚本)、`artifacts/luban_case_family_assets/diagram_microlesson/M_..._master.json`(深母题顶层)。

## 0. 形态结论(踩过的雷 → 正解)

| 错方向(试过/想当然) | 为什么错 | 正解 |
|---|---|---|
| 旁白讲、画面静止 | 没"教"的过程,人不被拉进来 | **PPT 式**:旁白讲到哪,关键词卡飞入 + 图形动,像老师边讲边写板书 |
| 纯双人播客对话(一上来俩人闲聊) | 只动声音、画面死、没系统讲解 | **老师主讲教学动画 + 先讲后问答疑**(讲完学生才问) |
| mp4 成片 | 不可交互 | 交互卡 + 预存配音 + SVG 时间轴(可暂停/重播/点步) |
| 只"讲"完就结束 | 做了变题库却不让学员做题,不算闭环 | 讲完**接闯关 + 看穿**,一镜到底 |
| 三幕靠按钮整屏切 + 跳顶 | 体感"三个独立环节拼一起",不连贯 | **无缝流动自动推进**(讲完自动浮现闯关、答完自动滑入下一题、平滑滚动不跳顶) |

## 1. 三层数据架构(单一权威)

```
master.json(深母题顶层·数据权威)
  ├─ teaching_lesson_ref → lesson.json(讲懂层:教学动画脚本)
  │                          └─ derived_from → J01 卡(考点锚:判据/采分/错因)
  ├─ variants[]            → 闯关题(同考点变题)
  └─ mastery_discrimination → 看穿判定 signal + 暖反馈
```

- **master 是顶层**,闭环渲染器读它,据三个引用组装三幕。`render_master_view.py` 退为"只闯关 deck 轻量版"。
- **两个渲染器读同一 master 数据 = 单一权威**(数据是权威,渲染只展示)。
- 母题 `schema_version` 用 `*.sample.v0` 不冒充生产 `case_family_structure.v1`。

## 2. ① 讲懂幕:PPT 式教学动画

### 2.1 数据:`lesson.json` 的 `teach.beats[]`

每 beat = 一句旁白 +(可选)图形动作 +(可选)关键词卡:

```json
{"id":"gate3_crit", "stage":"gate3", "claim":true, "anchor":"decision.judgment_points[0].criterion",
 "keycard":{"text":"判据①  开挖 ≥ 3m(或<3m但复杂)= 危大", "tone":"a"},
 "narration":"第一道判据:基坑开挖深度大于等于三米,就属于危大;就算不到三米,地质复杂、周边有建筑,也算危大。"}
```

- `stage`:图形动作 state(`intro/dig/gate3/gate5/conclude`,**不写则继承上一 beat**,画面不回退)。
- `keycard`:关键词卡飞入,`tone` ∈ `q`(问/题面·蓝)/`a`(判据·绿)/`concl`(结论·金)/`score`(采分·橙),按 beat 顺序累积成"板书"。
- `qa[]`:讲完后的**双人答疑**(先讲后问:老师系统讲透 → 模拟学生问真困惑 → 老师答疑再钉考点)。

### 2.2 SVG 舞台 state 机制

舞台元素全画好,初始隐藏;JS 按 timeline 给 `.stage` 设累积类 `reached-intro reached-dig …`,CSS `.reached-gate3 .line3m{opacity:1}` 累积揭示;深度条用 `transform:scaleY` 生长、阈值线/标签 `opacity` 淡入。**构造正确性靠确定性 SVG/图元,不文生图。**

### 2.3 旁白配音:`build_lesson_narration.mjs`

拍平 `beats` + `qa` 成有序音频段 → 按 `speaker` 切音色(老师/学生两个 voice)→ 一条 mp3 + timing(段带 `state`/`keycard`/`kind`)。运行时按 timing 同步:切 SVG state + 飞 keycard + 高亮答疑气泡。`--print` 先验闸看稿。

**音色**(macOS `say`):老师=`Tingting`、学生=`Meijia`(都女声,靠音色+左右气泡+名字区分)。⚠ **Mac 新 Siri 男声全坏**(Eddy/Flo/Reed 等生成 0.015s 空文件),可用只有 Tingting/Meijia/Lili/Han;接 CDN 级 TTS 时再换男声。

### 2.4 防漂移 anchor 闸(硬约束·与纯派生旁白的区别)

> 单卡播放器旁白走 [[narration-spec]] 的**纯派生**(固定模板、全字段、无创作);教学动画/双人旁白是**作者撰写 + anchor 闸**:讲解口吻/类比/PPT 是创作的(有趣、拉人),但**事实层必须可追溯**。

- 每个 `claim:true` 的 beat/答疑段**必须带 `anchor` 且能解析到真实依据字段**(`resolveAnchor` 支持 `a.b[0].c` 数字下标 + `arr[id].field` 按 id 匹配)。
- 依据源:默认 `derived_from` 讲懂卡;**讲懂的迁移铺垫等事实(依据在母题不变量)用 `anchor:"master:R2_invariant"` 回 `archetype_master_ref` 验证**(build_lesson 支持 `master:` 前缀)。一切事实可追溯到卡或母题。
- `build_lesson_narration.mjs` 配音前自动校验,**解析不到即报错退出**——不让"听感有趣"掩盖"事实漂移"。
- 纯口语黏合(打比方、捧场、过渡)标 `claim:false`,**不许含考点事实**。
- 效果:既能用对话/类比/板书把人拉进来,又候选诚实、考点全部 traceable 回卡。

## 3. ② 闯关幕:变题设计(红线)

- **两类题都要,每题挂 `basis_ref`**:① 同工程换数值**分档**(上限/中间边界/下限);② 换工程**迁移**(基坑→模板→脚手架)。只考一种工程测不出"会判据链"还是"背了那两个数"——换工程是 `R4_variable_rules.can_vary` 明文要求、考"掌握不变量"的必要题。每个变题 `basis_ref` 指向 R3 模板/规范,可追溯(红线17)。
- **分档题:答前不泄、答后讲清**:同工程分档要靠自己判,题干和选项(答前可见)不出现阈值数字——选项写"危大且超过一定规模",不写"≥5m";答后 `feedback`/`basis` 把判据(含阈值)讲透。
- **迁移题:题干给【该工程】阈值是合理的**:定位=考判据链会不会迁移到新工程,不考背模板/脚手架阈值(那是另一考点)。**前提**:讲懂幕必须有**迁移铺垫 beat**("判据链通用、阈值随工程",anchor `master:R2_invariant`),否则换工程会突兀(踩过雷:模板题无铺垫=被嫌突兀;但删它更错=没回依据)。
- **留鉴别梯度**:上限(需论证)+ **中间/边界陷阱**(危大未超规模)+ **下限**(未达危大)+ **迁移**(换工程)。关键鉴别题选"中间档边界 + 换工程迁移"(最区分真懂 vs 背原题)。
- **即时反馈钉判据**:答完显示对错 + `feedback` + `basis`(判据)+ `tier_tag`(档位)。

## 4. ③ 看穿幕:判定读 master signal(单一权威)+ 暖

- **判定只读 `mastery_discrimination` 的 signal,渲染器不另造标准**:关键鉴别题(中间档边界 + 下限)由 master 定;全对=真懂、关键鉴别题都错=背过、差一道=就差一步。
- **暖反馈用 `warm_feedback` 三档原文**,先捧→指出就差哪一步→给路不羞辱(背过文案"先别急着背,回判断流走一遍,走顺了换什么数值都不慌"),绝不毒舌(见 [[wow-see-through-must-be-warm-not-harsh]])。
- **诚实边界**:看穿是**鉴别候选**(`official_score_allowed=false`,终判归 LearnerStateService),文案标"自测看穿,非正式判定";student-safe 只渲 stem/options/feedback/warm。

## 5. 连续流引擎(无缝自动推进)

- 三幕在**一条流**里,后续幕初始 `.seg` 折叠隐藏(`max-height:0;opacity:0`),到点 `openSeg`(平滑展开)+ `flowTo`(scrollIntoView smooth)。
- 推进自动:讲懂音频 `ended` → 老师桥接"来出4道考考你" → 闯关自动浮现;答完一题反馈深入、`setTimeout`(答对~1.7s/答错~2.6s)自动滑入下一题;4题完自动滑入看穿。讲懂播放器进闯关时淡出(`.player.hide`)。留一个不显眼的"直接闯关"小入口。
- **红线:幕间过渡禁用整屏 `display` 互斥 + `scrollTo(0,0)` 跳顶**——那是"切"不是"流",踩过雷。旧内容留上方可回看。

## 6. 造一个教学动画闭环 · 操作步骤

1. 先有**讲懂卡**(J01 等,考点锚:判据/采分/错因,student_safe 双名单)。
2. 写 `<card>.lesson.json`:`teach.beats[]`(PPT 逐点,每 beat 旁白 + stage + keycard,`claim:true` 配 anchor)+ `qa[]`(先讲后问答疑)+ `speakers`。
3. `node build_lesson_narration.mjs <lesson>.json --print` 验防漂移闸 + 看稿 → 去掉 `--print` 配音(出 mp3 + timing,mp3 走 CDN/gitignore)。
4. 在 `master.json` 加 `teaching_lesson_ref` → lesson;`variants` 含同工程分档 + 换工程迁移、每题挂 `basis_ref`;`mastery_discrimination.key_discriminator_ids` 标关键鉴别题。lesson 加 `archetype_master_ref`,迁移铺垫 beat anchor `master:R2_invariant`。
5. `python3 render_archetype_journey.py <master>.json` → 一镜到底闭环 HTML。
6. 验收:`cdp_shot.mjs` 截三幕 + 手机 390px 无横滚 + 分档题题干无阈值泄露(`grep '≥\d+m'` 分档题题干应空,迁移题可给该工程阈值)+ student-safe + 连续流(无整屏切/跳顶)+ 每变题有 `basis_ref` 可追溯。

## 6.5 引擎对原型通用(F16 复刻验证)

用本 skill 把 J01(判断类④)的闭环复刻到 **F16 防水起鼓割补(工序类①)**,暴露并修掉 3 处"J01 专用硬编码",引擎才真通用——复刻别考点时照此检查:

| 暴露点 | J01 专用写死 | 通用化 |
|---|---|---|
| **舞台 SVG** | `_svg()` 硬编码基坑剖面 + `STATE_ORDER` 固定 | 外置到 `lesson.stage`(svg + states + css + banner);`ta.stage_spec(lesson)` 读它,无则回退基坑。F16 自带屋面剖面工序舞台。 |
| **关键鉴别题** | `vidx("V2")/vidx("V4")` 按前缀写死 | 外置到 `master.mastery_discrimination.key_discriminator_ids`;渲染器读 id 列表(回退 V2/V4 前缀)。F16=`["W1_miss_closure","W4_no_test"]`。 |
| **分镜点** | 一 state 一 beat(J01 恰好),按 beat 出点 | 按 **state 去重**出点(F16 intro/conclude 各 2 beat,否则点重复)。 |
| **变题依据** | 变题无可追溯依据字段 | 每个 `variants` 加 `basis_ref`(指向 R3 模板/规范),被质疑一键回依据验证(红线17)。 |
| **讲懂事实依据** | anchor 闸只回 `derived_from` 讲懂卡 | 支持 `anchor:"master:R2_invariant"` 回 `archetype_master_ref` 验证——迁移铺垫等事实的依据在母题不变量。 |

**方法论教训(红线17 的由来)**:用户质疑"模板支撑 6m 这道题",我没回 R3/R4 验证(R3.formwork 明写≥5m 危大、R4 明许换工程),被质疑就动摇删了题、还写下"绝不换工程"的错红线。**正确动作=回依据验证,站得住用依据辩护、站不住才改**。"被质疑即顺着改"=看人脸色,不是用引擎。

**工序类 vs 判断类的内容差异**(骨架同、填法不同):
- 不变量:判断类=两级判据链(数值阈值);工序类=修补闭环结构(治病因→恢复防水→检验)。
- 闯关:判断类=换数值判分档;工序类=**找漏点 / 判顺序 / 换部位迁移 / 检验闭环**(直接用 F16 的 common_errors 当鉴别题素材)。
- 看穿:判断类关键鉴别题=边界档+下限档;工序类=**最易漏的中间闭合层 + 收尾检验**。
- 防漂移 anchor 闸、PPT keycard、双人答疑、连续流引擎 **零改动复用**。

## 7. 红线 checklist(汇总,对应 SKILL.md 红线 13–17)

- [ ] 13 教学动画旁白 `claim:true` 段 anchor 回卡字段,配音前过闸(解析不到报错)。
- [ ] 14 看穿判定只读 master signal,不另造;标"鉴别候选·非正式判定"。
- [ ] 15 讲懂用教学动画(画面随旁白逐点建)非静态翻页/纯播客;闭环必接闯关+看穿。
- [ ] 16 闯关含同工程分档 + 换工程迁移(换工程是 R4 要的);分档题题干不泄阈值、迁移题给该工程阈值+讲懂铺垫。
- [ ] 17 每变题挂 `basis_ref` 可追溯;被质疑先回依据(R3/R4/规范)验证,不动摇就改。
- [ ] 连续流:无缝自动推进,禁整屏切 + 跳顶。
- [ ] student-safe + 候选诚实 + 暖(不毒舌)。
