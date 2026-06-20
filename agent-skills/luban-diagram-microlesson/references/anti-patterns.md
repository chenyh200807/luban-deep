# anti-patterns.md · video-first 学习卡反例库

> 用途:把 N01/S01 迭代里已经发生过的问题沉淀成可迁移的失败模式。做新卡、复审旧卡、修播放器或练习页时先扫这里。
> 边界:这里只管表现合同和学习体验,不重判母题事实;母题事实仍由 master/card/variants/scoring/misconception/source 和 schema gate 负责。

## 1. 反例总表

| 失败形状 | 学生看到的症状 | 根因 | 修法 | gate |
|---|---|---|---|---|
| 大横框里套小竖屏 | 手机上视频很小,横屏/宽屏仍像窄条,全屏也像网页缩放 | HTML 壳把某个竖屏比例误当全局舞台 | 普通态用 orientation-adaptive 学习舞台:竖屏可接近 9:16/4:5,横屏/宽屏改两栏/侧栏/overlay;theater/fullscreen 只显示学习内容 | `validate_learning_stage_runtime.mjs` + 竖屏/横屏截图 |
| 全屏仍像网页 | 标题、卡片、按钮一起放大,注意力散 | 把页面全屏当播放器全屏 | theater fallback + Fullscreen API;点击屏幕才浮控制层 | runtime gate 检查 theater 几何、隐藏 chrome、控制层不遮挡 |
| 章节只写 1/2/3 | 学生不知道节点去哪 | 把内部 beat 序号当用户语义 | 用“先学/错觉/读图/顺推/采分”等短标签 | preview gate 检查非纯数字章节 |
| 预览每次都生成 MP4 | 迭代慢,缓存和成片误差混在一起 | 没区分预览评审和成片验收 | UI/UX/文案/练习/播放器只改 HTML/CSS/数据,复用已有媒体;成片变更才 render | 评审记录必须写明预览档或成片档 |
| 开头直接讲知识 | 新生跟不上,不知道为什么要看 | 缺 opening hook 和考试动作主线 | 首帧先讲考试场景、丢分点、学完能写什么 | storyboard 必填 `opening_hook` |
| 前言和正片断开 | 像几段拼起来的讲稿 | 没有统一的 `main_exam_action` | hook、trap、worked、score、closing 都回扣同一个考试动作 | storyboard 必填 `main_exam_action` / `closing_echo` |
| 画面像翻页 | 有动画但只是慢慢变大/淡入,没有注意力管理 | Remotion 只做转场,没做镜头调度 | 每 6-10 秒有教学相关 visual state;用 push/spotlight/dim/trace/freeze | still 检查 hook/trap/worked/score/closing |
| 大箭头硬指 | 箭头抢主体,显得粗糙 | 用装饰替代视觉层级 | 讲到哪个点,就让该对象高亮/放大/周边降噪;箭头只作轻量辅助 | 视觉复审 |
| 音画错位 | 旁白讲完了,画面才慢慢强调 | timing 不是从关键词设计 | 每段填 `sync_keyword` 和 `visual_state`;关键视觉略早 0.1-0.3s | 成片档 ffprobe + 关键帧截图 |
| 没自然收尾 | 答疑后突然结束,CTA 像硬跳 | closing 没进入 narration flatten/gate | `lesson.closing` 必须进入 segments,claim 必须 anchor | `build_lesson_narration.mjs --print` |
| 练习混在讲解页 | 学生一边看视频一边被题干干扰 | 没拆“看懂”和“练会”两个任务 | 讲解页只承载 video;练习页独立 | preview gate 检查 practice link |
| 练习题没图 | 选择题像普通刷题,没有深母题迁移 | 没把变题视觉化 | 每题配原图/变化图/诊断图/答题纸 | preview gate 检查 question SVG |
| 选项短词化 | 点对了但不会写主观题答案 | 选项只服务选择,不服务采分表达 | 选项写“对象/路径 + 结果 + 判断依据”;末题做采分句输出 | practice review |
| 题图文字挤压 | 流程节点/判断节点里字挤成一团,学生看不清 | 图元尺寸和标签长度没有合同,只测外层不溢出 | 改 renderer 图元语法:长标签用 pill/多行/缩写+图例,不要硬塞小圆;把标签适配纳入 runtime gate | `validate_challenge_theater_practice.mjs` 的 SVG label fit |
| SVG 标签压线/跑边 | 标签贴着箭头、压住卡片边框,或跑出白板 | 把标注当坐标文本,没有图元级安全布局;gate 只查外层 overflow,不查 text/text 或 text/path | flow_arrow 等 primitive 必须自带 label badge/line offset;renderer 负责避让,IR 不手调;gate 在 scene 后段检查 SVG text collision 和 arrow label clearance | `validate_animation_ir_preview.mjs` 的 `runtime_svg_text_collision` |
| 右栏文字被裁 | 横屏/宽屏时学生答或题干只显示半句 | grid 列宽/overflow 只测页面横滚,没测文本块 scrollWidth | 右栏设 min-width/minmax,文本 `overflow-wrap:anywhere`;gate 查 visible text block 不裁切 | `text_not_clipped` + 宽屏截图 |
| 只套 N01 外形 | 构造题也像网络图,判断题也像白板节点 | 把样板 UI 当 authority | 先按 6+1 选原型,再选该原型视觉语法 | pressure tests |
| 学生端泄漏内部词 | 页面出现 `candidate` / `source_ref` / `P10` / `E03` | renderer 没做 student-safe package gate | 学生包禁止内部 token;制作侧追溯放在源 JSON/后台 | preview gate fail-closed |
| 答疑入口裸塞母题 MD | 问 AI 能用,但 HTML/URL 里暴露原始资料路径、候选采分点或制作字段 | 把静态卡当成问答后端,没有 context handoff 边界 | 前端只发 `context_id + 当前 scene/caption + safe summary`;TutorBot/后端按 context_id 取母题 MD | `ai_ask_entry` + student-safe gate |
| 无母题数据也标深母题 | 画面漂亮但题和采分句不可追溯 | 表现层越权造内容 | 缺 master/card/variants/source 时只叫视觉小样 | skill 红线 + schema gate |
| CTA 过早或重复 | 开场就能跳闯关,学生跳过采分句;页面里同时有多个强 CTA | challenge 状态不是由 timing/scene 派生,而是常驻 UI | 默认 `challengeUnlockSec=score.start`;采分句前 CTA locked,采分句后 enabled;普通页去重,底部主行动承担闯关 | `validate_animation_ir_preview.mjs` 的 `runtime_challenge_unlock` |
| 固定播放器遮挡 | 360 竖屏或横屏时播放器盖住字幕、教练卡、采分句或 CTA | shell 用固定 bottom magic number,没有测量真实 player 高度 | `ResizeObserver` 写 `--player-h`;正文/theater 布局用该变量;横屏避免 fixed overlay 遮挡 | `runtime_player_occlusion` + viewport matrix |
| 字幕跟着图一起缩放 | 运镜时字幕/教练卡被 camera transform 带走,看起来晃或压图 | caption 被塞进 `.visual`,和施工图共用 transform | `.visual` 只放 SVG/图元;字幕放 stage overlay/live region;coach 是独立 slot | static a11y + screenshot |
| 控制层浮出压内容 | 点击全屏后播放器出来,字幕/教练卡和控制条叠在一起 | theater controls 是 overlay,但没有定义浮出时哪些内容让位/退出 | controls visible 时临时隐藏或让出 caption/coach;auto-hide 后恢复 | `runtime_theater_occlusion` |
| 只用 opacity 隐藏 | 元素看不见但还被 gate/点击层当作可见或遮挡 | 视觉隐藏和布局/命中语义混用 | 临时退出用 `display:none` 或明确 `aria-hidden/pointer-events`,不要只调透明度 | hit-test / occlusion gate |
| 先渲染后救火 | 页面出来才发现比例、叠层、Remotion 没吃同源 IR | 缺 pre-render contract gate,把 schema 问题拖到 UI 评审 | IR 生成后先跑 `validate_animation_ir_contract.mjs`;不过不渲染、不调 CSS | pre-render IR gate |
| Remotion 单卡另写一套 | HTML preview 变好了,正式成片又偏;或 topic TSX 里硬编码 F16 SVG | Remotion 成了第二份 storyboard/renderer truth | topic wrapper 只导入 IR/timing;通用 `AnimationIrRenderer` 消费 `visual_library/actions` | contract gate 查 wrapper 导入当前 IR + 委托通用 renderer |
| 机器绿但无评审包 | gate PASS 后仍反复被用户截图指出拥挤/错位/没动画 | 没把截图墙和人审发现回写成 root-cause triage,下一轮 agent 又只看命令绿灯 | 按 `workflow-review-loop.md` 形成 review packet;人眼发现的问题必须补 gate/anti-pattern 或标 needs_human_review | review packet + screenshot wall |

