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
| 分级带 4 档 | 一般 `#dff0e6` · 较大 `#fdeed1` · 重大 `#fadcd6` · 特别重大 `#f1c9c1`（暗版 `#2c8a5b/#7a5a2a/#7a3a30/#5e2a22`） |

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
红色 Long Cang「鲁」圆角章 + 标题两行（小标签 9px 字距 2px + 主标题 15px 900）+ 右上角考点编号/分类。练习页右上角放「看讲解 →」回链。

### 4.2 海报 Poster（讲解页首帧）
点击播放前盖在舞台上：Long Cang 大标题 +副标 + 红色圆形 ▶ 播放钮 + "点击播放 · N 幕精讲 + M 追问 · 约 X 分 Y 秒"。`opacity` 由 `t<0.05 && !playing` 控制。

### 4.3 时间轴控制区
红色圆形播放/暂停钮 + `range` 进度条（`accent-color:#cf4436`）+ 当前/总时长 + 全屏钮 ⛶。下面一排 beat 芯片（当前红底白字，其余 `#23282b`），末位「问答 Q&A」橙底。再下面一排功能按钮：「🤖 问追AI」红渐变 + 「📝 做练习 →」绿。

### 4.4 钥匙卡 Keycard（舞台顶部胶囊）
`rgba(35,40,43,.92)` 暗胶囊 + 黄点 + 当前 beat 的一句记忆点（如「三指标任一达高级 → 按高级」）。

### 4.5 旁白条 Caption（舞台底部）
渐变遮罩 + 暗卡 + 红色 Long Cang「师」头像 + "老师旁白 · longanhuan_v3" 标签 + 当前 beat 旁白。QA 场景时 `opacity:0` 隐藏（对白已在舞台内）。

### 4.6 师生对白气泡（QA 场景，在舞台内播放，禁止堆在页尾）
- 学生：蓝色 Long Cang「生」头像 + 白底带边气泡（圆角 `13px 13px 13px 4px`），左侧滑入。
- 老师：红色「师」头像 + 深棕气泡 `#2b2620`（圆角 `13px 13px 4px 13px`）+ 内嵌**迷你领域图**，下方滑入。
- 底部导航圆点（当前红、拉长 18px）+「接着问」按钮。

### 4.7 问追AI 弹层（大窗 · 两页一致）
- `position:fixed/absolute; inset:0` 暗遮罩 → 底部大窗 `height:88vh; display:flex;flex-direction:column`。
- 结构：顶部抓手条（下拉关闭 `onTouchStart/Move/End`，下滑 >70px 关）→ 标题+✕ → 「已附带上下文」灰卡（练习页自动注入题干+作答+是否已对答案）→ 快捷追问 chips → textarea → **`flex:1` 可滚动回答区**（空闲引导 / 加载转圈 / 老师气泡回答）→ 底部钉住的提交钮。
- 接口：`window.claude.complete(prompt)`，`try/catch` + `.catch()`；无接口时走兜底文案。Prompt 必带本考点知识口径 + 老师人设（龙安欢/东北口语/按采分点）。

### 4.8 练习题卡（练习页）
进度条 + 题号/维度标签 → 题干 → **图示区**（每题必有：标尺/变化图/管道图/诊断图/答题纸）→ 选项（完整采分句，非关键词）→ 提交后每项展开解析 → 「📝 抄进答题纸的采分句」暗卡 → 行动钮 + 「🤖 这道题没搞懂？问追AI（已带题目）」。

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
- **标尺命中** `threshold_ruler`：多档×多子轴分级带 + 数值探针滑动 + 命中高亮 + 取最高（计算判定链类）。
- **流程管道** `report_pipeline`：有向节点 + 载体（信封/公文）流转 + 错误支路红✗淘汰 + 时钟（程序/时限类）。
- **成员围合** `investigation_group`：人头芯片 staggered 飞入围成组（主体/清单类）。
- **处理链** `handling_chain`：建议→批复→执行 + 双追责印章 + 自裁红✗（因果/责任类）。
- **现场剪影** `site_scene`：脚手架+斜撑+坠落小人+安全帽+防护栏+地面线+伤亡标签（事故物理来源）。
- **答题纸扫描** `answer_sheet`：采分句卡 + 高亮笔从左扫到右点亮关键词（收束）。

> 现场/舞台对象用 `top:` 定位（容器无固定高度时 `bottom:` + `top:0` 子元素会向下跑被字幕挡住——踩过的坑）。

---

## 6. 文案 / 配音

- 老师 voice **longanhuan_v3**；学生 voice **longlaotie_v3**。
- 老师：自然口语，"注意哈/记住哈"只在开头结尾少量用，面向阅卷采分点。
- 学生：东北男孩口吻，真诚不耍贫、不变段子。
- QA 放主讲之后，**至少三问三答**（母版四问四答）。主讲完整连贯，5 分钟内可长。

---

## 7. 生产流程（每个新考点照走）

1. 读成品 MD → 提炼 `source_card`：main_exam_action / wrong_idea / teaching_spine / facts / common_errors / practice_blueprint。
2. 查视觉原型盘点 → 冻结 `visual_archetype_decision`（6+1 判定）+ `domain_visual_plan`（学生必须看见哪些对象、如何进/移/命中/淘汰/退出、为什么文字框不行；≥4 个主讲 scene 出现领域对象）。
3. 写 5–8 beat 白板 storyboard：每 beat 一个视觉动作 + 一句旁白 + 离场说明。
4. 生成 `lesson.json`（含 source_card / archetype / domain_visual_plan / storyboard / student_qa / animation_ir.v0）。
5. 生成 `animation_ir.v0`：每 scene 明确 scene/focus/enter/hold/exit/layout/camera/visible_nodes/keycard/coach/actions/visual_library。renderer 只消费 IR，HTML preview 与 Remotion 吃同一份。
6. 产出讲解页 DC + 练习页 DC（+ 本地跑 TTS/timing）。
7. practice 精品标准：每题有图、答前不泄答案、选项是完整采分动作、每错项三段解析（为什么容易选/为什么扣分/正确补哪句）、末题训练采分句输出或诊断、结果页含表现+薄弱点+继续补练+问鲁班。
8. 过 gate 后才进 `finished/<ID>/`。

### 验证清单
源 workflow gate · `build_aliyun_lesson_narration.mjs --print` · `validate_animation_ir_contract.mjs` · `render_animation_ir_preview.py` · `validate_animation_ir_preview.mjs` · `render_animation_ir_practice.py` · 390px 截图 · practice 真实点击冒烟（选择/反馈/下一题/结果页）· finished 相对路径可访问 · 8800 本地可开。

### 红线
不做纯文字框/流程框/判断框 · 不把 6+1 当标签 · 安全合同管理类不退回文字 · 不只整页淡入淡出 · 不拿粗稿当成品 · 不用 emoji 表情符号 · 没过 gate/没截图/没冒烟不进 finished · 预览阶段不出 MP4。

---

## 8. 命名 / 文件

- 讲解页：`<考点名>_讲解.dc.html`；练习页：`<考点名>_练习.dc.html`；数据：`<考点名>_lesson.json`。
- 两页互链：讲解页底「做练习 →」；练习页头「看讲解 →」。
- 打包真机预览：讲解页加 `<template id="__bundler_thumbnail">`（红底+鲁字 SVG）→ `bundle_project` 出临时公网 URL（约 10 分钟失效）。
- 长期 / 小程序：H5 走 web-view（需备案域名 + 后端接 AI/TTS），或 Taro/uni-app 重写（RAF 动画改成小程序渲染驱动）。
