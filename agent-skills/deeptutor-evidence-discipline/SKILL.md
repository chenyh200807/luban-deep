---
name: deeptutor-evidence-discipline
description: Use this before claiming anything is done, fixed, verified, deployed, checked, healthy, or ready, and before signing off any audit, verdict, release, or forensics result. Use it whenever about to turn a tool exit code, a green CI run, a metrics or dashboard surface, a partial check, or a pile of collected evidence into a stronger claim than that surface can support. Use it when writing a subagent prompt, to pre-close the escape routes that surface would otherwise open.
---

# DeepTutor Evidence Discipline

本 skill 只治一个病。它不是 checklist 集合,是**证据面与结论强度之间的对齐规则**。

来源:`~/.codex/memories/MEMORY.md` 里 351 条实录失败的聚类结果。其中「第二权威 /
authority 分裂」一族(约 48 条)归
[deeptutor-authority-debugging](../deeptutor-authority-debugging/SKILL.md),
本 skill 不重复持有那个 authority。

## 一个母病

> **用不足以支撑该结论的证据面,产出了那个结论。**

注意它**不是**"撒谎",也不是"没检查"。绝大多数实录里,检查确实做了、命令确实跑了、
输出确实是绿的——**病在于那个绿色所覆盖的范围,小于被宣称的范围**。

所以本 skill 的唯一动作是:**在写下结论之前,先写下这个结论需要的证据级别,再问手上
的证据够不够到那一级。** 不够就降级结论,不是升级证据的解释。

## 证据阶梯

结论强度必须 ≤ 证据强度。跨级即为本病。

| 级 | 证据面 | 只能支撑的结论 |
|---|---|---|
| E0 | 命令退出码 0 / 脚本跑完 / 无报错 | 「该命令执行了」 |
| E1 | 单元测试绿 / CI 绿 / gate 绿 | 「被这些用例覆盖的形状没退化」 |
| E2 | metrics / 日志 / dashboard / snapshot | 「观测面此刻这么显示」 |
| E3 | 目标环境终态直查(容器内 SHA、DB `mode=ro` SELECT、持久化 messages) | 「目标环境当前是这个状态」 |
| E4 | 真实入口的真实行为(真机 / public endpoint / 用户可见路径) | 「用户会看到这个」 |
| E5 | 独立复核 + 可证伪 + 可重复 | 「这件事成立」 |

**"修好了 / 已上线 / 没问题 / ready"是 E4-E5 级结论。** 用 E0-E2 支撑它,就是本病。

## 四个形状

### S1 · 弱证据升级(最高频,约 80 条实录)

把 E0/E1 直接当 E4/E5 用。

**静态指纹**:结论里出现「完成 / 修好 / ready / healthy / GO / 已上线」,而证据栏里
只有退出码、测试数、gate 名。

实录:
- 「脚本成功即称发布完成」——没核跨层 lineage / health / 真实场景
- 「候选 survived 或 CI 绿就被写成 ready / human signoff」——把"未被当前证据推翻"
  误写成"已获授权"
- 「TRUSTED metrics 或 WS PASS 就写 release-ready」——未读 direct gate
- 「18/18 输出成功就称所有维护完成」——没核 INDEX 快照、命名迁移、链接同步、幂等重跑
- 「事实看似正确就签发」——把 factual correctness 和 provenance completeness 混为一门

**判据**:测试绿证明的是"这些用例没红",不是"这个能力对"。行为质量、真机可见性、
持久化终态,单元测试**结构上证不了**。

### S2 · 旁证替代主证(约 21 条实录)

主证不可达时,用一个恰好可达的面顶上,并且不标注这个替换。

**静态指纹**:主证获取失败(connection refused / 凭据缺失 / 字面 `${VAR}` 未展开)之后,
结论**仍然产出了**,而不是停在 BLOCKED。

实录:
- 「`psql` 收到字面 `${DB_URL}` 后仍用 metrics、缓存、REST 登录或样例补位」
- 「`127.0.0.1:8001/metrics` connection refused 后仍以 old/latest wrapper 或 benchmark
  做 current release truth」
- 「本地 `.env` 有部分观测凭据,就误以为 BI/member 行为 authority 足够」——把
  observability surface 当 member/BI authority
- 「余额百分比接近 100% 就判断未扣费」——没审账本历史 / plan entitlement / identity mapping

**判据**:**主证不可达 → 结论写 `BLOCKED`,不是换一个证据面继续。** 观测面回答的是
"系统怎么显示",账本回答的是"事实是什么",这两个问题不可互相替代。

### S3 · 局部冒充全量(约 14 条实录)

只覆盖了被点名的部分 / happy path / 单一分母,却给出整体结论。

**静态指纹**:结论是全称的(「整体 / 都 / 全部 / 基本没问题」),而执行段只出现了
用户点名的那几项。

实录:
- 「只核对用户点名的 fix,就给『基本没问题』」——没往 sibling path / 第六问题追
- 「只读前端审查只看 happy path 单题流,就把 retest 重构当通过」——没查重进、断网重试、
  答完再进的恢复语义
