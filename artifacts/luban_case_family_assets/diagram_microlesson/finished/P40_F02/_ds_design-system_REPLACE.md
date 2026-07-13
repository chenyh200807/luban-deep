# 鲁班智考 · 深母题动画学习卡 — Design System

> 母版来源：`安全事故等级判定与上报_讲解.dc.html` + `安全事故等级判定与上报_练习.dc.html`（S07）。
> 用途：在 Claude Design 里复用这套视觉 + 动画 + 生产规范，做任意考点的「动画学习卡 + 随堂练」。
> 一句话定位：**用动画讲知识，不用文字讲知识。** 每个考点先判 6+1 认知结构，再画领域对象，禁止纯文字卡 / 流程框 / 判断框。

---

## 0. 技术骨架（必须遵守）

- **每个产物 = 一个 Design Component（`*.dc.html`）**，浏览器直接打开、可被 `<dc-import>`。
- **仅用内联样式**：禁止 class 样式表、CSS 变量、设计 token 文件。`<helmet>` 里只放 `@font-face / @keyframes / body reset / 字体 <link>`。
- **emoji / 表情符号一律禁用**：所有图标用 CSS 图形或文字符号（✕ ● ✓ ⛶ 这类几何符号可作 UI 图标）。领域对象（信封/公文/笔/安全帽等）一律用 CSS 形状画，不用 🤖📝📎✉️📄🖊️ 这类 emoji。
- **动画**：`requestAnimationFrame` 驱动一个 `t`（秒）状态 → `renderVals()` 按 `t` 算出每个对象的 opacity / transform 标量 → 模板里用 `{{ }}` 标量插值。**绝不**用模板 `animation:` + `@keyframes` 驱动主时间轴。
- **运行时注入两段 JS（放 `componentDidMount`，因为 helmet 在打包后偶发不生效）**：
  ```js
  // 1) 移动视口（手机不缩小成桌面宽度）
  var vp=document.querySelector('meta[name=viewport]');
  if(!vp){vp=document.createElement('meta');vp.name='viewport';document.head.appendChild(vp);}
  vp.setAttribute('content','width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover');
  // 2) 模拟全屏样式（真全屏 API 在 iframe 被禁时兜底）
  if(!document.getElementById('lz-fs-style')){var s=document.createElement('style');s.id='lz-fs-style';
    s.textContent='body.luban-fs .lz-card{position:fixed!important;inset:0!important;width:100%!important;max-width:100%!important;height:100vh!important;overflow-y:auto!important;z-index:9999!important}body.luban-fs{overflow:hidden}';
    document.head.appendChild(s);}
  ```
- **画布尺寸**：竖屏手机卡 `width:100%;max-width:390px;min-height:100vh`；动画舞台 `width:100%;height:462px;overflow:hidden`。截图基准 **390px**。

---

## 1. 色彩

| 角色 | 色值 | 用途 |
|---|---|---|
| 纸面底 | `#f4f3ec` | 动画舞台 / 练习页底；点阵 `radial-gradient(#e4e2d7 .7px,transparent .7px) 18px` |
| App 暗底 | `#181b1e` | 头部、控制区、问答弹层；更深 `#15181b` / `#101315` |
| 墨色 | `#23282b` | 主文字、深色卡片、印章描边 |
| **品牌红** | `#cf4436` | 鲁班标识 / 老师 / 陷阱 / 强调 / 主按钮 |
| 暖橙（副） | `#cf8a44` / `#c9683e` | 学生标签、QA 高亮、渐变按钮右端 |
| 蓝（对象/主体） | `#2f6db0` | 分类芯片、上报主体、图示对象 |
| 绿（命中/正确） | `#2c8a5b` | 判定正确、命中档、"做练习"按钮 |
| 高亮笔 | `#ffd24a` | 关键词扫描、命中脉冲、探针 |
| 钢灰 | `#8a9296` / `#9aa0a3` / `#a7adb0` | 现场剪影、次要文字、轨道底 |
| 安全帽黄 | `#eebd3c` / `#d9a521` | 工地要素 |
| 卷材深 | `#3a5168` / `#46627e` | 屋面/地下防水卷材对象 |
| 基层暖灰 | `#b9a88a` | 钢筋混凝土基层、地面线 |
| 分级带 4 档 | 一般 `#dff0e6` · 较大 `#fdeed1` · 重大 `#fadcd6` · 特别重大 `#f1c9c1`（暗版 `#2c8a5b/#7a5a2a/#7a3a30/#5e2a22`） | |

