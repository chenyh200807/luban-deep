# animation-production-director.md · 鲁班深母题动画学习卡量产导演

> 目标:把母题引擎的数据资产变成手机端可学习、可闯关、可看穿的高质量动画交互内容。
> 本文件是 `luban-diagram-microlesson` 的动画量产导演层。它不新增内容权威,只规定如何把母题引擎的权威数据投射成讲解动画、白板运镜、练习和反馈。
> 配套必读:`video-first-pressure-tests.md` 用来跨原型压测,`anti-patterns.md` 用来对照已踩坑。入口 `SKILL.md` 只负责路由,本文件才是 video-first 细则。

## 0. 第一原则:母题引擎是内容权威

动画不是自由编剧。动画内容和数据基础必须来自母题引擎:

- `master.json` / case family:考点不变量、变题边界、mastery_discrimination、看穿信号。
- `teaching_card_ref` / diagram card:错觉、视觉纠正、采分句、讲解 spine、student-safe 字段。
- `variants[]` / quiz data:同考点变题、迁移题、边界题、basis_ref、标准答案和反馈。
- `scoring_points[]` / score_atoms:采分关键词、命中/漏点/部分命中,候选或签发边界。
- `misconception` / trap_alert / error model:学生常见错因和错误表达。
- `source_refs` / R1-R8:教材、规范、真题、讲义 chunk、变量规则和证据锚。

**硬规则**:

1. 先读母题引擎数据,再写脚本和画面。没有 master/card/variant/mastery 数据的动画,只能叫视觉小样,不能叫深母题学习卡。
2. 动画层只能做表达、运镜、节奏、交互和反馈呈现,不得新增考点事实、阈值、采分规则或掌握判定。
3. 每个讲解事实必须能回到 `card` 或 `master` 的字段;每道闯关题必须能回到 `variants[]` 或 quiz data;每个看穿结论必须读 `mastery_discrimination`。
4. 当视觉效果和数据权威冲突时,删视觉效果。不能为了好看改判据、改路径、改阈值、改采分句。
5. 候选数据必须诚实:student 端不露 internal id/source_ref/schema/candidate 字样,但制作侧必须保留追溯链。

## 1. 生产前四问

每次做动画前先写清楚:

1. `考点难在哪`:是顺序、构造、计算、判断、对比、采分诊断,还是纯数值记忆?
2. `母题引擎给了什么`:读到哪些 master/card/variants/scoring/misconception/source 字段?缺什么?
3. `这一段动画要改变什么`:纠正一个错觉、建立一个判据链、演示一次计算、暴露一个丢分点,还是训练一句采分表达?
4. `看完立刻考什么`:每条动效后面对应哪道练习或输出题?没有练习落点的动效要删。

### 1.1 decision-first 优先级

如果考点的核心动作是"判断能不能 / 属不属于 / 要不要 / 该不该放行",不要默认做成看完视频再做题。先判断它是不是 `decision-first`:

- **适用**:`decision_branch_reveal`、安全放行、验收判断、危大分档、合同/索赔成立、事故等级等。
- **首屏**:先给最小判断题,如"现在能不能正式吊?",学生先点一个立场。
- **反馈**:立刻说明错在对象/时点/阈值/要件/边界哪一道门,再进入动画白板纠错。
- **舞台**:竖屏上半屏是可操作图/判断树,下半屏是选项和反馈;横屏左侧大图,右侧教练反馈和采分原子。
- **视频角色**:动画/音频只是教练解释和复看材料,不是主路径本身。学生不用全屏也应能完成核心判断。

`video-first` 适合计算推演、构造演示、流程揭示;`decision-first` 适合判断题。不要因为 N01 样板成功,把所有考点都包装成视频播放器。

## 2. 6+1 表现原型:按认知结构选,不按章节选

选择原型的标准是"学生卡在哪一步",不是它属于哪一章。

