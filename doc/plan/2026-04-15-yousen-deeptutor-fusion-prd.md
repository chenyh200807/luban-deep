# PRD：佑森小程序与 DeepTutor 原生融合方案

## 1. 文档信息

- 文档名称：佑森 x DeepTutor 小程序融合 PRD
- 文档路径：`/doc/plan/2026-04-15-yousen-deeptutor-fusion-prd.md`
- 创建日期：2026-04-15
- 状态：Draft v1
- 适用范围：
  - `yousenwebview/`
  - `wx_miniprogram/`
  - 微信小程序宿主运行时
  - 佑森首页入口、登录、聊天、历史、学情、我的

## 1.1 当前执行状态（2026-04-15）

### 已完成

1. 宿主 `yousenwebview` 已注册 `packageDeeptutor` 分包。
2. `freeCourse` 浮动入口已从 H5 入口切回 Deeptutor 原生分包入口。
3. 宿主 `app.js` 已补齐 Deeptutor 一期所需的最小运行时：
   - `checkAuth`
   - `logout`
   - token 恢复
   - API / gateway URL
   - 网络状态基础监听
4. `packageDeeptutor` 已复制 Deeptutor 主要页面、utils、components、images、custom-tab-bar。
5. `packageDeeptutor` 内的绝大多数旧 `/pages/...` 路由和分包绝对路径问题已完成第一轮收口。
6. `freeCourse -> login -> chat` 已补上来源与回跳协议：
   - 入口会透传 `entrySource`
   - 登录/注册/手动登录成功后按 `returnTo` 回跳
   - 登录页间切换会保留来源与回跳信息
7. `chat` 页已修正为“先鉴权，再恢复待续会话”，避免 token 失效时先触发历史恢复请求。
8. `packageDeeptutor/utils/endpoints.js` 已锁死生产默认远端地址，避免宿主运行时缺字段时静默回退到 `127.0.0.1`。
9. `billing` 页已补回退兜底，空栈时不再停留在无效返回状态。
10. 宿主已支持从远端响应对象同步 Deeptutor 入口开关：
   - `app.js` 已支持从响应 payload 中提取 `deeptutor_entry_enabled` 等布尔字段
   - `index/gettopzm` 已兼容对象响应并同步入口开关
   - `freeCourse/Getmajorzm` 已在课程接口返回后同步入口开关
11. Phase 2 已开始接入页面级 Workspace Shell：
   - `history / report / profile` 已挂载 `workspace-shell` 普通组件
   - `helpers.syncTabBar` 已兼容页面级组件同步
   - `history` 编辑态已接入 shell 显隐控制
   - `chat` 因固定输入区冲突，当前阶段暂不挂底部 shell 组件
   - `custom-tab-bar` 已暴露统一 `syncState` 协议，页面不再直接散落写入组件内部状态
   - `history / report / profile` 的底部预留已统一抬高，按 shell 高度与安全区口径兜底
   - 已补上 `workspaceBack` 运行时状态，`history -> chat`、`workspace-shell -> chat`、`profile -> report` 不再形成返回死路
   - `chat` 顶栏已增加最小“返回工作区”胶囊按钮，并保留原 logo 的 Hero 主页语义
   - `report / profile` 顶栏返回文案已按工作区来源动态切换
12. `freeCourse` Deeptutor 入口已支持后端下发动态配置：
   - `title`
   - `subtitle`
   - `tip`
   - `badge`
   - `variant`
   - 兼容平铺字段与对象字段两种返回风格
13. 宿主已支持 Deeptutor Workspace 级 feature flags：
   - `deeptutor_workspace_enabled`
   - `deeptutor_history_enabled`
   - `deeptutor_report_enabled`
   - `deeptutor_profile_enabled`
   - `deeptutor_assessment_enabled`
14. Phase 2 工作区页面已接入 flags 约束：
   - `history / report / profile` 进入前会做页级 gate
   - `custom-tab-bar` 已按 flags 过滤可见项
   - `chat` 已按 flags 隐藏个人中心入口并关闭 assessment 弹窗
   - `report / profile` 的 assessment/report 入口已按 flags 降级
15. Deeptutor 漏斗埋点已接入客户端最小闭环：
   - `deeptutor_entry_expose`
   - `deeptutor_entry_click`
   - `deeptutor_login_success`
   - `deeptutor_first_question_start`
   - `deeptutor_first_answer_done`