**规则**：一卡只用 1（红）主 + 1（橙）副强调色，其余为对象语义色（蓝=主体、绿=正确、黄=高亮）。不另造新色。

---

## 2. 字体

- 正文 / UI：**Noto Sans SC**（400/500/700/900）。
- 手写印章点缀：**Long Cang**（仅用于「鲁/师/生」头像、海报大标题，**不用于正文**）。
- 字号下限：移动正文 ≥ 11px；点击目标 ≥ 44px；舞台标题 12–17px；钥匙卡 11px；旁白 12.5px。
- 海报大标题用 Long Cang 46px 红色；副标 17px 900 墨色。

```html
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&family=Long+Cang&display=swap" rel="stylesheet"/>
```

---

## 3. 间距 / 圆角 / 阴影

- 圆角：卡片 8–16px；胶囊/标签 7–14px 或全圆；按钮 11–13px；舞台对象块 5–9px。
- 手绘块阴影：`2px 2px 0 <同色或墨色>`（offset 实心，无模糊），强调用 `3px 3px 0`、`4px 4px 0`。
- 浮起阴影（按钮/弹层）：`0 3px 12px rgba(207,68,54,.28)`、弹层 `0 -8px 30px rgba(0,0,0,.5)`。
- 内边距：卡片 11–16px；头部 13–14px；控制区 12–18px。
- 元素成组一律 `display:flex; gap:` —— 不用裸 inline + margin。

---

## 4. 组件清单（母版里已成形，可直接复用）

### 4.1 头部 Header
红色 Long Cang「鲁」圆角章内嵌 `assets/mark-white.png` + 标题两行（小标签 9px 字距 2px + 主标题 15px 900）+ 右上角考点编号/分类。练习页右上角放「看讲解 →」回链。

### 4.2 海报 Poster（讲解页首帧）
点击播放前盖在舞台上：Long Cang 大标题 + 副标 + 红色圆形 ▶ 播放钮 + "点击播放 · N 幕精讲 + M 追问 · 约 X 分 Y 秒"。`opacity` 由 `t<0.05 && !playing` 控制。

### 4.3 时间轴控制区
红色圆形播放/暂停钮 + `range` 进度条（`accent-color:#cf4436`）+ 当前/总时长 + 全屏钮 ⛶。下面一排 beat 芯片（当前红底白字，其余 `#23282b`），末位「问答 Q&A」橙底。再下面一排功能按钮：「问追AI」红渐变 + 「做练习 →」绿。

### 4.4 钥匙卡 Keycard（舞台顶部胶囊）
`rgba(35,40,43,.92)` 暗胶囊 + 黄点 + 当前 beat 的一句记忆点。

### 4.5 旁白条 Caption（舞台底部）
渐变遮罩 + 暗卡 + 红色 Long Cang「师」头像 + "老师旁白 · longanhuan_v3" 标签 + 当前 beat 旁白（当前页/总页数）。QA 场景时 `opacity:0` 隐藏。

### 4.6 师生对白气泡（QA 场景，在舞台内播放）
- 学生：蓝色 Long Cang「生」头像 + 白底带边气泡（圆角 `13px 13px 13px 4px`），左侧滑入。
- 老师：红色「师」头像 + 深棕气泡 `#2b2620`（圆角 `13px 13px 4px 13px`）+ 内嵌**迷你领域图**，下方滑入。
- 底部导航圆点（当前红、拉长 18px）+「接着问」按钮。

