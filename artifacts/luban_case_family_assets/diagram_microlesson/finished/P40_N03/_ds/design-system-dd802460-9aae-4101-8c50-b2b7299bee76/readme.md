# 鲁班智考 · 深母题动画学习卡 — Design System

> 一句话定位：**用动画讲知识，不用文字讲知识。** 每个考点先判 6+1 认知结构，再画领域对象，禁止纯文字卡 / 流程框 / 判断框。

「鲁班智考」是一套面向**一级建造师案例课**的「深母题动画学习卡」系统。每个考点产出两件可在手机上直接打开的卡片：一张**动画讲解页**（RAF 驱动的 6+ 幕领域对象动画 + 师生问答 + AI 追问），一张**随堂练**（图示题卡 + 完整采分句选项 + 三段错因解析 + 薄弱点诊断结果页）。老师人设是东北口音的龙安欢，所有讲解都面向阅卷采分点。

本设计系统不是常规的 React UI 组件库 —— 它的**交付物是 Design Component 模板（`*.dc.html`）**，消费方式是 **fork 母版、只改内容区**。

---

## 来源 / Sources

- 母版来源（S07 基线）：`安全事故等级判定与上报_讲解.dc.html` + `安全事故等级判定与上报_练习.dc.html`
- 当前 v3 基线母版（本项目 `templates/`）：`流水施工参数与工期`（N03）讲解 + 练习
- 上传材料：`uploads/母版_讲解.dc.html`、`uploads/母版_练习.dc.html`、`uploads/design-system.md`、`uploads/README.md`、`uploads/support.js`、`uploads/mark-red.png`、`uploads/mark-white.png`
- 完整规范见根目录 `design-system.md`（视觉 / 动画 / 配音 / 生产流程 + §9 v3 增量），本文件是它的设计系统化入口。

---

## 技术骨架（红线）

- **每个产物 = 一个 Design Component（`*.dc.html`）**，浏览器直接打开、可被 `<dc-import>`。
- **仅用内联样式**：交付的 `.dc.html` 模板里**禁止 class 样式表 / CSS 变量 / 设计 token 文件**。`<helmet>` 里只放 `@font-face / @keyframes / body reset / 字体 <link>`。
  - 本项目根的 `styles.css` + `tokens/*.css` 是**给 Design System 标签页和规范卡用的文档参考**，不是给模板用的。fork 模板时请抄字面 hex/px 值，不要 `var()`。
- **emoji / 表情符号一律禁用**：UI 图标用几何符号（✕ ● ✓ ⛶ ▶ ⏸），领域对象（信封/公文/安全帽等）一律 CSS 形状画。
- **动画**：`requestAnimationFrame` 驱动一个 `t`（秒）→ `renderVals()` 按 `t` 算每个对象的 opacity/transform 标量 → 模板里 `{{ }}` 标量插值。**绝不**用模板 `animation:`+`@keyframes` 驱动主时间轴。（编译器会警告模板里的 style holes，这些是合法的实时动画标量，无需修改。）
- **运行时注入两段 JS（放 `componentDidMount`）**：① 移动视口 meta；② 模拟全屏样式（`body.luban-fs .lz-card`）。两个母版里都已写好。
- **画布尺寸**：竖屏手机卡 `max-width:390px;min-height:100vh`；动画舞台 `height:462px;overflow:hidden`。截图基准 **390px**。

---

## CONTENT FUNDAMENTALS — 文案怎么写

- **语气**：第二人称、口语、面向阅卷。不端着，像老师当面带你过题。
- **老师 voice = longanhuan_v3（龙安欢）**：东北话、亲切，「注意哈 / 记住哈」只在开头结尾少量用；先给结论、再点采分依据；只答本考点范围。例：「中不了哈。K 是相邻俩队进场的间隔……所以必须是最大公约数。」
- **学生 voice = longlaotie_v3**：东北男孩口吻，真诚不耍贫、不变段子。例：「老师我寻思着，这 K 为啥非得是最大公约数啊？」
- **采分点导向**：练习选项是**完整采分句**（不是关键词）；每个错项必须给三段——「为什么容易选 / 为什么扣分（带错因码）/ 正确补这句」。结果页讲薄弱点、不只报分。
- **casing / 标点**：中文为主，全角标点；数字、公式、错因码（E02/E05/E07/E09）用半角；箭头用 `→`，乘号 `×`，约等 `≈`。
- **emoji**：不用。需要符号时用 ✕ ✓ ● ▶ ⏸ ⛶ → 这类。
- **字幕硬规则**：旁白条一页 ≤3 行，按标点切句贪婪打包 ≤~26 字/页，随 beat 进度翻页（TTS 仍读整段）；QA 老师气泡空间大，整段显示不分页。