16. `chat` 页已开始收口 Workspace Shell 显隐语义：
   - `onShow / clearMessages / _onChatScroll / _doSend / onToggleTheme` 不再各自直接写死 shell 显隐
   - 改为统一经过 `chat` 页内的单点显隐判断
17. Deeptutor 运行时已增加宿主读取薄层：
   - 新增 `packageDeeptutor/utils/host-runtime.js`
   - `endpoints.js / ws-stream.js` 已改为依赖该薄层读取宿主 API/gateway/chatEngine
   - 减少 Deeptutor 内部直接碰宿主 `globalData` 的范围

### 进行中

1. 把 Deeptutor 页面中残留的 `getApp().globalData` 直接耦合进一步收敛到可审计的宿主 runtime contract
2. 收口宿主侧入口开关与入口稳定性，并与后端返回字段正式对齐
3. 做 Phase 1 的微信开发者工具编译与真机验收
4. 收口 Phase 2 页面级 Workspace Shell 的布局、底部留白、flags 显隐与交互一致性

### 未完成

1. 微信开发者工具真实编译验证
2. `login -> chat` 真机链路打透
3. 后台可控的 Deeptutor 入口/工作区开关联调验证
4. `chat` 页的 Workspace Shell 最终形态
5. PRD Phase 2：
   - `history`
   - `report`
   - `profile`
   - Workspace Shell
6. 埋点、灰度与正式发布治理

## 2. 执行摘要

本项目的真实目标，不是“让两个同 AppID 的独立小程序互跳”，而是：

**在不新开第二个正式 AppID 的前提下，让 `yousenwebview` 成为宿主小程序，把 DeepTutor 以原生模块方式无缝接入，并达到可持续演进、可灰度发布、可合规上线的产品级标准。**

核心结论如下：

1. `yousenwebview` 与 `wx_miniprogram` 当前是两个独立工程目录，但同属一个 `appid=wx6d4fbd3776ea7d4d`。
2. 在微信运行模型下，同一个 `appid` 不能被当成两个可原生互跳的独立小程序。
3. 如果不新增正式第二个 `appid`，唯一正确的原生路线是：
   - `yousenwebview` 作为宿主
   - DeepTutor 代码保持独立模块化
   - 发布时合包
4. 这件事可以做，而且工程量可控。
5. 真正的复杂点不是代码量，而是：
   - 全局 `App` 能力合并
   - 路由模型重构
   - Deeptutor 现有 `tabBar` 语义迁移
   - 登录态与全局状态统一

本 PRD 推荐的目标架构是：

- **一期**：先打通 `freeCourse` 浮动入口 -> Deeptutor 原生 `login + chat`
- **二期**：建设 Deeptutor Workspace Shell，接入 `history / report / profile`
- **三期**：做到账户体验、性能、埋点、风格和运营能力达到正式产品线标准

## 3. 背景

当前存在两套微信小程序前端：

1. 佑森宿主小程序：`/yousenwebview`
   - 当前承载首页分发、免费课、WebView、小店等业务。
   - 启动入口较轻，业务以课程导流为主。

2. DeepTutor 小程序：`/wx_miniprogram`
   - 当前承载登录、聊天、历史、学情、我的、摸底测试、练习、会员等原生能力。
   - 具备更完整的 AI 学习产品体验。

用户希望的不是 H5 跳转，而是：

- 在佑森现有首页场景中留出 Deeptutor 入口
- 用户点击后进入原生 Deeptutor 体验
- 技术上尽量保持两套代码边界清晰
- 产品上不让用户感觉在两个系统间来回切换

## 4. 问题定义

### 4.1 当前核心问题

当前无法直接实现“从 `yousenwebview` 原生跳到 `wx_miniprogram`”的根因，不是按钮逻辑，而是运行边界：

1. 同一个 `appid` 不等于两个独立可跳转的小程序
2. 小程序原生路由只能进入当前编译包中已注册页面
3. Deeptutor 页面当前不在 `yousenwebview/app.json` 中
4. Deeptutor 页面大量依赖自己的 `App.globalData`、`checkAuth()`、网络状态和路由语义
5. Deeptutor 现有产品结构依赖 `tabBar` 四栏，不是一个单页聊天组件

### 4.2 根因

根因不是“文件没放一起”，而是两套工程当前分别拥有：

