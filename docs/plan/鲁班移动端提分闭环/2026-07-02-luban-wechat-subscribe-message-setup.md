# 微信订阅消息链路建设（双轮 v3.2 §9-D12 / 阶段 1 P0-④）

> Status: **代码侧已建成待接线；后台申请待 owner 操作（PENDING_OWNER）**
> Date: 2026-07-02
> 代码侧: `deeptutor/services/wechat_subscribe/service.py`（服务端发送+降级契约）·
> `yousenwebview/packageDeeptutor/utils/subscribe-message.js`（交接时刻授权 helper）·
> 域测试 `tests/services/wechat_subscribe/`（7 passed）

## 一、owner 后台操作清单（逐步，约 10 分钟）

前提：小程序已过审上线且类目含教育类（当前已有登录/支付在线，应满足）。

1. 登录 [微信公众平台](https://mp.weixin.qq.com)（小程序账号，非公众号）。
2. 左栏 **功能 → 订阅消息**。若首次使用，页面会要求先开通——点开通并同意协议。
3. 切到 **公共模板库** 标签，搜索关键词按优先级试：**「学习提醒」→「复习提醒」→「上课提醒」→「作业提醒」**。
4. 选一个字段贴合的模板（理想字段组合：`课程/内容名称(thing)` + `时间(time/date)` + `温馨提示(thing)`）。选中 → **选用**，按需勾选字段顺序 → 提交。
   - 公共库选用**即时生效无需审核**；若公共库无合适模板走"申请新模板"则有 1-3 个工作日审核（尽量避免）。
5. 选用成功后在 **我的模板** 里拿到**模板 ID**（形如 `AbCdEf...`，一串 Base64 样字符）。
6. 把模板 ID 发我（或自行填入两处，值必须相同）：
   - 服务端：Aliyun `.env` 增加 `WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST=<模板ID>`（走既有 release runbook 同步，注意 sync --delete footgun）；
   - 客户端：`yousenwebview/packageDeeptutor/utils/subscribe-message.js` 的 `TEMPLATE_IDS.nextDayRetest`。
7. 同时记下模板的**字段键名**（如 thing1/time2/thing3）发我——服务端发送的 `data` 形状要按它拼。

**推送文案基调（发我模板字段后我来拟，先锁铁律）**：帮你变强、不审视——「你昨天拿下的考点，今天换了身新皮等你——回来稳住它」方向；禁「看穿/识破/检验你」类措辞。

## 二、代码侧已建成的四件（§9-D12 全覆盖）

| §9-D12 要求 | 落点 | 契约 |
|---|---|---|
| tmplIds 配置 | 服务端 env `WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST` + 客户端 `TEMPLATE_IDS` | 未配置=链路未建成的合法态，一律红点降级，不报错 |
| 授权弹窗时机 | `requestNextDayRetestAuthorization()` 只供交接时刻调用 | 绝不在冷启动/onShow 弹（帮 helper 写死在注释与调用契约里） |
| 服务端发送 | `send_subscribe_message()`，access_token 复用 member_console stable_token 缓存（provider 注入，不建第二 token 权威） | 唯一成功态 `sent` |
| 拒绝降级 | 双端统一：未配置/用户拒绝(43101)/上游失败/token 失败 → 结构化 `red_dot` 结果 | **永不 raise 到主流程**，消费侧渲染 App 内红点+英雄位文案 |

## 三、刻意不做（防 unconsumed island / scope 蔓延）

- **不开 API endpoint、不建授权状态表、不写调度 job**——这三件随交接时刻 UI（spike 工程）一起接线：交接屏调用授权 helper → 上报授权结果 → 次日到期时服务端取 openid（member 已有 wechat identity）调 `send_subscribe_message`。现在建=无消费者的孤岛。
- 不做多模板管理后台：`TEMPLATE_ENV_KEYS` 一行一个语义键即登记面，够用。

## 四、外部不确定性（如实登记）

- 公共库模板即选即用；若被迫走自建模板申请，审核 1-3 个工作日且可能被拒——审核期内「明天见」钩子按 D12 以 App 内红点先行，链路建成不阻塞 spike 启动。
- 订阅消息为**一次性授权**：每发一条耗一次授权，交接时刻每次练完都可再请求（微信允许重复请求同模板），频次策略随 spike 数据调。