---

## VISUAL FOUNDATIONS — 视觉基底

- **色彩**：一卡只用 **1 主（品牌红 #cf4436）+ 1 副（暖橙 #cf8a44）**强调色，其余是对象语义色——蓝 #2f6db0=主体、绿 #2c8a5b=正确/命中、黄 #ffd24a=高亮/探针。不另造新色。分级带 4 档（一般/较大/重大/特别重大）用于标尺命中。详见 Colors 规范卡。
- **底色**：暗 UI 用 `#181b1e`（更深 `#15181b`/`#101315`）；舞台/练习页用纸面底 `#f4f3ec` + 点阵 `radial-gradient(#e4e2d7 .7px) 18px`。背景是**纸面纹理 + 暗底纯色**，不用渐变大背景（仅页面 backdrop 有一处径向暗角、海报有上下浅渐变）。
- **字体**：正文/UI = **Noto Sans SC**（400/500/700/900）；手写章 = **Long Cang**，**仅**用于 鲁/师/生 头像和海报字标，绝不用于正文。移动正文 ≥11px、点击目标 ≥44px。
- **圆角**：卡片 8–16px、按钮 11–13px、胶囊全圆、舞台对象块 5–9px。
- **阴影**：两套——① **手绘实心位移**（`2/3/4px 实心、无模糊`，同色或墨色）用于舞台块/气泡/结果块；② **浮起阴影**（`0 3px 12px rgba(207,68,54,.28)` 按钮、`0 -8px 30px rgba(0,0,0,.5)` 弹层）。
- **卡片长相**：白底 + 1.5px 浅描边 `#dddacb` + 圆角 12px；强调卡可加 `border-top:5px` 语义色顶条。暗卡 `#23282b` 圆角 12px。
- **动画**：对象级动作（进入/移动/分层/命中/淘汰/trace/扫描/退出），不是整页淡入淡出；每 beat 切层 `lo{i}`/`lpe{i}`、离场对象明确退出、不累积画面。缓动 `eo(p)=1-(1-p)^3`，窗口函数 `W(a,b)` 切分段，`lp(a,b,p)` 线性插值。
- **过渡**：层切换 `transition:opacity .4s ease`；进度条/选项 `.15–.35s ease`；海报 `.35s`。
- **hover/press**：移动端为主，不依赖 hover；按钮按压态主要靠**禁用态变灰**（`#e2e0d5`/`#3a3127` 底 + 灰字）与 `cursor` 切换；选中态换边框色+浅底（`#fdf2f0` 红 / `#f0f8f3` 绿）。
- **透明/模糊**：弹层遮罩 `rgba(16,19,21,.82)`、钥匙卡胶囊 `rgba(35,40,43,.92)`；不用 backdrop-filter 模糊。
- **影像气质**：无照片，全部 CSS 形状领域对象，工地暖色（安全帽黄、墨色剪影）+ 纸面米底，整体暖、纸感、手绘。

---

## ICONOGRAPHY — 图标

- **不用 emoji、不用图标字体、不用 CDN 图标库。**
- **UI 图标 = Unicode 几何/符号字符**：播放 ▶、暂停 ⏸、全屏 ⛶、退出全屏 ⊠、关闭 ✕、对 ✓、错 ✕、要点 ●、箭头 →。
- **领域对象 = CSS 形状**（绝对定位 div + 背景/边框/渐变拼），如节拍柱、标尺分级带、横道图格、信封/公文、安全帽、印章。母版的 `qaFig()` / `figFor()` 用「绝对定位元素数组」生成迷你领域图。
- **品牌标识 = flow-mark PNG**（见 `assets/`）：`mark-white.png` 暗底（头部红章内 ~21–22px）、`mark-red.png` 亮底（海报 ~80px）。鲁/师/生是**人物角色**，仍用 Long Cang 字，不是品牌标识。