- 各自的 `app.json`
- 各自的 `App()`
- 各自的页面体系
- 各自的导航模型
- 各自的运行时全局状态

因此本项目本质上是一个：

**宿主小程序 + AI 原生子系统 的融合工程**

而不是简单的“加一个按钮”。

## 5. 事实约束

### 5.1 微信平台约束

1. 同一个 `appid` 在客户端只对应一个小程序包。
2. `wx.navigateToMiniProgram` 语义是“打开另一个小程序”，不适用于同 `appid` 下两套独立工程互跳。
3. `app.json` 中的 `pages` / `subpackages` 才决定当前包里有哪些原生页面。
4. 微信官方分包文档明确指出：
   - 主包放默认启动页和 `TabBar` 页面
   - 独立分包不能依赖主包和其他分包中的内容
   - 从独立分包启动时，`getApp()` 可能拿不到真实 `App`

### 5.2 当前代码约束

1. `yousenwebview/app.js` 很轻，仅有基础 `wx.login`
2. `wx_miniprogram/app.js` 承担了 Deeptutor 的：
   - API 地址解析
   - token 恢复
   - `checkAuth`
   - `logout`
   - 主题
   - 网络状态监听
3. Deeptutor 页面大量依赖 `getApp().globalData`
4. Deeptutor 当前 `chat / history / report / profile` 都按 `switchTab` 模型组织
5. Deeptutor 并非超大包，体量本身不是阻塞项

已知体量：

- `wx_miniprogram` 目录约 `856KB`
- `yousenwebview` 目录约 `3.4MB`

### 5.3 合规约束

1. 本项目允许设计发布开关、灰度开关、可见性开关。
2. 这些开关只能用于正式的灰度发布、场景控制、内容治理与运营节奏控制。
3. 不得将能力开关设计为“审核看一套、线上给用户看另一套”的规避机制。
4. 教育与教培相关内容需按微信类目和主体要求合规接入。

## 6. 产品目标

### 6.1 业务目标

1. 在佑森现有小程序中建立高转化的 Deeptutor 原生入口
2. 将课程流量自然导入 AI 陪学、答疑、练习、诊断场景
3. 提升留存、学习时长、复访率和付费转化
4. 形成“课程内容 + AI 陪学 + 学情闭环”的统一体验

### 6.2 用户体验目标

目标不是“能打开”，而是达到接近世界一线教育产品的标准：

1. 入口明确
   - 用户一眼知道这是“AI 学习助手”，不是广告位误触
2. 跳转自然
   - 点击后进入原生页面，不出现白屏、无响应、死链、路由报错
3. 登录清晰
   - 未登录用户先完成登录，再进入聊天
   - 已登录用户直接进入核心场景
4. 场景闭环
   - 从聊天可进入历史、学情、我的
   - 从学情可回到聊天和练习
5. 质感统一
   - Deeptutor 是更强的 AI 工作区，而不是风格割裂的外来页面

### 6.3 架构目标

1. 保持 `yousenwebview` 作为唯一宿主小程序
2. 保持 Deeptutor 业务代码尽可能独立，避免被宿主业务强耦合污染
3. 不新增第二套微信聊天入口协议
4. 不破坏 Deeptutor 当前 `/api/v1/ws` 单一流式入口原则
5. 为后续独立 AppID、独立产品、独立商业化预留迁移空间

## 7. 非目标

本次融合明确不做以下事情：

1. 不在本阶段新申请第二个正式小程序 `appid`
2. 不将 Deeptutor 退化为 H5 主体验
3. 不在一期强行保留 Deeptutor 现有全部页面和所有交互细节
4. 不重构后端聊天协议
5. 不在同一需求里同时重做佑森首页整体视觉
6. 不做大规模账号体系重建

## 8. 目标用户与关键场景

### 8.1 目标用户

1. 正在浏览免费课、课程导流页的潜在转化用户
2. 已报名或已接触建筑考试内容、需要即时答疑的用户
3. 有明确备考任务、需要学情和练习闭环的高意图用户

### 8.2 关键场景

1. 免费课首页看到“鲁班AI智考”入口，点击进入
2. 首次进入，完成登录并立即发起问题
3. 聊天后查看历史记录，再次继续某个对话
4. 在学情页查看能力画像、薄弱点、推荐练习
5. 在“我的”里完成设置、会员、协议、退出等操作

## 9. 方案决策

## 9.1 可选方案对比

### 方案 A：继续使用 H5 入口

