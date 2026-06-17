# 图解母题卡 · 移动端 UX 重排验收（F16 / N01）

> **v2 更新（2026-06-17 晚）· 翻页 deck**：按产品反馈"宁愿多几页也不要长滚动、一页一个重点"，F16 从"折叠长页"进一步改成**翻页 deck**——一屏一个重点，点「下一步」一屏屏走。
> - 结构：**11 屏** = 8 步（每步一屏：聚焦图 + 步骤标题 + 老师讲一句 + ✍这样写才得分；为什么/你常漏折在"＋"里）+ 错因屏 + 复测屏 + 收束屏。
> - **整页高度 2958 → 930px**（≈ 一屏），单屏基本不滚；底部「上一步/进度/下一步」固定常驻。
> - CDP 实测：默认 screen0=step1（activeLayer=identify_bulge）、`scrollWidth===390`、翻到第 8 步→错因→复测、答错跳回对应步（practice_incorrect→reinforcement_layer）、错因卡跳转（mode=error, activeError）、`#step=k` 深链、所有 dataset 钩子均正常。
> - 旁白改为 deck 内"听老师讲"自动逐屏推进；renderer 仍只渲染不判分；学生端无内部词；无外链/音频。
> - 截图：`F16_qigu.rendered.mobile.png`（首屏=第 1 步）。
> - N01 暂仍是上一版（固定底部条 + 两列），尚未改成 deck。
>
> 以下为 v1（折叠长页）记录，保留备查。

---


- **日期**: 2026-06-17
- **触发**: 真机/模拟器试用反馈——"一页内容太多要狂滚、『下一步』藏太深要往下拉半天"。
- **范围**: 只改 renderer 的布局/CSS/交互（`render_card.py` / `render_network_card.py`），**未动 schema、数据、判分、DOM 钩子、单一权威边界、无外链约束**。

## 设计方向
受硬约束（无外链/无 web 字体→系统字体、390px、无横向滚动、微课）。对象是忙碌备考成人，方向选**克制·聚焦·拇指优先的单步体验**，不是花哨堆料。

## F16 改了什么
1. **底部固定操作条**（`#stepNav`）：`上一步 ｜ 进度 N/8 ｜ 下一步` 在移动端 `position:fixed` 钉屏幕底，**不管滚到哪都在手边**；body 加底部留白避免遮挡。→ 解决"下一步藏太深"。
2. **侧栏 4 张说明卡 → 分段切换**：`怎么写得分 ｜ 为什么 ｜ 你常漏 ｜ 算不算分`，一次只显示一张（默认"怎么写得分"）。→ 解决"4 张堆着要狂滚"。
3. **下半部 → 默认收起的折叠块**：`你常犯的错` / `复测一题` / `得分要点+收束` 用原生 `<details>` 默认收起；快速导航点一下自动展开并滚到对应块。→ 默认只露"看工序"主区。
4. **头部/步骤瘦身**：移动端隐藏 goal-chip、副标题与 caption 收成 2 行、8 个步骤改一行**横向滑动条**。

## N01 改了什么
- 同款**底部固定操作条**（`上一步/下一步` 移动端钉底）+ 步骤改两列，体验与 F16 一致。

## 验收（CDP, 390px）
| 项 | 改前 | 改后 |
|---|---|---|
| 整页高度 | 2958px | **1698px**（≈ −42%） |
| `下一步`位置 | 滚到很深才见 | **固定屏幕底，首屏即见**（`position:fixed`，视口底 775–844px） |
| 说明卡 | 4 张同时铺 | 分段，默认 1 张（"怎么写得分"） |
| 下半部 | 顺排 4 段 | 折叠块默认全收起（errors/practice/points = closed） |
| 快速导航 | 锚点滚动 | 点击**展开**对应折叠块 + 滚动 |
| `scrollWidth===390`（无横滚） | ✓ | ✓ |
| 默认 activeLayer / 步骤推进 / 分段切换 | — | 均正常（identify_bulge → cut_bulge，mini 1/8→2/8） |
| 无外链 / 无音频 | ✓ | ✓ |
| schema 校验器 | 4/4 OK | 4/4 OK（未动 schema） |

## 不变（守住的边界）
- 所有 DOM 断言钩子（`dataset.activeLayer/narrMode/activeError`、`#prevBtn/#nextBtn/#progressBar/#practiceFeedback`、`.step-tab/.error-card/.option`）保留可用。
- 旁白播放 / 错因跳步 / 复测对错反馈逻辑未改，仅容器位置变化。
- renderer 仍只渲染、不判分；学生端不露 source_ref/schema/renderer/candidate 等内部词。

## 截图
- `F16_qigu.rendered.mobile.png`（全页，折叠后）
- `F16_qigu.rendered.mobile.firstscreen.png`（首屏，含固定底部条）
- `N01_network_keypath.rendered.mobile.png`

## 仍可继续（未做）
- 若想更紧：把"听老师讲"旁白与侧栏 step 文案的重复进一步合并；步骤条加当前步高亮滚动居中。
- N01 也可引入分段/折叠（当前只做了固定底部条）。
- 真机字体/滚动惯性、iOS 锁屏计时器仍需真机复核（见 `miniprogram_hidden_sandbox_eval.md`）。