| 原型 | 代表考点 | 动画表现 | 语义用色 | 互动/练习 | 何时不要动画化 |
|---|---|---|---|---|---|
| 1 时序/工序 | 施工流程、工序、验收流程 | step reveal,工序路径,进度条,错步回退 | 蓝到绿=进度完成 | 下一步/拖顺序/找漏步 | 只有背口诀、无顺序因果 |
| 2 构造/空间 | 防水节点、钢筋锚固、剖面、后浇带 | 剖面分层、爆炸图、局部放大、层点击 | 层色编码:基层/防水层/保护层稳定 | 点层解释/找错误层/对照正确做法 | 缺可靠构造依据或图元 |
| 3 计算/图结构 | 网络计划、关键线路、时差、流水 | 图节点高亮、逐步推演、路径重算、变量变化 | 关键线红/当前算点蓝/余量琥珀 | 拖节点/试算/改数值重算 | 只问定义,没有可推演结构 |
| 4 判断/分支 | 危大论证、合同变更、事故等级 | 判断树、条件卡、分支灰/绿/暗、边界档 | 分支灰、命中绿、淘汰暗 | 选分支/边界判断/换工程迁移 | 判据链缺证据或阈值未核 |
| 5 对比/正误 | 规范 vs 非规范、质量通病、错做法 | 左右对照、错因标注、局部扣分点 | 绿=对、红=错、琥珀=风险 | 点查扣分原因/修错 | 两边差异不能视觉化 |
| 6 采分点/诊断 | 题干→采分点命中、答案对照、错因 | 答案逐句扫光、hit/partial/miss 标注 | hit绿/partial琥珀/miss红 | drill-down 为何没分/补一句 | 没有评分粒度数据 |
| 7 数值/记忆 | 定义、规范数值、参数辨析 | 静态卡、表格、记忆钩子、间隔复习 | 中性,少动效 | 间隔复习/快问快答 | 数字本身不能靠动画解决 |

混合考点先定主原型:如果核心难点是判断,构造图只当辅助;如果核心难点是空间,判断句只当说明。不要一张卡塞两套主 body;真跨两类就拆成卡组。

## 3. 母题数据到动画资产的映射

### 3.1 数据读取顺序

1. `master`:读不变量、变量规则、变题、掌握鉴别、warm_feedback。
2. `teaching_card_ref`:读 wrong_idea、visual_correction、exam_phrase、memory_hook、authority boundary。
3. `source_refs`:核教材/规范/讲义 chunk/真题锚,确认候选或签发状态。
4. `variants` / `quiz`:读题目梯度和 basis_ref。
5. `misconception` / common_errors:抽学生语言,做错法和干扰项。

### 3.2 输出资产必须保留的 lineage

每个动画项目至少生成或维护:

- `*.lesson.json`:讲解 beat,每段 claim 有 anchor。
- `*.lesson.timing.json`:TTS timing,每段对应 stage/keycard/speaker。
- Remotion/HTML 渲染源:只读 lesson/master/card 数据。
- `*.practice.html` 或 journey 练习幕:题目来自 variants/quiz。
- 截图/验收记录:首屏、关键运镜、练习、结果页。
- `validate_video_first_preview.mjs` 输出:证明普通态 responsive learning stage、横屏/宽屏适配、全屏/theater、章节、拖动进度、独立练习、student-safe 和练习闭环没有明显破约。
- `validate_learning_stage_runtime.mjs` 输出:用真实浏览器视口证明竖屏首屏、竖屏播放、横屏播放、桌面宽屏和 theater 控制层没有塌陷、遮挡、窄竖条或横向溢出。

### 3.3 禁止的漂移

- 旁白说了卡里没有的事实。
- 动画里出现新阈值、新路径、新采分点,但 master/card 没有。
- 练习题比 variants 多出新判据,却没有 basis_ref。
- 看穿结论由前端临时规则判断,不是读 `mastery_discrimination`。

## 4. 旁白设计:先抓人,再讲内容

### 4.1 标准段落

旁白不要一上来讲知识点。按下面顺序设计:

1. **为何要学**:考试场景、近年频率、常和哪些题型连在一起、能拿哪些分。来自 master/source/exam matrix;没有频率证据就说"常见训练场景",不要编年份。
2. **错觉/痛点**:学生最容易怎么想,这种想法为什么丢分。来自 `wrong_idea` / misconception。
3. **视觉事实**:用一个画面把错觉打掉。比如"关键线路不是一个工作,是一条从开始到结束的 0 总时差连续链"。
4. **推演过程**:一步步算、判、拆、对照,每步只讲一个动作。
5. **采分表达**:把图、判据、工序落成能写到答题纸上的一句话。
6. **答疑/迁移铺垫**:模拟学生问真正会卡住的问题;老师补齐边界和迁移条件。
7. **闯关桥接**:明确告诉学生"现在换个数/换个工程/换个表达,看你是不是真会"。
8. **收尾回扣**:最后用 8-15 秒把本卡的考试动作再说一遍,并自然把主行动交给闯关。