优点：

- 实现快
- 不需要合包

缺点：

- 不符合本项目“原生 Deeptutor 小程序版”的目标
- 登录、性能、沉浸感、分享能力都弱
- 用户感知明显降级

结论：

- 不采用为主方案

### 方案 B：申请第二个正式 `appid`，独立小程序互跳

优点：

- 架构最干净
- 审核、发布、类目、运营边界最清晰
- 可直接使用 `wx.navigateToMiniProgram`

缺点：

- 需要新增主体/资质/类目/运维流程
- 当前无法立刻落地

结论：

- 长期最优
- 但不是当前最短上线路径

### 方案 C：同 `appid` 下，代码独立、发布合包

优点：

- 符合当前现实约束
- 能提供原生 Deeptutor 体验
- 不需要新增 `appid`
- 代码仍可按模块独立维护

缺点：

- 需要处理运行时和路由融合
- 需要重构 Deeptutor 现有 `tabBar` 语义

结论：

- **本 PRD 采用的正式方案**

## 9.2 目标方案

采用：

**`yousenwebview` 作为宿主主包，DeepTutor 作为独立业务模块接入，并通过分阶段方式从“入口 + 登录 + 聊天”逐步演进到完整 AI Workspace。**

## 10. 顶层产品设计

## 10.1 产品定义

最终对外不是“两个小程序凑在一起”，而是：

**佑森小程序中的 AI 学习工作区**

其中：

- 佑森负责流量、课程、导流和内容触点
- Deeptutor 负责答疑、诊断、练习、学情和 AI 学习闭环

## 10.2 信息架构

目标信息架构如下：

```text
佑森主包
├── 首页分发
├── 免费课
├── 课程详情
├── WebView/小店/既有业务
└── 鲁班AI智考入口
    └── DeepTutor Workspace
        ├── 登录
        ├── 对话
        ├── 历史
        ├── 学情
        └── 我的
```

## 10.3 设计原则

### A. 入口必须场景化，不做“外挂感”

- 入口应放在 `freeCourse` 等高意图场景中
- 入口文案要表达价值，不做纯品牌露出
- 推荐品牌文案：
  - 鲁班AI智考
  - AI 智能答疑
  - 24 小时陪学答疑

### B. Deeptutor 必须是工作区，不是单页问答框

- 如果只做一个聊天页，短期可上线，但长期产品价值不完整
- 真正高价值结构必须具备：
  - 对话
  - 历史
  - 学情
  - 我的

### C. 宿主与 AI 子系统要“强体验、弱耦合”

- 宿主负责入口和场景承接
- Deeptutor 负责自己的工作流与状态
- 不能把 Deeptutor 的页面逻辑散落到佑森业务页里

## 11. 目标技术架构

## 11.1 总体架构

```text
yousenwebview (宿主主包)
├── app.js / app.json
├── pages/index
├── pages/freeCourse
├── pages/...
├── deeptutor-runtime/
│   ├── auth-adapter
│   ├── route-adapter
│   ├── env-adapter
│   └── feature-flags
└── packageDeeptutor/ (普通分包，非独立分包)
    ├── pages/login/login
    ├── pages/login/manual
    ├── pages/workspace/index
    ├── pages/chat/chat
    ├── pages/history/history
    ├── pages/report/report
    ├── pages/profile/profile
    ├── pages/assessment/assessment
    ├── pages/practice/practice
    ├── pages/billing/billing
    ├── pages/register/register
    ├── pages/legal/terms
    ├── utils/*
    ├── components/*
    ├── images/*
    └── workspace-shell/*
```

## 11.2 为什么不用独立分包

虽然微信支持独立分包，但本项目一期不应采用，原因如下：

1. Deeptutor 当前强依赖 `getApp()` 和宿主全局状态
2. 独立分包从自身启动时，`getApp()` 不一定拿得到真实 `App`
3. 独立分包不能依赖主包和其他分包内容
4. Deeptutor 当前不是一个完全自给自足、零全局依赖的前端模块

结论：

- **一期与二期统一采用普通分包**
- 待 Deeptutor Runtime 彻底模块化后，才评估独立分包价值

## 11.3 运行时融合原则

### A. 只能保留一个 `App()`

宿主 `app.js` 成为唯一 `App()` 定义处。

需要把 Deeptutor 需要的全局能力注入宿主运行时，包括：

