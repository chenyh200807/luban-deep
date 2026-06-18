# style-guide.md · 图解微课卡视觉/认知单一源

> **所有卡的颜色、字体、SVG 纪律、认知负荷规则的唯一来源。** 每张卡、每个原型都引用本文,不各调各的。
> 现状:`artifacts/luban_case_family_assets/diagram_microlesson/render_card.py` 的 `:root` 变量是雏形;本文是它该收敛到的规范。

## 一、语义配色板(color = 意义,不是装饰)

配色是 **signaling**(系统化用色标识/区分信息,经证实提留存、降认知负荷),不是好看。固定语义,跨所有卡一致:

| token | hex | 语义 | 用在哪个原型 |
|---|---|---|---|
| `--correct` / green | `#1aa06d` / bg `#e8f7f0` | **对 / 命中 / 已掌握 / 流程完成** | ⑤对错、⑥hit、①终点 |
| `--wrong` / red | `#d9534f` / bg `#fdecea` | **错 / 漏点 / 危险** | ⑤对错、⑥miss、安全危险 |
| `--partial` / amber | `#e08a1e` / bg `#fdf2e3` | **部分命中 / 风险 / 告警 / 易错** | ⑥partial、错因、风险提示 |
| `--progress` / blue | `#2f6df0` / bg `#eaf1ff` | **流程进度 / 当前步 / 中性强调** | ①步骤、当前焦点 |
| `--critical` / red-hi | `#d9534f` | **关键线路高亮**(图结构) | ③关键线路 |
| `--ink` | `#1d2530` | 正文主色 | 全 |
| `--sub` | `#6b7686` | 次要/说明文字 | 全 |
| `--line` | `#e7ebf0` | 1px 细线/边框 | 全 |
| `--bg` | `#eef1f5` | 页底 | 全 |

**层色编码(②构造型专用)**:同一剖面里不同构造层用不同稳定色(基层=灰 `#cdd6e2` / 防水层=蓝 `#2f6df0` / 附加层=绿 `#1aa06d` / 保护层=琥珀 `#e08a1e`),**一层一色、跨卡一致**,让"哪层是什么"一眼对上。

铁律:**绿=对、红=错** 永不互换;**关键线路恒红**;**采分点 hit绿/partial琥珀/miss红**。

## 二、字体(三族分工)

| 角色 | 字族 | 用途 |
|---|---|---|
| 标题 | -apple-system / PingFang SC 粗 | 卡标题、步骤主标题 |
| 正文 | -apple-system / PingFang SC | 解释、采分表达 |
| 技术标注 | ui-monospace / Menlo | 采分点号、错因码、数值(等宽对齐) |

手机字号:标题 14-16px / 正文 12-13px / 标注 10-11px。

## 三、SVG 纪律(借 svg-precision + diagram-design)

- **self-contained**:纯内联 `<svg>`,**无外链、无 CDN、无 JS**(iOS 快速查看不跑 JS;交互靠静态/CSS 或宿主)。
- **viewBox + 显式 width/height**;**绝对坐标**优先,transform 只为降复杂度。
- **坐标/宽/间距尽量被 4 整除**;1px hairline、无阴影、圆角 ≤10px。
- **可复用元素**(箭头 marker、渐变、clipPath)进 `<defs>` 按 id 引用;**不用 exotic filter**;**无 NaN/inf**,数值留 3-4 位小数。
- **文本是渲染风险**,优先形状表达;关键标注用文本但位置固定。
- **no Mermaid-slop**:不要通用圆角框堆;构造图是工程示意,**手作/图元库,不文生图**。
- 移动端聚焦:`viewBox` 给手机一个聚焦窗口,隐藏浮动 callout,**390px 无横向滚动**。

## 四、认知负荷纪律(Mayer 多媒体学习 + 色彩 signaling 研究)

- **signaling**:箭头/高亮引导视线到关键元素(降外在认知负荷)。
- **一屏一个判断点**:不要一屏塞多个并行结论。
- **分段呈现**:复杂过程拆步,一步一屏;**允许暂停/回看/重播/切静态图**(抵消动画 transient information 流逝问题)。
- **冗余最小**:图说清的别再大段文字重复(空间/时间邻近原则)。
- **暖但专业**:考生不是小学生;文案先肯定→点差距→给安全网,**绝不毒舌**(见 [[wow-see-through-must-be-warm-not-harsh]])。
- **每条动效通向一次练习/反馈**:看完必有"复测/补答/下一步",否则不发。

## 五、student-safe(脱敏,跨所有原型)

学生端**禁止出现**:`source_ref` / `P10`/`P11` 等采分点内部号 / `schema` / `renderer` / `candidate` / `母题包` / `本系统`。
内部口径(source_boundary)只进 HTML 注释,学生看到的是 `student_boundary`(如"这是教研估分讲解,不是官方阅卷;图为示意,数值以教材规范为准")。