### 4.1.1 叙事骨架:一条线从头贯到尾

不要把开场、主讲、答疑、收尾写成四段互不相干的文案。每张动画先定义一个**考试动作主线**,所有段落都服务它:

| 段落 | 任务 | N01 样板做法 | 通用写法 |
|---|---|---|---|
| hook | 告诉学生为什么值得学 | 考场要交"路径、总工期、判断依据"三件套 | "这类题不是考定义,是要你交出 X、Y、Z" |
| trap | 抓最常见错觉 | "C 最长,所以关键线路是 C" | "很多人第一眼会把 A 当答案,但它错在对象/条件/边界" |
| model | 建正确判断动作 | 关键线路是一条 0 总时差连续链 | "正确做法不是背词,而是先找 A,再看 B,最后写 C" |
| worked | 现场推一遍 | 顺推、逆推、看总时差 | "我们只练一个动作:把图/条件/做法翻译成采分句" |
| score | 落答题纸 | 路径 + 总工期 + 判断依据 | "考试不要只写结论,要把依据一并写出来" |
| qa | 处理真困惑 | 最长工作、路径相加、总/自由时差 | "学生会卡的边界,放到主讲后集中答" |
| closing | 回扣并切闯关 | 别背关键线路,把图翻译成三件套 | "收个尾:下次遇到这类题,只做这 N 步;现在闯关验证" |

**技巧**:

- 开场提出的词,结尾必须再出现一次,形成闭环。
- 旁白里的关键词要可视化:如果画面里没有"路径/工期/依据",旁白就不要把它当主线。
- 每一段只推进一个判断动作。N01 里"读箭线""顺推""逆推""看总时差""写采分句"是五个动作,不能混成一段长讲解。
- 学生声只问真会卡的问题,不负责捧哏、不重复老师结论。

### 4.2 教师与学生声音

- 老师:稳定、短句、像考前点拨,优先讲判断动作和采分句。
- 学生:只在讲完主线后出现,负责提出真实困惑,不要打断主讲。
- TTS 推荐:老师 `longanhuan_v3`;学生追问默认且优先用 `Ethan`(晨煦)。除非用户明确指定,不要混用其他学生音色。音频离线生成,运行时只播放。
- 每句旁白 8-18 秒为宜;超过 20 秒必须拆 beat。

### 4.3 旁白红线

- 不说"这个很简单"。
- 不用泛励志,只解释为什么能多拿分。
- 不把候选采分点说成官方阅卷。
- 不让画面只跟着字幕走;旁白每说一个关键动作,画面必须有对应变化。
- 不在答疑后突然结束;没有 closing 段就不算完成。
- 不让收尾变成泛鼓励;收尾必须回扣本卡的考试动作和下一步闯关。

## 5. 视觉与运镜:像老师导演注意力

### 5.1 画面结构

手机竖屏优先,首屏必须同时满足:

- 有第一帧白板/poster,不是黑帧。
- 中央播放按钮清晰。
- 完整 hook 能在 390px 宽下读完。
- 主视觉不是小图标,而是占据核心视野的板书/构造/网络/判断树。

### 5.2 运镜词汇

每个 beat 至少选一种有教学目的的镜头:

- `push-in`:讲到关键点时推近,让它成为唯一焦点。
- `spotlight`:当前节点/层/条件亮起,其他元素暗化。
- `trace`:用线条沿路径生长,表现流程或逻辑走向。
- `wipe/reveal`:答案或采分句逐格揭示,模拟老师写板书。
- `split-compare`:正误/前后变化左右对照。
- `exploded-section`:构造层分离,再合回正确结构。
- `freeze-frame`:在最易错瞬间暂停,用红叉/问号打断错觉。
- `answer-paper`:最后切到答题纸,把视觉结果转成采分句。

### 5.3 镜头节奏

- 0-12 秒:抓注意力,解释为什么学。
- 12-30 秒:暴露错觉,用视觉打掉。
- 30-75 秒:主推演,每 6-10 秒一次视觉变化。
- 75-105 秒:采分表达 + 边界/迁移。
- 105 秒后:答疑桥接和进入闯关。

不是所有视频都必须 120 秒;原则是"讲到能做题为止",不要为了完整讲义拖长。

### 5.4 顶流视觉判断

用 3 秒眼路径检查:

1. 先看到什么?必须是当前关键对象。
2. 第二眼看到什么?必须是判断依据。
3. 第三眼看到什么?必须是要写出的答案或下一步动作。

