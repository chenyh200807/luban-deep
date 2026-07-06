# 鲁班智考 · 学习 tab 前端第一片设计(五模块重建 Slice 1)

> **Status: Approved slice / 设计稿。**
> **定位**:把第 10 轮定稿(纸墨朱竹宣纸语言)的**学习 tab(10a 亮 / 10b 夜)**落进
> 微信小程序 `packageDeeptutor`,作为五模块前端重建的第一垂直片。它同时是我们刚做完
> 并扛过 Codex 对抗的后端 read model(`home_next_step_projection` / `pack_lifecycle` /
> `revalidation_queue` / learning-report stats + `/api/v1/lesson-progress`)的**精确消费者**。
> **Date: 2026-07-04**
> **设计单一真值(仓库内 #350 资产,非 Downloads 副本)**:
> `docs/plan/鲁班移动端提分闭环/设计资产-五模块第10轮/鲁班智考五模块·第10轮定稿.dc.html`
> 的 `#10a`(学习亮)/`#10b`(学习夜)。Downloads 副本经 diff 与本仓库版逐字节一致。
> **IA/硬约束 authority**:[五模块 IA Brief `2026-07-02-luban-five-module-ia-frontend-brief.md`(#352,Approved)](2026-07-02-luban-five-module-ia-frontend-brief.md)——本片必须遵守其 **H1-H5**(见 §2.1)。
> **上游**:[双轮 v3.2] · [融合计划 v1.1](2026-07-03-luban-proactive-learning-lifecycle-fusion-plan.md)。

## 2.1 五模块 Brief H1-H5 硬约束在本片的落地

| 约束 | 本片如何遵守 |
|---|---|
| **H1** 错因标签绑 read model,禁写死 | 「待补错因」指标卡读 report 的真实错因计数/码,不硬编码"固定 10 类";码在 `ERROR_CODE_REGISTRY`(内核现主吐 E02/E07) |
| **H2** Long Cang 字体只许 CDN 子集化,禁内嵌 | 小程序用 `wx.loadFontFace` 从 CDN 加载 Long Cang 子集;**加载失败即降级 `'Kaiti SC', serif`**,绝不内嵌字体文件(防回退 D6);仅教学动画模块(海报竖排考点名 + 舞台标题)用它 |
| **H3** 母题绑 manifest `pack_id`,禁旧 F 系列硬编码 | 路线/课程架/下一站全部按 `pack_lifecycle` + `/api/v1/luban/lessons` 的真实 pack_id 渲染;**首发只有绿灯 pack 是"可学",其余一律"即将开通"**,不硬编码任何 F/S 站 |
| **H4** 四包计费默认关待 owner | 本片不做计费;"会员解锁"只作 `pack_lifecycle` 锁态的**视觉呈现**(未学·锁),不接支付,四包远程开关不碰 |
| **H5** 五色命中态=纯视觉编码 | 学习页不含判分命中态(那在批改结果页);本片不发明任何判分语义 |

---

## 0. 为什么是这一片(first principles)

五模块 = 6 屏完整重建,一次做完必糊。按 tab 切垂直片。**学习 tab 第一**因为:
1. 它是设计的**默认落地页**(可见度最高);
2. 它是**已就位后端的精确消费者**——建它 = 端到端闭合我们这一路的工作,而非另起孤岛;
3. 它含已认可的**微课解锁点**(讲懂 web-view + lesson-progress),放进设计好的家;
4. 另外 4 tab 大半是"现有页归位"(report→学情 / chat→对话 / mistake-book→复习 / profile→我的),纯新建的就是学习页。

## 0.1 两个已拍板决策(用户离开时按推荐值定,待复核)

| 决策 | 定值 | 理由 |
|---|---|---|
| 微课 web-view 内容源 | **先挂后端 `card_url`**(= test2 已托管 `luban-preview/<pack>/lesson.html`) | 前端忠实消费后端真契约、现在就能跑通;"纸墨朱竹新卡(`anim-card-page1.html`)进 luban-preview 发布管道"列为**独立内容任务**,接线不变,内容升级后 web-view 自动换皮 |
| 底部导航 | **画设计的 5 tab(学习/复习/问鲁班/学情/我的),点其余 tab 路由到现有页** | 学习页成为真首页;过渡期现有页保留旧底栏,后续片再归位 |

## 1. 组件清单 ↔ 后端 read model 接线契约

学习页 = 402×874 宣纸驾驶舱,自上而下:

| # | 组件(设计锚) | 数据源(read model) | 字段缺失时降级 |
|---|---|---|---|
| 1 | 顶栏:logo 章 + 设置点 | 静态 | — |
| 2 | 状态卡×3:距考 / 路线 12/40 / 今日 X/Y 分 | 距考=profile 考试日期(本片占位);路线=`pack_lifecycle`(点亮数/40);今日=report stats | 缺→占位数字/隐藏进度 |
| 3 | 动画精讲卡 header:下一站 · S07 + 「匹配你的薄弱」+ 为什么推荐 | `home_next_step_projection`(`source_ref`=pack、`reason`=为什么、`mode`) | 缺→"内容即将上线"空态卡 |
| 4 | 宣纸舞台:旁白/全屏/Long Cang/播放 + "6 幕精讲…" | `/api/v1/luban/lessons/{pack}` → `card_url`(web-view) | 缺/404→播放键禁用+"微课即将上线" |
| 5 | 你的路线 · 已点亮 12/40 + 横滑课程架三态海报(墨已学/朱推荐/纸未学-锁) | `pack_lifecycle`(mastered/practiced→已学;下一站→推荐;unlearned→未学;绿灯与否→锁) | 缺→只显 fallback 首站或空态 |
| 6 | 今日任务卡:半写训练 1 题 + 掌握可信度 72% + 为什么推荐 | `next_step` practice 臂 / training prescription(report) | 缺→隐藏或"先做一题摸底" |
| 7 | 复习到期条:复习 3 张到期 · 去复习 → | `revalidation_queue`(items 数) | 缺/0→隐藏该条 |
| 8 | 指标卡×3:近 3 天练习 / 待补错因 / 掌握趋势 | report evidence stats | 缺→"0"或隐藏 |
| 9 | 底部 tab(学习/复习/问鲁班/学情/我的) | 静态 + 路由 | — |

**降级铁律**:任一 read model 字段缺(= test2 今天的状态,后端未部署)→ 该组件显示合理空态,**整页绝不崩、不留裂口**。这是本片在 test2 上唯一能验的行为(渲染+降级)。

## 2. 单一权威边界(继承融合计划 §8 + 评审要点摘要)

- **前端不算分、不算掌握度**——只投影后端 read model(评审要点 §19)。掌握/点亮/可信度全部读字段,前端零推断。
- **不新增第二套聊天入口**——问鲁班中央 tab 路由到现有 `/api/v1/ws` 对话页(chat),不建新 WS。
- **lesson-progress 上报走唯一 writer**——看完 CTA → `POST /api/v1/lesson-progress`(唯一学-evidence writer),前端不碰账本。
- **文案铁律**——禁"看穿/识破/揭穿/露馅";对="你是真懂了,不是背的✅",错="这一点再看一眼就稳了↺"(评审要点 §46 + copy-tone memory)。

## 3. 视觉体系(纸墨朱竹 · 做成可复用 token,后 4 tab 复用)

- 宣纸底 `#f5f3ec` + 18px 点阵 `radial-gradient(#e4e0d0 .7px, transparent .7px)`;暖白卡 `#fffdf8`,边 `#e7e3d5`
- 墨色文字三阶 `--t1 #26241f / --t2 #5b584e / --t3 #96917e`;竹青正向 `--grn #48806a`;gauge 底 `--gauge #e9e5d7`
- **朱红 `#cf4436` 只留品牌四处**:logo 章 / 播放键 / 红海报 / 问鲁班中央章;UI 控件一律不用红(主按钮/倒计时/当前 tab 用墨色,警示用赭 `#c26555`)
- 亮(10a)/夜(10b)双主题:夜=夜宣纸暗,主按钮反转为纸色
- Long Cang 书法体仅用于教学动画模块(海报竖排考点名 + 舞台"鲁班智考");wxss 用 `'Long Cang','Kaiti SC',cursive` 兜底
- 单位换算:设计 px → 小程序 rpx(×2,以 375pt 设计宽为基,`402px` 屏按比例)

## 3.9 关键发现:spike 已建可用播放器(复用,不重造)

调查发现 2026-07-02 spike 已落 `packageDeeptutor/pages/luban/`:
- `stations`:站点列表(拉 `/api/v1/luban/lessons` 绿灯站,navigate 到 station)
- `station`:**两幕 web-view 播放器**——幕1 讲懂 `card_url`→幕2 闯关 `practice.html`→跳 handoff(已接 `getLubanLessonDetail`)
- `retest`:变体复测(拉 `/retest-items` 本地判分,telemetry only)
- `handoff`:交接时刻(明天见订阅授权)

**它缺的恰是本片要补的**:①`lesson-progress` 学-evidence 上报(station 页注释明写"零学习证据写入·本页不碰"——我的新端点没接);②第 10 轮纸墨朱竹**学习 home**;③消费 `next_step`/`pack_lifecycle`。

**打法收敛(less is more:复用 > 重造)**:
- **不新建 lesson 播放页**——复用 spike 的 `luban/station`(已工作的 web-view 播放器)
- 本片新建的只有**学习 home**(`pages/learn/learn`,纸墨朱竹宣纸驾驶舱),它的下一站卡「播放」/ 课程架 / 完整路线 → navigate 进现有 `luban/station`、`luban/stations`
- **lesson-progress 接进现有 `luban/station` 讲懂幕**(补上缺的学-evidence writer),不在新页做

**决策(用户 2026-07-04 拍板 = (b)-深)**:station/stations 现用旧板岩靛蓝(原 report 那套 #818cf8/#7dd3fc),本片**顺带重塑成纸墨朱竹,按第 10 轮定稿原则,视觉一次到位**。深度=**深**:stations 站点列表改成设计的**竖排书法海报路线图**(84×112,墨/朱/纸三色轮替,Long Cang 竖排考点名),复用学习 home 的"课程架"同一组件;station 播放页 native 壳(loading/error/footer)刷纸墨朱竹色。逻辑/结构不动,只换视觉层 + 列表→海报重构。
- **诚实边界**:(b) 让 native 外壳一路纸墨朱竹不换脸;但 web-view 里加载的**卡内容本身**(讲懂/闯关 HTML)仍是旧 luban-preview,换成纸墨朱竹新卡=独立内容任务(发进 luban-preview 托管)。"视觉一次到位"= 外壳一次到位,卡内容待内容任务。

## 4. 文件结构(新建学习 home + 复用 spike 播放器)

```
packageDeeptutor/pages/learn/          # 新建:纸墨朱竹学习 home(宣纸驾驶舱)
  learn.js/.wxml/.wxss/.json
packageDeeptutor/styles/
  paper-ink.wxss    # 新建:纸墨朱竹可复用 token(后 4 tab 复用)
packageDeeptutor/utils/
  learn-view-model.js  # 新建:纯函数 read model → 页面 data(node 测试)
packageDeeptutor/pages/luban/station/  # 复用(spike):补 lesson-progress 上报到讲懂幕
  station.js        # 幕1 讲懂 web-view 后 → postLessonProgress(lesson_viewed)
packageDeeptutor/utils/api.js          # 补:postLessonProgress(唯一缺的 API 封装)
```

- app.json 注册 `packageDeeptutor/pages/learn/learn`(station/stations 已注册)
- 请求复用现有 `utils/api`(已有 getHomeDashboard/getLubanLessons/getLubanLessonDetail/
  getLearningReport;只补 `postLessonProgress`)——不新建网络层
- 学习 home 播放键/课程架 → `route`/`navigateTo` 进现有 `luban/station`、`luban/stations`

## 5. 数据流

```
learn.js onLoad/onShow
  → 并发: GET next_step(home dashboard) · learning-report(pack_lifecycle+stats+revalidation) · luban/lessons(绿灯)
  → learn-view-model.build(responses)  # 纯函数,全程 optional-chaining 降级
  → setData(viewmodel)
播放键 tap → navigateTo lesson?pack=<source_ref>
lesson.js → GET /api/v1/luban/lessons/{pack} → web-view src=card_url
  看完 CTA tap → POST /api/v1/lesson-progress {pack_id, watched_stage:"lesson", card_sha}
              → toast "已记下今天看过 · 去闯关" → 回学习页
```

## 6. 测试计划

- **node contract 测试**:`learn-view-model.js` 纯函数——喂 mock read model(齐全/字段缺/全空)断言 setData 形状 + 降级不抛;喂含新字段的 report 断言路线点亮数正确;喂空断言 fallback 站非空(day-0 不白屏)。
- **DevTools 冒烟**:指向 `deeptutor-fusion-exec/yousenwebview`,reLaunch learn 页 → 断言渲染非空 + 无 JS error(降级态);lesson 页 web-view src 正确拼装。
- 后端未部署 → **不做**"真数据点亮"的 E2E(如实标 pending,等 stage0 部署到 test2)。

## 7. 边界(YAGNI · 不在第一片)

- 另外 4 tab(复习/对话/学情/我的)的重建与现有页归位 → 后续片
- 练三档真答题流(半写/默写/全量作答)→ 按钮先 navigate 现有 practice/chat,答题流后续片
- next_step 的 `practice_active` 臂在首页无干净读源(融合计划遗留)→ 本片今日任务卡优先读 report 处方,practice 臂通电后接
- 生命周期蓝环在**学情页**(10e)的独立呈现 → 学情片
- 纸墨朱竹新动画卡进 luban-preview 发布管道 → 独立内容任务
- 后端部署 test2 → owner

## 8. 待 owner / 用户复核

1. §0.1 两个决策(微课内容源 / 底部导航)按推荐值定,请复核。
2. 距考试天数数据源(profile 考试日期字段是否存在、本片是否占位)。
3. 学习页成为默认落地页后,现有 `freeCourse` 首页 / 入口桥关系(是否本片就改落地,还是先加入口)。