## 2. 快速判定

看到下面任一现象,先不要继续美化,先回根因:

- 你正在调颜色,但还说不清这张卡的 `main_exam_action`。
- 你正在改 Remotion 动画,但没有 `sync_keyword`。
- 你正在写练习题,但不知道它来自哪个 variant / basis_ref。
- 你正在加文案,但这句话没有 anchor 或只是老师自由发挥的考点事实。
- 你正在做全屏,但普通态竖屏截图里内容仍是小片,或横屏/宽屏截图里仍被锁成窄竖条。
- 你还没跑 `validate_animation_ir_contract.mjs`,就已经开始看 HTML 或改 CSS。
- 你在 Remotion topic 文件里写 `if (scene.id === "...")` 或硬编码某张卡的 SVG。
- 你只跑了静态 HTML gate,但没有跑 `validate_learning_stage_runtime.mjs` 的真实视口矩阵。
- 你只看 390x844,但没有看 360 窄竖屏、844/932 横屏和 theater 控制层。
- 你说 practice 合格,但没跑闯关页 runtime gate,没看目标视口截图,也没查 SVG 标签是否挤压。
- 你说 workflow 改好了,但没有 review packet,没有 root-cause triage,也没有说明新增了哪个 gate/anti-pattern。
- 你截图里发现文字挤压/裁切,但只调外层卡片大小,没有补 gate 或改 renderer 图元。
- 你发现 SVG 文字贴箭头/压边,但只调当前卡 x/y,没有把 flow_arrow/note/pill primitive 变成自带安全区的图元。
- 你加了"问 AI",但只是跳到空白聊天页,没有带当前 scene、字幕和考点上下文。
- 你发现问题后只改某张卡 CSS,却没有说明为什么不该沉淀到 renderer/gate/skill。
- 用户说“不满意”,你的第一反应是换视觉风格,而不是检查 hook、主线、节奏、练习闭环。