### 4.7 问追AI 弹层（大窗 · 两页一致）
- `position:fixed/absolute; inset:0` 暗遮罩 → 底部大窗 `height:88vh; display:flex;flex-direction:column`。
- 结构：顶部抓手条（下拉关闭，下滑 >70px 关）→ 标题+✕ → 「已附带上下文」灰卡（练习页自动注入题干+作答+是否已对答案）→ 快捷追问 chips → textarea → `flex:1` 可滚动回答区（空闲引导 / 加载转圈 / 老师气泡回答）→ 底部钉住的提交钮。
- 接口：`window.claude.complete(prompt)`，`try/catch` + `.catch()`；无接口时走兜底文案。Prompt 必带本考点知识口径 + 老师人设（龙安欢/东北口语/按采分点）。

### 4.8 练习题卡（练习页）
进度条 + 题号/维度标签 → 题干 → **图示区**（每题必有：标尺/变化图/管道图/诊断图/答题纸）→ 选项（完整采分句，非关键词）→ 提交后每项展开解析 → 「抄进答题纸的采分句」暗卡 → 行动钮 + 「这道题没搞懂？问追AI（已带题目）」。

### 4.9 结果页（练习页）
Long Cang 评语 + 大比分 → 逐题表现 → 薄弱点（按 error_code）→ 继续补练两道 → 红色「问鲁班」入口 → 重做。

---

## 5. 动画原则（红线）

1. **先判 6+1 认知结构**，冻结 `visual_archetype_decision` + `domain_visual_plan`，再动手。
2. **必须画领域对象**：工程/现场/资金/图结构对象要真的进入、移动、分层、命中、淘汰、trace、扫描、退出。6+1 原型是结构不是标签。
3. **对象级动作**，不是整页淡入淡出。每个对象按 `t` 算 opacity/transform。
4. **不累积画面**：每 beat 用 `lo{i}`(opacity) + `lpe{i}`(pointer-events) 切层，离场对象明确退出，只留必要锚点。
5. **安全/合同/管理类也不准退回纯文字**：用标尺命中、管道流转、人头围合、印章淘汰等表达。
6. 缓动 `eo(p)=1-(1-p)^3`；窗口函数 `W(a,b)` 把 beat 内进度切成分段动作；`lp(a,b,p)` 线性插值。

### 领域可视化母题库（visual_library，可跨考点复用）

- **标尺命中** `threshold_ruler`：多档分级带 + 数值探针滑动 + 命中高亮 + 取最高（计算判定链类）。
- **阈值触发** `threshold_trigger`：阈值尺（0—临界—上限）+ 指针滑过临界刻度 → 临界区高亮 → 触发后续做法对象出现（**因果**，非并列分类）。专治**条件维**（满粘/坡度阈值/热熔温度等）：禁用「几个并列 token 卡」图，改用「指针滑过即触发」的动作；练习页静态版也画成「指针停在 X、落入临界区 → 结果」的因果图。例：坡度尺指针滑到 28% 越过 25% → 绿区亮 →「满粘 + 钉压」面板 + 钉头出现。
- **流程管道** `report_pipeline`：有向节点 + 载体（信封/公文）流转 + 错误支路红✗淘汰 + 时钟（程序/时限类）。
- **成员围合** `investigation_group`：人头芯片 staggered 飞入围成组（主体/清单类）。
- **处理链** `handling_chain`：建议→批复→执行 + 双追责印章 + 自裁红✗（因果/责任类）。
- **现场剪影** `site_scene`：脚手架+斜撑+坠落小人+安全帽+防护栏+地面线+伤亡标签（事故物理来源）。
- **答题纸扫描** `answer_sheet`：采分句卡 + 高亮笔从左扫到右点亮关键词（收束）。
- **顺逆/镜像对比类**（搭接缝顺流水 vs 逆流水、上下层垂直 vs 错开等）：两侧**几何必须真不一样**，把区分二者的**唯一判别特征**画出来（如搭接台阶相对水流的朝向：顺＝台阶顺流而下水盖过；逆＝迎水唇水钻进）。**不能靠移动一个标签/箭头假装区别**——两边对象结构相同就等于没画。