如果第一眼看到的是一堆卡片、一大片空白、过大的箭头、装饰性渐变,返工。

### 5.5 运镜方法:用镜头替学生筛注意力

N01 的关键提升不是"更花",而是镜头开始替学生判断该看哪里。后续量产按这套方法拆镜:

1. **先定焦点层级**:每一帧只允许一个第一焦点、一个第二焦点、一个背景层。第一焦点=当前判断对象;第二焦点=依据;背景层只保留上下文。
2. **先遮再亮**:重要信息出现前,先让非重点降噪或暗化。直接把全部信息摊出来,学生会自己乱找。
3. **推近不是慢慢放大**:push-in 要有明确落点和时间窗。通常 12-18 帧完成主要推近,再停住给旁白落词;不要 3 秒缓慢漂移。
4. **trace 表示逻辑,不是装饰线**:路径、流程、判断链用线条生长;线条必须沿真实依赖/空间/工序走,不能只画漂亮箭头。
5. **freeze-frame 打断错觉**:学生最容易错的瞬间暂停 0.4-0.8 秒,给红叉/问号/反证句,再进入正确模型。
6. **答题纸是最终镜头**:讲解不是以图结束,而是以"图如何写成分"结束。最后必须出现答题纸/采分格/关键词扫光。
7. **每 6-10 秒要有视觉状态变化**:不是每 6 秒换页,而是焦点、遮罩、线条、板书、场景或卡片至少有一个发生教学相关变化。

### 5.6 场景编排:多页面但不碎片化

不要把"多点页面"理解成幻灯片堆叠。场景切换要服从认知阶段:

- `hook scene`:展示考试任务和收益,少放细节。
- `trap scene`:只让错误对象变大,给学生一个"我也会这样想"的入口。
- `model scene`:建立正确结构,隐藏暂时无关的信息。
- `worked scene`:逐步推演,允许信息密度上升。
- `score scene`:把视觉结果转成答题纸。
- `qa/closing scene`:收束主线,不要再引入新的复杂图。

技巧:切场景前先问"这一屏要学生形成哪一句话?"如果没有一句话,这屏删掉。

## 6. Remotion / HTML 实现纪律

### 6.0 OpenMAIC-style IR 分工

稳定不靠锁死 AI,而靠分工:

- AI/专家组负责产结构化中间表示:每个 beat/scene 明确 `scene/focus/enter/hold/exit/layout/camera/visible_nodes/keycard/coach`。
- renderer 只做确定性渲染:纯 switch/组件映射,不让自由 HTML、CSS class 累积或上一次播放状态决定下一屏。
- 预览和正式成片共用同一份 IR:HTML renderer 用来快速评审手机交互;Remotion renderer 用来正式成片,不得另写一份 storyboard。
- gate 证明 scene 生命周期:当前屏 visible nodes 有上限、只有一个 active scene、只有一个 keycard、theater 仍有闯关入口、无 `reached-*` 累积。

F16 这类工序/构造型卡的默认拆法:

1. `hook`:先打错觉,告诉学生为什么这题不是"补一层"。
2. `disease`:剖面认病因,气/水汽顶起卷材。
3. `cut`:割开放气,打掉直接加铺错觉。
4. `dry`:排气干燥、清基层/旧胶。
5. `add/seal`:附加层盖过边缘、新卷材搭接封严。
6. `test`:蓄水/淋水检验。
7. `score`:答题纸采分句。
8. `closing`:收束主线并切闯关。

每一屏都要回答一句话:"这一屏结束时,学生应该形成哪一句可写进答题纸/判断题的表达?"答不上来就删屏或合并屏。

### 6.1 Remotion

- 所有动画由 `useCurrentFrame()` 驱动;用秒写 timing,乘 `fps`。
- 用 `interpolate(..., {extrapolateLeft:"clamp", extrapolateRight:"clamp"})`。
- 进入动效优先 `Easing.bezier(0.16,1,0.3,1)`,退出用 `Easing.in(Easing.cubic)`。
- 不用 CSS animation / transition 做 Remotion 内动画。
- 关键帧必须可 still render:hook、误区、主推演、采分句、答疑/收尾。

### 6.2 HTML 交互壳

- 讲解页和练习页分开;讲解视频结束后主行动切到"开始闯关"。
- 视频首屏用 poster;中心播放按钮;`playsinline`。
- 练习页手机优先,底部固定上一题/下一题,未答不能跳。
- 题目图用 deterministic SVG,不是截图糊上去。