- 「把 40/41/60/501/2,112 混为一个『总池』」——没标出交付表面 / 资产池 / 理论池分母
- 「受控浏览器不能完整读取微信软文正文却写成已全量审计」

**判据**:全称结论必须显式声明**分母**和**未覆盖面**。写不出未覆盖面,说明没测绘过
边界,该结论降级为"就点名项而言"。

### S4 · 中途停止(约 24 条实录)

证据齐了,但没走完到可执行的那一步;或者反过来,给了结论没给依据和选项。

**静态指纹**:交付里有大量文件/命令/数字,但没有"所以现在该做什么、谁做、什么算通过"。

实录:
- 「回答只复述文件/工具输出,没有把它们翻译成『现在该怎么决策』」
- 「只做完证据收集,没有把用户要求的固定结构结论交付出来」
- 「战略/产品/架构问题只回一段短 close-out」——founder-level decision support 当成了
  普通执行汇报

**判据**:取证阶段和结论阶段要拆开,但**两个都要交付**。战略类问题按
结论 → 依据 → 选项 → 推荐 → 下一步 → 红线 收束。

## 四个动作时点

在这四个时刻**必须**跑一次上面的阶梯对照。其余时候不必。

### T1 · 声称「完成 / 修好 / 已修复」之前

写出三行,写不出就不许说完成:

```text
claim level:        我在声称第几级(E0-E5)
evidence level:     我手上最强的证据是第几级
gap:                差的那几级由什么承担;不承担就降级 claim
```

后端改 Python 未 rebuild、前端未 DevTools 上传 = **未部署**,claim 封顶 E1。

### T2 · 声称「查过了 / 没问题」之前

```text
分母:        我检查的是 N 项里的哪 M 项
未覆盖面:    明确列出没查的
全称资格:    M < N 时,结论只能写"就这 M 项而言"
```

### T3 · 交付结论之前

```text
证据 → 结论的那一跳,是否跨了阶梯?
结论落到动作了吗(谁 / 做什么 / 什么算通过)?
坏消息写了吗(未做的、被阻塞的、我不确定的)?
```

### T4 · 写 subagent prompt 时

把本 skill 的约束**前置注入**,而不是等它犯错再纠正。四类任务的可粘贴片段见
`references/`:

- 审计类 → [inject-audit.md](./references/inject-audit.md)
- 判断类 → [inject-verdict.md](./references/inject-verdict.md)
- 发布类 → [inject-release.md](./references/inject-release.md)
- 取证类 → [inject-forensics.md](./references/inject-forensics.md)

这四份是本 SKILL.md 的**投影,不是第二权威**。判据改动只改本文件,再同步投影。

### 层盲区表(供 Stop Gate「层盲区」一栏查表)

- asyncio / 并发 → [blindspot-asyncio.md](./references/blindspot-asyncio.md)(16 项,2026-07-26 异源+本地双路侦察)

写「层盲区」时**查表,不要现编**。表里没有的层,如实写「该层尚无指纹表」,并作为下一轮
盲区侦察的候选——这比编一句「注意并发安全」有用得多。

## Tripwires(执行中命中即停,不要继续)

禁令是静态的,覆盖不到没想过的岔路。这些是动态自检点:

```text
· 主证不可达,而我正准备换一个证据面继续  → 停,写 BLOCKED
· 我要新增字段 / router / fallback 才能让它工作  → 停,先过 authority-debugging
· 我需要在两个身份空间之间建映射才能完成  → 停,先只读验 join 可行性
· 我发现的"根因"需要改 3 个以上模块  → 停,根因可能判错了
· 我无法用一条命令复现被报告的现象  → 停,先复现再定位
· 结论里出现全称词,而我只查了被点名的项  → 停,补分母或降级结论
```

实录佐证:2026-07-21 采分点一役,在写第一行代码前派只读 GATE 验 join 可行性,结论
"接不了"——拦下了一次会把 A 题采分点安到 B 题上的内容漂移事故。**那次真正的交付是
两次翻车没有落地成代码。**

## 无法验证的技术结论

当结论依赖本 repo owner 无法独立验证的底层语义(asyncio 调度、锁与事务、GC 时机、
流式协议),不要求"讲懂原理",要求**可观察的证伪条件**:

```text
[结论]                            一句话
[如果这条错了,线上会表现为什么现象]  具体到可观察指标或用户可见行为
[最便宜的证伪实验]                  一条命令或一个指标
```

这把"撞过才知道"的遭遇驱动,换成一个提前布下的观察哨。

## 与其他 skill 的边界

- 「同一业务事实有两个 writer/reader」→ [deeptutor-authority-debugging](../deeptutor-authority-debugging/SKILL.md),不在本 skill。
- 「测试怎么写、怎么先写复现测试」→ [deeptutor-test-verification-gate](../deeptutor-test-verification-gate/SKILL.md)。
- 「发布五层核验的具体命令」→ [deeptutor-release-launch-gate](../deeptutor-release-launch-gate/SKILL.md)。

本 skill 只回答一个问题:**手上这份证据,配不配得上我准备写下的那句话。**