- token / userId / userInfo
- `checkAuth`
- `logout`
- API / gateway 地址
- 主题
- 网络状态
- Deeptutor 场景级全局变量

### B. Deeptutor 运行时必须命名空间化

不能把 Deeptutor 的所有全局字段直接扔进宿主根层 `globalData`。

建议结构：

```js
globalData: {
  userInfo: null,
  pathurl_route: null,
  deeptutor: {
    token: null,
    userId: null,
    userInfo: null,
    theme: "dark",
    networkAvailable: true,
    goHomeFlag: false,
    pendingChatQuery: "",
    pendingChatMode: "AUTO",
    pendingConversationId: null,
    apiUrl: "",
    gatewayUrl: ""
  }
}
```

同时提供统一适配函数，避免页面直接关心宿主内部细节。

### C. 路由能力必须适配，不可原样复用

当前 Deeptutor 页面大量使用：

- `wx.switchTab`
- `wx.navigateTo`
- `wx.reLaunch`

其中 `switchTab` 语义与当前宿主结构冲突最明显。

因此必须新增 `deeptutorRoute` 适配层，把 Deeptutor 的页面间导航从“依赖 App 级 tabBar”改成“依赖 Deeptutor Workspace 内部路由语义”。

## 11.4 Deeptutor Workspace Shell

这是本项目达到世界级体验的关键设计，而不是可选优化。

### 为什么需要 Workspace Shell

如果直接把 Deeptutor 原本的四个页面粗暴塞进主包，会带来：

1. 宿主首页与 Deeptutor 四栏争夺 App 级 `tabBar`
2. 佑森和 Deeptutor 的导航模型混乱
3. 后续再拆成独立产品很痛苦

因此推荐设计一个：

**DeepTutor Workspace Shell**

其职责是：

1. 提供 Deeptutor 内部的顶部/底部工作区导航
2. 将对话、历史、学情、我的组织成一个统一工作区
3. 保持 Deeptutor 产品完整性
4. 不污染宿主的 App 级结构

### Shell 的形态

可采用：

- 顶部品牌栏 + 底部 Deeptutor 局部导航
- 或顶部切换 + 页面级分段导航

不建议继续强依赖微信全局 `tabBar`。

## 12. 分阶段落地方案

## 12.1 Phase 0：方案与底座准备

目标：

- 完成模块划分、运行时适配设计、路由抽象方案

产出：

- Deeptutor 融合 PRD
- 页面依赖清单
- 路由重写清单
- 埋点方案
- 开关方案

## 12.2 Phase 1：原生入口 MVP

目标：

- 从 `freeCourse` 入口进入原生 Deeptutor
- 打通登录与聊天主链

范围：

- 接入页面：
  - `login`
  - `manual`
  - `chat`
- 接入依赖：
  - `utils/*`
  - `components/*`
  - `images/*`
- 接入 Deeptutor runtime adapter

体验结果：

- 用户点击“鲁班AI智考”入口
- 未登录先进入登录
- 登录成功进入聊天
- 已登录用户直接进入聊天

本阶段暂不承诺：

- 历史
- 学情
- 我的
- 完整会员与练习闭环

## 12.3 Phase 2：Workspace 完整版

目标：

- 将 Deeptutor 升级为完整 AI 工作区

范围：

- 接入页面：
  - `history`
  - `report`
  - `profile`
  - `assessment`
  - `practice`
  - `billing`
  - `register`
  - `legal`
- 引入 Workspace Shell
- 将现有 `switchTab` 迁移为内部路由语义

体验结果：

- 聊天不是终点，而是工作区起点
- 用户可查看历史、学情、我的
- 学情与练习开始形成闭环

## 12.4 Phase 3：产品化与世界级打磨

目标：

- 把“能用”提升为“强产品感”

范围：

- 体验打磨
- 性能优化
- 错误恢复
- 埋点与漏斗
- 灰度与发布管理
- 视觉统一与品牌强化

## 13. 详细功能需求

## 13.1 入口能力

需求：

1. `freeCourse` 页面保留 Deeptutor 浮动入口
2. 入口展示由后台配置控制是否显示
3. 点击后进入 Deeptutor 原生路由
4. 打点记录：
   - 入口曝光
   - 点击
   - 登录完成
   - 首问发起
   - 首答完成

建议开关：

- `deeptutor_entry_enabled`
- `deeptutor_entry_text`
- `deeptutor_entry_variant`