### STAGE 叠压铁律（每个 beat 收尾人工过一遍，是 gate 的一部分）

舞台固定 `390×462`、全绝对定位；每个 beat 在全 opacity 时逐一核对：

1. **文字标签绝不压深色领域对象**（卷材条 `#3a5168/#46627e`、深色 band 等）。灰字 `#5c6469` / 红字 `#cf4436` 压深底＝低对比＝"被挡"。标签要么落浅底 `#f4f3ec`，要么改成对象内白字。坐标/端标（如「檐口·低 / 屋脊·高」）放在对象**两侧或上方**留白带，不与对象同高同位。
2. **同一行的左右标签统一 `top`、放在对象下方留白带**，别一个压对象一个不压。
3. **环/点状标记与对象留 ≥4px 间隙**（`ring.top + h < strip.top`），否则视觉粘连。
4. **长说明句（>16 字）起点靠左、整句落浅底**；箭头指向对象即可，句体别压对象。
5. 舞台对象一律 `top:` 定位（容器无固定高度时 `bottom:` 会被字幕挡住）；测量括号标签放线条上方加端点竖线。

### 双轴验收（gate · 验"正确且能读懂"，不验"渲染成功"）

> 根因复盘（F02）：条件维漏、beat0/beat1 压字、顺逆流水两边雷同——四次同一病根：**自查在验"渲染成功/对象出现"，没验"正确/能读懂/真能分清 A 与 B"**；且作者与裁判同一双眼、同源盲点。

1. **建每个领域对象前，先写一句验收判据**：`这个对象正确当且仅当 ___`，点名它必须画出的**判别特征**。自查只查这一句，不查"渲染了没"。
2. **对比类视觉做证伪式自查**：不问"它对吗"，问"啥都不懂的学生能不能只看图分清这俩？区分二者的唯一特征画出来了吗"——主动证明"这俩看着一样 / 这标签压在深底上"，证伪不了才算过。
3. **以陌生学生的眼睛读，且改完必重载后截那个 beat**（作者的眼会脑补屏幕上没有的意图；运行中预览改静态坐标可能不重挂载——必须 `show_html` 重载再截那个 beat，不能信第一帧）。
4. **gate 两轴都要过**：① 覆盖轴＝采分点覆盖矩阵（每条 present）；② 正确轴＝逐对象判据 + 可读性（几何/语义对不对、每个标签是否在浅底、每组对比判别特征可辨）。任一缺口不进 finished。
5. **把判据喂给独立核验**：fork 的 verifier 若只被告知"看看渲染"也只会查渲染；要把每个对象的判据列给它，才可能查到语义错（异源裁判查"意义"非"像素"）。
6. 用户每抓到一个问题，先归类"哪一类自查能拦住它"，把那一类补进本清单——而非只修当前这处。

---

## 6. 文案 / 配音

- 老师 voice **longanhuan_v3**；学生 voice **longlaotie_v3**。
- 老师：自然口语，"注意哈/记住哈"只在开头结尾少量用，面向阅卷采分点。
- 学生：东北男孩口吻，真诚不耍贫、不变段子。
- QA 放主讲之后，**至少三问三答**（母版四问四答）。主讲完整连贯，5 分钟内可长。
- **画面必须结合旁白（硬规则）**：主讲画面的**视觉相位顺序与旁白句序一致**，且**时机对齐 caption 翻页**——讲到哪句、屏上就出现那句对应的对象。用 `W(a,b)` 窗口把每个对象的 opacity/位移绑到对应 caption 页的 `lp` 区间。例：beat 讲「钉压」时才出钉头、讲「180~200℃」时温度计水银才升进高亮带。验收时**截中段帧**，确认 caption 文字与可见对象同步，不允许"旁白讲 A、画面还停在 B"。

---

## 7. 生产流程（每个新考点照走）

1. 读成品 MD → 提炼 `source_card`：main_exam_action / wrong_idea / teaching_spine / facts / common_errors / practice_blueprint。