### 6.2.1 手机全屏播放器 UX

手机端不要把网页整体放大成"全屏"。全屏模式只服务视频学习:

- 全屏默认只显示视频内容,隐藏页面标题、卡片、普通按钮。
- 普通窗口里的学习舞台必须是 `orientation-adaptive` 响应式容器,不是固定 9:16 竖屏容器。竖屏手机可用接近 9:16/4:5 的主舞台;横屏、桌面、宽容器必须改成两栏/侧栏/overlay/bottom sheet,扩大有效教学画面,避免外层大框套小竖片。全屏/theater 再覆盖为 `width:100%; height:100%; aspect-ratio:auto`。
- 全屏必须同时有 CSS theater fallback 和浏览器 Fullscreen API 尝试;Safari/web-view 不支持时,至少保证页面内 theater 形态像播放器,不是滚动网页。
- 点击屏幕才浮出控制层;控制层包括播放/暂停、静音、退出、可拖动进度条和章节跳转。
- 控制层出现时,必须给视频内容预留底部空间,不能遮住字幕、讲解卡、收尾卡或采分句。
- 进度条必须能拖动;拖动时画面和字幕同步跳到对应时间。
- 章节节点不要只写 `1/2/3`。用学习阶段短标签,如"先学/错觉/读图/顺推/逆推/时差/线路/采分"。
- 如果按钮很多,优先保留播放器基本动作;视觉说明文字放进 tooltip/aria,不要塞满屏幕。
- 重新生成 mp4/poster/mp3 后,HTML 资源引用带 mtime/hash 版本参数,避免 Safari/web-view 播旧缓存。

### 6.2.2 播放结束状态

- 视频 `ended` 后主按钮变成"开始闯关"。
- 播放按钮仍可回看,但不能比闯关更强。
- closing 旁白结束和 CTA 切换要自然衔接;不要靠突然跳页制造完成感。

### 6.3 文件命名

- `<topic>.lesson.json`:动画脚本。
- `<topic>.lesson.timing.json`:音频 timing。
- `<topic>.remotion.mp4`:Remotion 成片。
- `<topic>.poster.png`:首屏 poster。
- `<topic>.rendered.html`:讲解页。
- `<topic>.practice.html`:独立练习页。

### 6.4 音画同步制作法

音画同步不是最后微调,而是从 lesson/timing 设计开始就要做:

1. **先列关键词时间点**:从旁白中抽出必须对齐的词,如"关键线路/总工期/总时差/采分句/阈值/错误做法"。
2. **关键视觉略早出现**:视觉通常比关键词早 0.1-0.3 秒出现,让学生听到词时已经看见对象;不要晚于旁白 0.5 秒以上。
3. **每个 segment 有 visual state**:`state` 不只是字幕分类,要能驱动 Remotion 的页面、焦点、遮罩和字幕。
4. **用 still 检查关键帧**:hook、trap、model、worked、score、qa、closing 都要能单帧看懂。
5. **长句拆段**:一句旁白里如果有两个视觉动作,拆成两个 segment 或两个内部 cue。
6. **字幕卡跟随语义,不是逐字稿**:字幕卡写当前结论或白板讲解,不必塞满全部旁白。
7. **ffprobe 对齐总时长**:mp3、mp4、timing.json 三者时长不能明显漂移。Remotion duration 要按 timing totalSec 重新计算。

N01 最终 timing 结构可作为参考:主讲约 0-100s,三组学生答疑约 101-148s,closing 约 148-161s。这个比例不是固定模板,但说明"主讲、答疑、收尾"要各有明确时间段。

### 6.5 预览与成片渲染分层

不要把"给用户看一版学习卡"默认等同于"重新导出 MP4"。量产时分两档:

1. **预览评审档**:用于看排版、文案、UI/UX、交互、章节标签、练习闭环。优先复用已有 mp4/poster/mp3;只改 HTML/CSS/JSON 时,用 Remotion still 和 CDP/Playwright 390px 普通页 + theater 截图验收,不跑 full render。
2. **成片验收档**:用于验证真实音画同步、媒体内容变化、正式候选、发布前缓存和 CDN 链路,或用户明确要求视频文件。这时才执行 full `remotion render`、`ffprobe`、关键时间点截图和版本参数检查。

判断标准:如果本次改动没有改变 Remotion 帧内容、音频、timing 或媒体文件,就不要生成新 MP4。HTML 播放器壳、比例、按钮、练习页、章节文案的修改,默认属于预览评审档。

