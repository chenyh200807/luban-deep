# learning-stage-shell.md · 学习舞台模板与运行时验收

> 用途:防止每张动画学习卡手写一套播放器/全屏/横竖屏布局,导致细微 CSS 或内容变化就出 bug。
> 原则:thin wrapper and fat skills。HTML 壳是薄 wrapper,只承载稳定交互和布局;考点事实、题目、反馈、看穿信号仍来自母题引擎和本 skill。

## 1. 先套成熟结构,不是套皮肤

可以复用的成熟方案不是某个 App 的视觉样式,而是学习交互闭环:

1. **先让学生做一个小动作**:判断、点对象、拖步骤、选错因、补采分句。
2. **马上给反馈**:指出错在对象、时点、阈值、顺序、边界还是表达。
3. **用动画解释这个反馈**:镜头服务刚才的错误或疑问,不是先播一段完整知识点。
4. **再给更难一档的题**:同结构变化、边界、迁移、输出采分句。

判断/放行类卡优先 `decision-first`;计算/构造/流程类卡才优先 `video-first`。不要把所有考点塞进同一个竖屏视频皮肤。

## 2. Learning Stage Shell 固定槽位

每张可预览学习卡只允许填下面这些槽位,不要每张卡重写播放器结构:

| slot | 用途 | 内容来源 |
|---|---|---|
| `mode` | `decision-first` / `video-first` / `process-first` | 原型选择和主考试动作 |
| `stage` | 主图、白板、判断树、剖面、网络图、答案扫描 | card/master/lesson beat |
| `coach` | 当前一句讲解、反馈、采分句 | timing segment / quick feedback |
| `quick_action` | 首屏小判断、小选择或播放按钮 | 认知动作,不是装饰 |
| `score_atoms` | 人证/试吊/路径/依据等采分原子 | scoring_points / teaching_spine |
| `transport` | 播放、暂停、静音、进度、章节 | 壳统一实现 |
| `chapter_nav` | 语义节点,如先学/错觉/试吊/采分 | lesson video_beats |
| `challenge_cta` | 看完后闯关/开始闯关 | independent practice |

稳定壳负责:

- 竖屏普通态。
- 横屏/宽屏两栏态。
- theater/fullscreen 态。
- 控制层点击浮出。
- 可拖动进度和语义章节。
- 播放结束后 CTA 变成闯关。
- player 高度运行时测量,不得写死 124/132px 之类 magic number。
- 采分句前闯关 CTA 只能 locked/弱提示;采分句后才 enabled/主行动。

稳定壳必须暴露机器可校验 hooks,不要靠 class/id 默契:

| hook | 用途 |
|---|---|
| `[data-card-id]` | 当前学习卡/母题包稳定 id |
| `[data-stage-shell]` | 学习舞台壳边界 |
| `[data-beat-id]` | beat 级讲解/卡片节点 |
| `[data-action-id]` | `animation_action[]` 渲染后的动作节点 |
| `[data-visual-node-id]` | `data-id:<target>` 的 DOM 命中目标 |
| `[data-practice-id]` | 练习题/变题节点 |
| `window.__LUBAN_LESSON_MANIFEST__` | renderer 输出给门禁/调试的结构化 manifest |

`data-visual-node-id` 可以包含多个空格分隔 id,但不得把 `source_ref`、采分点内部 id 或 taxonomy code 暴露给学生端。`animation_action[].target` 只能命中这些 `data-*` hook,普通 DOM `id` 不算命中。

`window.__LUBAN_LESSON_MANIFEST__` 只能放 presentation action wiring,不得放 `schema_version`、`source_ref`、`scoring_point`、E-code、P-code、candidate 等制作侧/内部 token。资产级 schema/hash 放 `card_bundle_manifest.json`,不要注入学生 HTML。

内容层只负责:

- 这一 beat 的画面状态。
- 这一句讲解或反馈。
- 当前高亮哪个对象/采分原子。
- 练习题和反馈。

## 3. 三个标准布局

### 3.1 竖屏普通态

- 首屏先出现 hook 或 quick_action。
- stage 不能小片化,可接近 4:5 或 9:16,但不是强制。
- 控制层未播放前默认隐藏;播放后可 sticky 或位于底部。
- 如果是 `decision-first`,学生不用全屏也能完成第一次判断。

### 3.2 横屏/宽屏普通态

- 左侧是大 stage。
- 右侧是 coach、score_atoms、transport、challenge_cta。
- 不允许仍然显示窄竖条。
- 右栏内容要服务当前动作,不是堆满说明文字。

### 3.3 theater/fullscreen 态

- 只显示学习内容和浮动控制层。
- 页面标题、rail、普通 caption、nav 必须隐藏。
- 点击画面浮出 controls;controls 不遮住主 stage。
- 退出后回到普通态,不丢 currentTime。

## 4. 运行时验收矩阵