推荐挂载点：

- 最小落地优先挂在 `Getmajorzm` 返回中，因为 `freeCourse` 已经消费该接口的运营位字段
- `gettopzm` 可作为补充挂点，但只建议在其升级为对象返回后承载开关同步
- 不建议把宿主入口显隐直接挂到 Deeptutor FastAPI 的 `profile/settings` 或后台 admin settings 路由

推荐最小字段集：

- `deeptutor_entry_enabled`
- `deeptutor_entry_title`
- `deeptutor_entry_subtitle`
- `deeptutor_entry_tip`
- `deeptutor_entry_variant`

推荐返回示例：

```json
{
  "deeptutor_entry_enabled": 1,
  "deeptutor_entry_title": "鲁班AI智考",
  "deeptutor_entry_subtitle": "智能答疑入口",
  "deeptutor_entry_tip": "点击进入",
  "deeptutor_entry_variant": "default"
}
```

前端兼容说明：

- `deeptutor_entry_enabled` 已直接生效
- `deeptutor_entry_title / subtitle / tip / variant` 已接入前端动态展示
- `variant` 当前兼容：
  - `default -> blue`
  - `promo -> orange`
  - `compact -> dark`
  - `smart -> teal`
- 最小客户端漏斗埋点已接入：
  - `deeptutor_entry_expose`
  - `deeptutor_entry_click`
  - `deeptutor_login_success`
  - `deeptutor_first_question_start`
  - `deeptutor_first_answer_done`

## 13.2 登录能力

需求：

1. 未登录用户自动进入 Deeptutor 登录页
2. 支持现有登录方式保留：
   - 微信手机号/验证码
   - 用户名密码
   - 手动登录
3. 登录成功后回到 Deeptutor 工作区而不是回宿主首页
4. 登录失败有清晰错误提示

## 13.3 聊天能力

需求：

1. 保持 Deeptutor 现有聊天能力和 `/api/v1/ws` 协议不变
2. 支持恢复历史对话
3. 支持网络中断提示与恢复
4. 支持积分/计费相关状态展示
5. 支持后续从学情、练习回流聊天

## 13.4 Workspace 能力

需求：

1. 在 Deeptutor 内形成稳定工作区结构
2. 页面间跳转不出现“返回宿主后丢上下文”
3. 历史、学情、我的与聊天保持同一产品身份
4. 用户在 Deeptutor 内的来回切换要有“同一系统内工作”的感觉

## 13.5 运营开关

需求：

1. Deeptutor 入口可后台控制显示/隐藏
2. Deeptutor 工作区模块可做灰度开放
3. 某些子页面可配置关闭
4. 开关变更应有缓存与失败兜底

建议开关：

- `deeptutor_workspace_enabled`
- `deeptutor_history_enabled`
- `deeptutor_report_enabled`
- `deeptutor_profile_enabled`
- `deeptutor_assessment_enabled`

前端兼容说明：

- 宿主 `app.js` 已支持从 `payload / data / config / flags / feature_flags / settings` 提取上述字段
- `custom-tab-bar` 已按 flags 过滤工作区可见项
- `history / report / profile` 已做页级 gate，关闭后会 toast 并回退到 `chat`
- `assessment` 关闭时，`chat` 新手弹窗、`report` 摸底测试入口、`profile` 对应入口都会同步关闭

## 14. 技术改造清单

## 14.1 宿主层

需要改造：

1. `yousenwebview/app.js`
   - 注入 Deeptutor runtime 能力
2. `yousenwebview/app.json`
   - 注册 Deeptutor 分包
3. `yousenwebview/pages/freeCourse/*`
   - 接 Deeptutor 原生入口

## 14.2 Deeptutor 模块层

需要改造：

1. 页面路径前缀切换为分包路径
2. 路由从 `switchTab` 迁移到自定义适配层
3. `getApp().globalData` 调用收敛到运行时适配器
4. 对 Deeptutor 自定义 `tabBar` 做重构或降级

## 14.3 推荐新增模块

建议新增：

- `yousenwebview/deeptutor-runtime/`
  - `state.js`
  - `auth.js`
  - `env.js`
  - `route.js`
  - `flags.js`

目标：

- 让 Deeptutor 页面依赖“Deeptutor Runtime”
- 而不是直接依赖宿主 `App` 的原始结构

## 15. 工程量评估