预览评审档也必须 fail-closed 跑静态合同门:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_video_first_preview.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/<topic>.rendered.html \
  artifacts/luban_case_family_assets/diagram_microlesson/<topic>.practice.html
```

这条命令只检查表现合同,不重算题目、不判断采分句真伪、不替代 `validate_schema_drafts.py`。

随后必须跑真实视口运行时门:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs \
  artifacts/luban_case_family_assets/diagram_microlesson/<topic>.rendered.html
```

它不是截图替代品,而是防止模板回归:390 竖屏首屏、390 播放态、844x390 横屏、1024x720 宽屏、390 theater 控制层都要通过几何断言。过不了先修 Learning Stage Shell,不要继续调文案或装饰。

## 7. 练习设计:从会看懂到会迁移

每个动画后面至少 4-6 道题,按难度上升:

1. **原图识别**:能否找出刚讲的关键对象。
2. **错觉鉴别**:能否识别最常见错误说法。
3. **同结构换数/换条件**:是否会重走算法或判据链。
4. **边界档/反例**:最容易混的中间状态。
5. **迁移题**:换工程、换图、换表达,考不变量。
6. **采分句输出题**:让学生写路径/工期/理由,或写工序/错法/正确做法/采分关键词。

题目形式要丰富,但标准统一:

- 选择题选项写成"对象/路径 + 工期/档位/结果 + 判断依据"。
- 变化题必须配变化图。
- 诊断题必须给学生答案片段,让他找 hit/partial/miss。
- 输出题要按采分原子拆输入格,不能只让学生自由写一大段。
- 每题反馈都要解释依据,不是只说对错。
- 关键鉴别题写入 `mastery_discrimination.key_discriminator_ids`。

### 7.1 题目丰富度技巧

题目丰富不是换几个选项,而是换学生要执行的认知动作:

- `看见对象`:让学生点/选当前考点对象,验证他没看错题眼。
- `识别错觉`:给常见错误表达,问为什么错。
- `复走过程`:换数字/条件,让学生重走同一算法或判据链。
- `卡边界`:选接近阈值、相邻工序、部分命中答案,防止过度概括。
- `换外壳`:换工程、换图、换描述,考不变量是否迁移。
- `写采分句`:把最终答案拆成 2-4 个采分原子输入,训练输出,不是只训练选择。

干扰项写法:

- 错项最好对应真实 misconception,不要随便编离谱选项。
- 每个错项都要有"为什么会有人选它"的心理理由。
- 反馈先指出错在对象/顺序/条件/边界/表达哪一类,再给正确判断依据。
- 选择题只是过渡,最终要有输出题;考试拿分靠写出来。

## 8. 专家组分工

量产前至少做 5 个角色的自审,可由同一个 agent 分角色完成:

1. **母题引擎审稿人**:查动画事实是否都来自 master/card/variants/source。
2. **考试采分审稿人**:查采分句、干扰项、反馈是否能服务拿分。
3. **学习科学导演**:查是否先抓注意力,是否一屏一判断点,是否每条动效接练习。
4. **视觉/运镜导演**:查焦点、暗化、推近、切页、视觉记忆钩子。
5. **移动端 QA**:390px 视口无横滚,按钮不遮挡,文字不溢出,练习闭环可走完。
6. **红队**:主动找漂移、source 泄漏、候选冒充、过度动画、无效题。

被质疑时先回依据验证。依据站得住就解释并优化表达;依据站不住才改内容。

## 9. 验收清单

### 数据与权威

- [ ] 已读取 master/card/variants/scoring/misconception/source。
- [ ] 所有 `claim:true` 旁白有 anchor。
- [ ] 每道练习有 basis 或 basis_ref。
- [ ] 看穿结论读 `mastery_discrimination`,不是前端新造。
- [ ] student 端不露 internal id/source_ref/schema/candidate。

### 教学体验

- [ ] 首屏有完整 hook,不是直接讲内容。
- [ ] 每个 beat 一个视觉动作 + 一句旁白。
- [ ] 主画面有运镜:推近、暗化、揭示、对照或局部放大。
- [ ] 最后有答题纸/采分句转化。
- [ ] 最后有 closing 旁白,回扣主线并桥接闯关。
- [ ] 关键术语出现时,画面同步或略早给出对应视觉。
- [ ] 播放结束后进入闯关的主行动明确。

### 练习闭环