---

## 领域可视化母题库（visual_library · 可跨考点复用）

- **标尺命中** `threshold_ruler`：多档分级带 + 数值探针滑动 + 命中高亮 + 取最高（计算判定链类）。
- **流程管道** `report_pipeline`：有向节点 + 载体（信封/公文）流转 + 错误支路红✗淘汰 + 时钟（程序/时限类）。
- **成员围合** `investigation_group`：人头芯片 staggered 飞入围成组（主体/清单类）。
- **处理链** `handling_chain`：建议→批复→执行 + 双追责印章 + 自裁红✗（因果/责任类）。
- **现场剪影** `site_scene`：脚手架+斜撑+坠落小人+安全帽+防护栏+地面线+伤亡标签（事故物理来源）。
- **答题纸扫描** `answer_sheet`：采分句卡 + 高亮笔从左扫到右点亮关键词（收束）。

> 踩坑：舞台对象一律 `top:` 定位（容器无固定高度时 `bottom:` 会被字幕挡住）；测量括号标签放线条上方加端点竖线；底部说明文字放 bar 标签下方、足对比度。

---

## 做新卡的标准动作（fork 母版）

1. 读 `design-system.md`（视觉 / 动画 / 配音 / 生产规范 + §9 v3 增量）。
2. **fork 两个模板**（`templates/animated-lecture/AnimatedLecture.dc.html`、`templates/practice-quiz/PracticeQuiz.dc.html`），改名为 `<考点名>_讲解.dc.html`、`<考点名>_练习.dc.html`。
3. **只改【内容区】，骨架别动**（讲解页脚本顶部有 ═ 注释标出内容区 vs 骨架）：
   - 讲解：`examTitle/examCode/examCat/posterSub/posterMeta/KNOWLEDGE/DUR/beats[]/keycards[]/narr[]/qa[]` + `qaFig()` 四张迷你图 + 模板里 6 个 BEAT 块的领域对象。
   - 练习：`examTitle/KNOWLEDGE/moreText/Q[]/codeMap` + `figFor()` 每题图示。
4. 把 `assets/mark-white.png`、`mark-red.png` 复制进新卡所在目录的 `assets/`（头部/海报 logo 引用它们）。
5. 改两页互链文件名占位（讲解→练习、练习→讲解）。
6. 自检：主讲 **≥6 beat**、QA **≥4 问且每问带迷你领域图**、字幕一页 **≤3 行**、每题有图、选项是完整采分句、末题做诊断、结果页含薄弱点+问鲁班。

---

## 文件索引 / Manifest

**根目录**
- `readme.md` — 本文件（设计系统入口 + 内容/视觉/图标基底）
- `design-system.md` — 完整规范（视觉/动画/配音/生产流程 + §9 v3 增量）
- `SKILL.md` — Agent Skill 入口（可下载到 Claude Code 使用）
- `styles.css` — 文档用入口样式表（@import tokens；模板不引用它）
- `tokens/` — `colors.css` / `typography.css` / `spacing.css` / `fonts.css`（仅供规范卡 + 文档）
- `assets/` — `mark-red.png`（亮底）、`mark-white.png`（暗底）品牌 flow-mark

**模板 Templates（交付物，fork 用）**
- `templates/animated-lecture/AnimatedLecture.dc.html` — 动画讲解页母版
- `templates/practice-quiz/PracticeQuiz.dc.html` — 随堂练母版
- 各自 `assets/` 内含 mark PNG；`support.js` / `ds-base.js` 为运行时脚手架

**Design System 标签页（规范卡）**
- `foundations/` — Colors(5) / Type(3) / Spacing(2) / Brand(2) 规范卡
- `patterns/` — Components(6)：Header·Keycard·Caption / Timeline controls / QA bubbles / Quiz option states / Poster / 问追AI 弹层

---

## 红线汇总

不做纯文字框/流程框/判断框 · 不把 6+1 当标签 · 安全合同管理类不退回文字 · 不只整页淡入淡出 · 不用 emoji · logo 用 mark-white/mark-red.png · 配音 老师 longanhuan_v3 / 学生 longlaotie_v3 · 改进若通用就回灌母版。
