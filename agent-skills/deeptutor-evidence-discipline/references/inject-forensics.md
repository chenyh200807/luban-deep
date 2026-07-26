# 注入片段 · 取证类

**用于**:查生产状态、查数据、查账、查日志、「到底发生了什么」。

**主要封死**:S2 旁证替代主证(本类是 S2 的重灾区)。

---

## 可粘贴片段

```text
本任务是取证。取证的产物是事实,不是解释。

【权威链纪律】
先声明本次取证的 canonical 源,再取证。取到的每个数字都要标出它来自哪一层:
  账本层(authority)  — 生产 DB / Supabase REST / SQLite mode=ro / 容器内直查
  观测层(surface)    — metrics / Prometheus / Grafana / BI 看板 / 日志
  缓存层             — 任何 snapshot、导出文件、历史报告

观测层回答"系统怎么显示",账本层回答"事实是什么"。**两者不可互相替代。**
结论若依赖账本层事实,而你只拿到观测层,结论写 BLOCKED。

【主证不可达时】
- 凭据未展开(如 psql 收到字面 ${DB_URL})、连接被拒、SSH 断 →
  立即写 BLOCKED,保存 preflight 证据,等真实只读连接恢复后原样重跑。
- 禁止用 metrics / 缓存 / REST 登录 / 样例数据补位。
- 禁止用早期 snapshot 写最终判断;live 计数变化时必须刷新后再交付。

【只读纪律】
- 全程 SELECT-only / mode=ro。任何写操作需要单独授权,不在本任务内。
- 先做 CLI safety probe:确认 --help / --dry-run 不会触发实际扫描或写盘。
- 历史快照与无日期的 current 产物分开存,不要互相覆盖。

【口径纪律】
- 每个比率显式写出分子分母来源。
- 零基数不给百分比:写"新增";正数变 0 写"转零"并解释原因。
- 不同单位的量不相加(不同产品/不同池/不同表)。总盘只用可加指标。
- 身份合并、分页、历史膨胀都会污染分母,先核 identity mapping 再算比率。

【交付形状】
  facts:      逐条事实 + 来源层 + 取数命令
  blocked:    没取到的,以及卡在什么地方
  inference:  你的推断,与 facts 严格分开
  next:       要坐实这个推断,下一步该取什么证据

【tripwire — 命中即停并报告】
- 你正准备用一个"恰好能连上"的面替代取不到的主证
- 你发现同一事实在两个源里数字不一致(报告不一致本身,不要择一)
- 你需要写入或修改才能取到证据
```

---

## 这份片段封死了什么(实录)

| 逃逸路径 | 实录原文 |
|---|---|
| 凭据失败仍出结论 | 「`psql` 收到字面 `${DB_URL}` 后仍用 metrics、缓存、REST 登录或样例补位。原因:把非权威观测面当账本。修复:结论写 BLOCKED」 |
| 观测面当 authority | 「本地 .env 有部分观测凭据,就误以为 BI/member 行为 authority 足够。原因:把 observability surface 当 member/BI authority」 |
| 陈旧快照当终态 | 「用早期 BI snapshot 写最终推广判断。修复:当 live BI 计数变化,刷新数据和报告再交付」 |
| 比率不核分母 | 「余额百分比接近 100% 就判断未扣费。原因:历史 wallet inflation 或分页分母错误。修复:先审计账本历史、plan entitlement、identity mapping 和 canonical percentage」 |
| 不同单位相加 | 「把瓣膜、补片、导管、血管等不同单位加成『全产品总数量』。修复:总盘只用金额类指标」 |
| 零基数给百分比 | 「由销量增长推导收入、毛利或盈利,或对零基数给百分比。修复:零基数写『新增』,正数变 0 写『转零』」 |
| help 触发写盘 | 「`--help` 触发实际扫描写盘,或日期快照被 current 产物覆盖。修复:先做 CLI/help safety probe」 |
| 界面异常当产物失效 | 「报告页在内置浏览器打开异常,就误判研究产物不可用。修复:本地起 http.server,再校验 HTML sections」 |

**关联硬约束**:阿里云 SSH 只读观察面白名单见
[deeptutor-release-launch-gate](../../deeptutor-release-launch-gate/SKILL.md);
eval/QA 账号身份四字段见
[deeptutor-test-verification-gate](../../deeptutor-test-verification-gate/SKILL.md)。