- [ ] 每题有图或变化图。
- [ ] 题目难度递进。
- [ ] 至少一道迁移题或边界鉴别题。
- [ ] 至少一道采分句/答案输出题。
- [ ] 未答不能下一题,答后即时反馈。
- [ ] 结果页有暖反馈和回看入口。

### 技术验证

- [ ] `npx remotion compositions` 通过。
- [ ] `node artifacts/luban_case_family_assets/diagram_microlesson/validate_video_first_preview.mjs <topic>.rendered.html <topic>.practice.html` 通过。
- [ ] `node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs <topic>.rendered.html` 通过。
- [ ] 预览评审档:至少检查 hook/误区/主推演/采分句 still 或已有 poster,再用 CDP/Playwright 检查 390px 竖屏普通页、横屏/宽屏普通页、theater/fullscreen、closing、练习页;不默认生成 MP4。
- [ ] 成片验收档:mp4 有 video+audio,时长合理。
- [ ] 成片验收档:timing/mp3/mp4 总时长一致,关键 segment 有对应画面状态。
- [ ] HTML 引用 poster/mp4/practice。
- [ ] HTML 对 mp4/poster/mp3 带版本参数,手机端不会播旧缓存。
- [ ] 截图里普通态学习舞台必须自适应当前方向:竖屏不小片化,横屏/宽屏不把内容锁成窄竖条;全屏/theater 只显示内容和浮动控制层。

## 10. 产出模板

### 10.1 Storyboard 表

| beat | prototype | main_exam_action | opening_hook / closing_echo | 来源字段 / anchor | sync_keyword | visual_state | camera_verb | practice_id | acceptance_still |
|---|---|---|---|---|---|---|---|---|---|
| hook | ③ | 把图写成采分句 | 为什么值得学 | master/source | 路径/工期/依据 | 考试任务卡 | slow-in/layer | path | hook-frame |
| trap | ③ | 防对象错判 | 错觉 | card.wrong_idea | 最长工作 | 错误对象红叉 | push-in/freeze | concept_trap | trap-frame |
| model | ③ | 建判断动作 | 连续链 | card.visual_correction | 连续/0时差 | 关键结构 reveal | trace/spotlight | path | model-frame |
| worked | ③ | 重走过程 | 推演 | question_data/variant | 顺推/逆推 | 算法逐步走 | pan/push | transfer_recompute | worked-frame |
| score | ③ | 落采分 | 采分句 | scoring/exam_phrase | 采分句 | 答题纸三格 | reveal | score_sentence | score-frame |
| qa/closing | ③ | 补边界并切闯关 | closing_echo | misconception/master | 边界/闯关 | 双人答疑 + 收尾卡 | focus shift | float_compare | closing-frame |

### 10.2 Quiz 梯度表

| level | cognitive_action | 题型 | 数据来源 | visual_asset_required | 正确答案结构 |
|---|---|---|---|---|---|
| 1 | 看见对象 | 原图识别 | card/question_data | 原图高亮 | 对象 + 结果 + 依据 |
| 2 | 识别错觉 | 错觉鉴别 | misconception | 错点局部放大 | 错因 + 正解 |
| 3 | 复走过程 | 同结构变化 | variants | 变化图 | 变化后结果 + 重算依据 |
| 4 | 卡边界 | 边界/反例 | variants/key_discriminator | 边界图 | 档位/路径 + 为什么 |
| 5 | 换外壳 | 迁移 | variable_rules | 新工程/新图 | 不变量 + 新条件 |
| 6 | 写采分句 | 输出题 | scoring_points | 答题纸/采分格 | 采分原子完整 |

## 11. N01 video-first 样板复盘

`N01_network_video_first.rendered.html` 是当前 video-first 样板,但后续不能被它的具体画面锁死。要继承的是产线原则,不是照搬 N01 的网络图布局。

### 11.1 第一版踩过的坑

- 只有页面切换,没有 Remotion 级别的真实动画和运镜。
- 没有声音、没有旁白,学生不知道什么时候该看哪里。
- 题目混在讲解页里,看懂和练会两个目标互相干扰。
- 一上来直接讲内容,没有先解释为什么要学、考试怎么用、为什么容易丢分。
- 箭头过大,视觉焦点不自然,抢了节点和判断依据的注意力。
- 画面长期锁在一张白板上,缺少多场景切换、推近、暗化、答题纸转化。
- 音画节奏一度脱节;旁白讲到关键点时,画面没有同步强调。
- 练习题缺少每题图/变化图,选项也没有训练"路径 + 工期 + 判断依据"的考试表达。