## 15.1 方案一：MVP 融合

范围：

- 入口
- 登录
- 聊天

工程量评估：

- 前端小程序：5 到 8 人日
- 联调与问题修复：2 到 4 人日
- QA 与真机回归：2 到 3 人日

综合估算：

- **约 1.5 周**

## 15.2 方案二：完整工作区融合

范围：

- 入口
- 登录
- 聊天
- 历史
- 学情
- 我的
- 评测/练习/计费/协议
- Workspace Shell

工程量评估：

- 前端小程序：10 到 15 人日
- 路由与运行时重构：4 到 6 人日
- 联调与稳定性修复：3 到 5 人日
- QA、真机、灰度：3 到 5 人日

综合估算：

- **约 3 到 4 周**

## 15.3 为什么不是超大工程

因为：

1. 两边都是 JS 小程序
2. Deeptutor 体量不大
3. 后端主协议已存在
4. 主要挑战在前端运行时与导航整合

## 16. 风险与应对

## 16.1 路由风险

风险：

- `switchTab` 语义与宿主结构冲突

应对：

- 统一改造为 `deeptutorRoute` 适配层

## 16.2 全局状态污染风险

风险：

- 宿主与 Deeptutor 共用 `globalData` 易相互污染

应对：

- Deeptutor 全局状态命名空间化

## 16.3 登录态混乱风险

风险：

- 宿主登录和 Deeptutor 登录边界不清

应对：

- 第一阶段先让 Deeptutor 自管登录态
- 后续再评估单点登录

## 16.4 体验割裂风险

风险：

- 视觉和导航看起来像两套拼接产品

应对：

- 通过 Workspace Shell、统一品牌层和入口语义解决

## 16.5 合规风险

风险：

- 教育内容可能受类目和主体要求影响

应对：

- 发布开关只用于灰度和场景控制
- 正式上线前完成类目、内容、运营策略复核

## 17. 验收标准

## 17.1 Phase 1 验收

1. 用户可从 `freeCourse` 浮动入口进入 Deeptutor 原生页面
2. 未登录用户能稳定进入登录页
3. 已登录用户能稳定进入聊天页
4. 聊天页可正常发问、收流式回复、处理中断与失败
5. 入口点击到聊天可用链路成功率达到 `> 95%`
6. 不出现空白页、无响应、路径不存在等致命问题

## 17.2 Phase 2 验收

1. Deeptutor Workspace 内可稳定访问：
   - 对话
   - 历史
   - 学情
   - 我的
2. 页面切换成功率达到 `> 98%`
3. 关键用户路径可闭环：
   - 入口 -> 登录 -> 聊天
   - 聊天 -> 历史 -> 恢复对话
   - 聊天 -> 学情 -> 推荐动作
   - 我的 -> 会员/协议/退出

## 17.3 世界级体验验收

达到“世界顶尖水准”的定义不是一句口号，而是满足以下标准：

1. 入口理解成本低
   - 用户不需要学习“这是什么”
2. 进入速度快
   - 中端机型点击入口到可交互页面首屏目标 `<= 1.5s`
3. 首问反馈快
   - 首 token 体验目标 `p50 <= 3s`
4. 零死路
   - 任意 Deeptutor 页面都能回到明确的上一层或工作区首页
5. 同一产品感
   - 不是“佑森里塞了一个外来模块”，而是“佑森里有一个成熟 AI 工作区”

## 18. 里程碑建议

### M1：方案冻结

- 完成 PRD
- 完成技术拆分
- 完成页面与依赖清单

### M2：MVP 可跑通

- 入口 -> 登录 -> 聊天链路通
- 真机验证完成

### M3：Workspace 完整版

- 历史 / 学情 / 我的接入
- 路由体系稳定

### M4：灰度与正式上线

- 埋点上线
- 开关上线
- 运营与合规复核完成

## 19. 最终决策

本项目的推荐决策是：

1. **短期不再纠结“同 AppID 能不能像两个小程序一样互跳”**
2. **直接采用“宿主主包 + Deeptutor 原生模块分阶段接入”方案**
3. **一期以 `login + chat` 为上线目标**
4. **二期建设完整 Deeptutor Workspace**
5. **长期若要审核、产品、商业化完全独立，再评估第二个正式 `appid`**

一句话总结：

**能融，正确方式不是拼接，而是把 Deeptutor 作为佑森中的高价值 AI 工作区来建设。**