2. **先做采分点覆盖矩阵（gate 第一轴），再写 storyboard**：
   - 把数据 §5 R5 的**每一条 point_id 逐行**填表，每条标「映射到哪个 beat / 哪个 QA」。**任何一条不允许空白**，除非数据用 Option B 显式 curate（且照抄其省略理由）。
   - **`teaching_spine`（叙事主线）≠ 采分点全集**。主线只组织顺序；数据 §0"五维/N 维"命中的每一维都得在动画里出现——标题写"四关"没关系，但条件维等采分点必须有自己的画面。
   - **beat 数按覆盖定，不按默认**：允许 5–8 主讲 beat、5 分钟内可长；先数采分点再定 beat 数，别拿"6 beat / less is more"当上限把采分点挤掉。
   - **练习覆盖 ≠ 动画覆盖**：某维进了 practice Q 不算讲解页已讲；两份产物各自过一遍矩阵。
   > 复盘（F02）：第一版漏了条件维（满粘/坡度>25%钉压/热熔阈值）、平行屋脊、檐口800满粘——根因正是把"四关链主线"当成采分点全集 + 把练习覆盖当动画覆盖。

3. 查视觉原型盘点 → 冻结 `visual_archetype_decision`（6+1 判定）+ `domain_visual_plan`（学生必须看见哪些对象、如何进/移/命中/淘汰/退出、为什么文字框不行；≥4 个主讲 scene 出现领域对象）。

4. 写 5–8 beat 白板 storyboard：每 beat 一个视觉动作 + 一句旁白 + 离场说明 + **逐对象验收判据**（`这个对象正确当且仅当 ___`）。

5. 生成 `lesson.json`（含 source_card / archetype / domain_visual_plan / storyboard / student_qa / animation_ir.v0）。

6. 生成 `animation_ir.v0`：每 scene 明确 scene/focus/enter/hold/exit/layout/camera/visible_nodes/keycard/coach/actions/visual_library。renderer 只消费 IR，HTML preview 与 Remotion 吃同一份。

7. 产出讲解页 DC + 练习页 DC（+ 本地跑 TTS/timing）。

8. practice 精品标准：每题有图、答前不泄答案、选项是完整采分动作、每错项三段解析（为什么容易选/为什么扣分/正确补哪句）、末题训练采分句输出或诊断、结果页含表现+薄弱点+继续补练+问鲁班。

9. **双轴 gate 通过后才进 `finished/<ID>/`**（见 §5 双轴验收）。

### 验证清单
源 workflow gate · `build_aliyun_lesson_narration.mjs --print` · `validate_animation_ir_contract.mjs` · `render_animation_ir_preview.py` · `validate_animation_ir_preview.mjs` · `render_animation_ir_practice.py` · 390px 截图 · practice 真实点击冒烟（选择/反馈/下一题/结果页）· finished 相对路径可访问 · 8800 本地可开。

### 红线
不做纯文字框/流程框/判断框 · 不把 6+1 当标签 · 安全合同管理类不退回文字 · 不只整页淡入淡出 · 不拿粗稿当成品 · 不用 emoji 表情符号 · 没过 gate/没截图/没冒烟不进 finished · 预览阶段不出 MP4 · **画面必须结合旁白（相位顺序+时机对齐字幕）** · **写 storyboard 前先过采分点覆盖矩阵、进 finished 前过双轴验收** · **对比类视觉两侧几何必须真不一样、画出唯一判别特征，不靠移标签假装** · **文字标签不压深色对象**。

---

## 8. 命名 / 文件

- 讲解页：`<考点名>_讲解.dc.html`；练习页：`<考点名>_练习.dc.html`；数据：`<考点名>_lesson.json`。
- 两页互链：讲解页底「做练习 →」；练习页头「看讲解 →」。
- 打包真机预览：讲解页加 `<template id="__bundler_thumbnail">`（红底+鲁字 SVG）→ `bundle_project` 出临时公网 URL（约 10 分钟失效）。
- 长期 / 小程序：H5 走 web-view（需备案域名 + 后端接 AI/TTS），或 Taro/uni-app 重写（RAF 动画改成小程序渲染驱动）。