静态 gate 只能检查“有没有”;布局 gate 必须检查“真实视口里是否成立”。每张学习卡预览至少跑:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/<topic>.rendered.html
```

该 gate 覆盖:

1. `portrait_initial_decision`:390x844,首屏 decision/hook,center play 或 quick action 可见,controls 不抢屏。
2. `portrait_playing_trial`:390x844,播放态,stage 不塌,controls/章节/进度可见。
3. `landscape_playing_trial`:844x390,横屏播放态,stage 必须横向展开,不能是小竖片。
4. `wide_playing_trial`:1024x720,桌面宽屏态,stage/右栏比例合理。
5. `portrait_theater_controls`:390x844,theater 控制层可见,stage 从视口顶端开始,controls 不覆盖主 stage。

每个状态都必须检查:

- 无水平溢出。
- `.lesson` 声明 `orientation-adaptive`。
- `.stage` 可见且占视口比例达标。
- 横屏/宽屏下 `.stage` 宽高比不能像窄竖条。
- theater 下隐藏页面 chrome。
- controls 高度不过载,不压住主 stage。
- 固定播放器不得遮挡 `.visual`、字幕、教练卡、采分句或 CTA。
- 可见按钮/链接/range 命中盒不小于 44px。
- 字幕必须是独立 live region,不要挂进 `.visual` 跟着 camera transform。
- 闯关 CTA 必须由 timing/scene 派生 unlock;采分句前 locked,采分句后 enabled。
- seek 回旧 scene 时,旧 scene 节点不得继续可见。

独立练习页也必须走真实视口 gate,不能只被 `validate_video_first_preview.mjs`
静态扫过。默认命令:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_challenge_theater_practice.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/<topic>.practice.html
```

该 gate 至少检查:

- 360/390 竖屏、844 横屏、以及一个宽屏/桌面视口。
- 题图/SVG 内部标签适配图元,不得把文字挤进过小节点。
- 题干、学生答、选项、反馈不裁切;长文必须换行或进入渐进展开。
- 导航/底栏在文档流或有明确让位,不得覆盖选项和反馈。
- 可见交互命中盒不小于 44px。
- 机器门 PASS 后必须补目标视口截图;若用户反馈来自某个特殊视口,该视口加入下一轮 gate 或截图证据。
- 章节不是纯数字。
- 可见按钮文字不明显溢出。

## 5. 自查机制分层

不要把所有验收塞进一个脚本:

1. `validate_schema_drafts.py`:母题/卡 schema 和基础事实结构。
2. `validate_animation_action_schema.py`:现有 v0 lesson 的 `animation_action[]` 白名单与 `data-id:` target 形状。
3. `validate_animation_ir_contract.mjs`:animation_ir.v0 的 scene/action/visual_library/student-safe/Remotion 同源 **渲染前**合同。
4. `build_lesson_narration.mjs --print`:旁白 claim anchor、closing、音频生成前文本。
5. `validate_timing_sync.mjs`:总时长 + `sync_keyword` 覆盖,并命中对应 timing 段文本/keycard。
6. `validate_data_id_targets.mjs`:lesson `animation_action[].target` 在 rendered HTML 中命中。
7. `validate_video_first_preview.mjs` / `validate_animation_ir_preview.mjs`:静态表现合同、IR→HTML 等价、student-safe、独立练习页、章节、practice link、CTA 解锁。
8. `validate_learning_stage_runtime.mjs`:真实视口布局、横竖屏、通过真实 `[data-theater-toggle]` 进入 theater、控件遮挡。
9. `cdp_shot.mjs` + Remotion still:留下人工复审截图;关键帧至少看 hook/trap/worked/score/closing。
10. `workflow-review-loop.md`:把 gate 输出、截图墙、人审/LLM judge、root-cause triage 和回炉层级记录成 review packet。
11. `build_card_bundle_manifest.py`:bundle-root 相对路径 + master/lesson/timing/rendered/practice/audio hash;成片档才跑 Remotion render + ffprobe + 音画同步截图。

如果第 3 层没过,不要继续调文案、颜色或题目。先修 IR/renderer contract。

J01 当前确定性壳验收命令:

```bash
artifacts/luban_case_family_assets/diagram_microlesson/gate.sh J01
```

这个命令不生成 MP4;它验证当前 journey HTML 的 schema/action/timing/data-id/runtime,生成 independent practice HTML,跑 practice preview gate,并生成 non-authoritative bundle manifest。

## 6. Definition Of Done

一张卡“可以给用户看下一轮”必须同时满足:

- 选对 6+1 原型和入口模式。
- 首屏能让学生知道为什么学、先做什么。
- 普通竖屏、横屏/宽屏、theater 三种布局都过 runtime gate。
- 练习页独立且题目有图。
- 练习页文字和图元标签通过 runtime 可读性 gate。
- preview 阶段不重新生成 MP4。
- 截图人工看过,没有明显小片化、遮挡、文本挤压和无意义空白。
- review packet 已记录 gate、截图、发现、root-cause triage 和修复层级。

## 7. 反复出 bug 时的处理顺序

1. 先问是不是壳被每张卡重写了。
2. 再问是不是 slot 越界:内容层在改 transport/theater/grid。
3. 再问 runtime gate 是否覆盖了出问题的真实状态。
4. 最后才改局部 CSS。

如果只能通过给某张卡加特殊 CSS 才能过,默认说明模板不够好;优先改 Learning Stage Shell,不要积累 per-topic 补丁。
每次修复要记录 root-cause triage:`symptom / shared_failure_shape / one_authority / broken_contract / fix_layer / new_gate_or_antipattern`。没有新增 gate 或 anti-pattern 的重复 bug,默认还没修到根上。