## 3. 修复顺序

1. 先修业务事实:这张卡到底训练哪一个考试动作。
2. 再修 authority:事实、题、反馈、看穿信号是否都来自母题引擎。
3. 再修叙事:hook、trap、worked、score、closing 是否一线贯穿。
4. 再修视觉:镜头是否替学生筛注意力。
5. 再修交互:播放器、全屏、拖进度、章节、闯关是否闭环。
6. 最后才修装饰:颜色、阴影、圆角、动效细节。

## 4. 一句话红线

不要用“更像精品”的视觉补丁掩盖结构问题。精品感来自:考试动作清楚、母题权威稳、音画对齐、画面帮学生看重点、练习证明能拿分。

## 5. 稳定化范式(成熟方案 = 范式,不是库)· 2026-06-19 三专家评审

**问题**:动画展示模块小问题多、不稳定。**结论:稳定不来自换库,来自"声明式 + 参数化 + 确定性渲染 + 视觉快照测试"这套范式。鲁班已做对大半(Remotion + 确定性 SVG + 离线配音 + 两道门),别引 Manim/Lottie/OpenMAIC(重依赖/AGPL/LLM 自由生成不可控,见 openmaic 评估 3/10)。**

**不稳定本质**:把本该确定性渲染的东西交给 LLM 自由发挥(几何/坐标/HTML/selector),又没在"生成↔渲染"边界设对账门。

**铁律**:
- **LLM 只填数据,绝不画几何**。坐标/布局/selector 由确定性渲染器算(`render_*_video_first.py` 的 `board_svg()` 是样板)。`validate_schema_drafts.py` 应加:card JSON 出现 x/y/width/`#id` 即 FAIL。
- **三道缺门**(把"小问题"从人眼打地鼠变 CI 红灯,均复用现有件、不引新框架):
  1. **selector 命中**:可点元素用 `data-id` 不用 `#id`;渲染后断言每个 teacher action/高亮 target 在 DOM 真命中(消灭"在动但指错"的静默失败——openmaic `byId{false}/byDataId{true}` 铁证)。
  2. **音画时长一致**:`mp3/mp4/timing.json` 三方时长 + 每 `claim` 段 `sync_keyword`/`anchor` 断言(新 `validate_timing_sync.mjs`),消灭尾部黑帧/错位。
  3. **视觉快照回归**:**只对每原型 fixture 的 golden 截图做 diff**(复用 `cdp_shot.mjs`,不引 Playwright),fixture 变了才报警;生产卡数据天然不同,不逐卡 baseline(less-is-more)。
- **收口而非重造**:抽 `stage_shell.py`(壳=合同 / 几何=参数分离),每 6+1 原型一个 `fixture.json`+golden;不为未来原型提前抽通用 motion 引擎。
- **Codex/外部产线接入 = 契约暴露,不是 skill 复制**:外部只交 card/lesson JSON,产物回本套渲染器 + `gate.sh`(schema→narration→preview→timing_sync→runtime)校验;**绝不把本 skill 复制出去**(第二份 authority 必漂移)。门的 FAIL message 即修正信号。
- anti-patterns 15 条:~9 条可全自动 gate,纯人工只剩镜头调度/箭头层级/采分表达质量(教学品味)。