### 11.2 最终沉淀的默认形态

1. **首屏**:白板 poster + 中央播放按钮 + 完整 hook。学生点播放前就知道"为什么学这个能多拿分"。
2. **讲解视频**:Remotion 负责动画主体;每个 beat 有一个视觉动作,如 push-in、spotlight、trace、dim、scene change、answer-paper reveal。
3. **旁白音色**:老师主讲用 `longanhuan_v3`,学生答疑默认用 `Ethan`(晨煦);音频离线生成,运行时只播放。
4. **音画同步**:关键视觉可以略早于旁白关键词出现,但不能晚到让学生听完才看到;同步问题优先调画面 timing,不是拉长空白。
5. **场景丰富度**:不要整段锁在同一白板。至少包含 hook 场景、错觉场景、主推演场景、采分句/答题纸场景、答疑/闯关桥接场景。
6. **独立闯关页**:练习从讲解页分离;播放结束后主 CTA 自动切到"开始闯关"。
7. **每题有图**:原图识别有原图高亮,变化题有变化图,诊断题有答题纸或答案片段,迁移题有新图。
8. **选项像答案**:选择项写成"对象/路径 + 结果 + 判断依据",不是短标签。
9. **递进挑战**:原图识别 → 错觉鉴别 → 换数/换条件 → 边界/反例 → 迁移 → 采分句输出。
10. **自然收尾**:答疑后要有 closing,回扣主线并把行动交给闯关。
11. **播放器交互**:手机全屏只显示内容,点击浮出控制层;进度可拖动,章节有语义标签,控制层不遮挡正文。
12. **手机先验收,再补横屏/宽屏**:390px 竖屏检查首屏、播放、普通学习舞台、全屏控制层、closing、ended CTA、练习作答、反馈和结果页;同时补一张横屏/宽屏截图,证明布局没有被固定竖屏比例拖坏。
13. **预览不出片**:仅评审学习卡效果时不重新生成 MP4;只有正式音画同步/发布候选才 full render。

### 11.3 以后复制什么,不复制什么

**复制**:

- 母题引擎数据先行:master/card/variants/scoring/misconception/source 先读完再做 storyboard。
- video-first 信息架构:讲解页看懂,练习页闯关。
- 先 hook 再讲内容:先抓注意力和考试收益,再进入知识点。
- Remotion frame-driven 动画:镜头、强调、暗化、trace、reveal 都由帧驱动。
- 练习闭环:每题配图、递进挑战、采分句输出、即时反馈。
- 播放器闭环:poster 首帧、中心播放、全屏内容、点击浮控、可拖进度、语义章节、自然收尾。

**不要复制**:

- 不要把所有考点都做成网络图白板。
- 不要把 N01 的具体排版当成固定模板;构造/空间要用剖面和爆炸,判断/分支要用判断树,对比/正误要用左右对照,诊断/采分要用答案扫描。
- 不要为了"更像 N01"削弱本考点自己的错觉、构造、判据或采分句。
- 不要让视觉设计先于数据权威;N01 的好处是把 ③计算/图结构讲清楚,不是一套万能皮肤。

### 11.4 最小验证命令

每个 video-first 样板按验收档位留证据。预览评审档只需确认静帧和手机壳:

```bash
npx remotion compositions
npx remotion still <composition-id> <poster.png> --frame=<hook-frame>
node artifacts/luban_case_family_assets/diagram_microlesson/validate_video_first_preview.mjs <topic>.rendered.html <topic>.practice.html
node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs <topic>.rendered.html
node artifacts/luban_case_family_assets/diagram_microlesson/cdp_shot.mjs <topic>.rendered.html --width=390
node artifacts/luban_case_family_assets/diagram_microlesson/cdp_shot.mjs <topic>.practice.html --width=390
```

只有成片验收档才生成 MP4:

```bash
npx remotion render <composition-id> <topic>.remotion.mp4
ffprobe -hide_banner <topic>.remotion.mp4
```

如果是纯 HTML 静态小样,也必须说明"未进入 Remotion 成片验收",不能标成 video-first 动画学习卡完成。

## 12. 一句话标准

一张鲁班深母题动画学习卡,不是"把知识点做成视频",而是:

**用母题引擎的数据权威,先抓住学生为什么要学,再用可视化运镜纠正一个核心错觉,最后用递进题和采分句输出证明他能多拿分。**