---

## 9. v3 增量（当前基线 · 母版_讲解 / 母版_练习）

> 做新卡 = fork `母版_讲解.dc.html` + `母版_练习.dc.html`，只换【内容区】，骨架不动。相对 S07 的四项增量：

**① 品牌 logo（取代 Long Cang「鲁」占位）**
- 头部红色圆角章内嵌 `assets/mark-white.png`（白色 flow-mark，约 21–22px）。
- 讲解海报用 `assets/mark-red.png`（80px）+ Long Cang「鲁班智考」字标。
- 「师 / 生」头像仍用 Long Cang 字（是人物角色，非品牌标识）。

**⑤ 练习防套路（选项设计硬规则）**
- **正确项位置打散**：不能恒在某一位（尤其别恒 A）。源数据正确项可写 index0，但在 `componentDidMount` 用固定 per-question 置换重排 `q.opts`（评分靠 `o.ok` 标志、不靠索引）。整套分布要杂（如 C/D/B/A/C/D）。
- **选项长度拉平**：正确项常是"最全采分句"天生最长——必须把干扰项也写成等长完整句，让"选最长=正确"失效；至少一题的干扰项比正确项更长。
- 干扰项是完整采分动作、非关键词；每项三段解析（为什么容易选/为什么扣分+错因码/正确补哪句）。
- 验收：过一遍"只按位置/只按长度能否全对"，能就回炉。
> 复盘：F02 v1 每题正确项恒 A 且恒最长，"选 A/选最长"即全对——两 tell 叠加，不用理解。

**② 字幕一页 ≤ 3 行（硬规则，全局适用）**
- 旁白条空间窄：一页 ≤3 行，宁拆多页随时间翻页，不要一大块。
- 实现：`paginate(text,max)` 按标点切句、贪婪打包成 ≤~26 字/页；按 beat 内进度 `lp` 取当前页；标签右侧显示「· 2/4」页码。
- **TTS 仍读整段**，只字幕翻页。
- **QA 老师气泡空间大 → 整段显示、不分页。**

**③ QA 老师气泡内嵌「每问专属迷你领域图」**
- 由 `qaFig(idx)` 按当前 QA 返回绝对定位元素数组 `{x,top,w,h,bg,fg,fs,lab}`，渲染进气泡内的 `figLabel + 定高容器`。
- 每问一张专属图（示例：K 整除咬合 / 4工序→5队拆分 / 依次30 vs 流水18 bars / 采分四句 tags）。
- 对应母版字段：`qa[]` 每项加 `figLabel` + `fig`（类型名）。

**④ 排版纪律（踩坑修复）**
- 舞台对象一律 `top:` 定位；测量括号（K/T）标签放在线条**上方**并加端点竖线，避免压住色块。
- 舞台底部说明文字放在 bar 标签**下方**、加足对比度，别和标签重叠。
- 两页互链文件名占位：讲解→`考点名_练习.dc.html`，练习→`考点名_讲解.dc.html`，fork 后按真实考点名替换。
- **STAGE 叠压五条铁律**见 §5（文字标签不压深色对象 · 左右标签统一 top 放对象下方 · 环点留 ≥4px · 长说明句整句落浅底 · 坐标标签放两侧留白带）。

### 入库结构（放进 design system 项目根）
```
母版_讲解.dc.html        # 讲解页母版（fork 改内容）
母版_练习.dc.html        # 练习页母版（fork 改内容）
assets/mark-white.png    # 品牌 flow-mark（暗底用）
assets/mark-red.png      # 品牌 flow-mark（亮底用）
design-system.md         # 本文件
README.md / readme.md    # 给 Claude 的使用入口
```

**参考样例**（领域对象动画 + 阈值触发 + 顺逆镜像对比 · F02 卷材防水卡）：`F02_卷材防水_讲解.dc.html` / `F02_卷材防水_随堂练.dc.html`。
