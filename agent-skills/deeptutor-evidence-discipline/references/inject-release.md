# 注入片段 · 发布类

**用于**:部署、上线、发版、「已经修好了吗 / 生产是最新的吗」。

**主要封死**:S1 弱证据升级(本类是 S1 的重灾区,约 59 条实录)。

---

## 可粘贴片段

```text
本任务涉及发布声明。发布声明是 E4-E5 级结论,证据必须到那一级。

【嗅觉 — 发布前扫这几条】
- 部署脚本 exit 0 → 不等于容器在跑新代码。容器内 grep 对 SHA
- 改一个设置没检查隐式耦合 → 设置之间有耦合(实测 `journal_mode=WAL` 会把默认
  `synchronous` 从 FULL 降到 NORMAL)。改前改后各 dump 一次全部相关配置
- 用 `cp` 在分支/worktree 间搬文件 → 会带上别人未提交的改动。查源工作区 git status

【禁止的等价】
以下任何一项,都不构成"已上线 / 已修好 / release-ready":
  · 脚本退出码 0 / build 成功 / 部署命令跑完
  · CI 全绿 / 单元测试全绿 / gate 全绿
  · metrics 显示 TRUSTED / WS smoke PASS
  · 本地或 staging 验证通过
它们各自只能支撑"该步骤执行了",不能支撑"目标环境现在是这个状态"。

【必须的证据链】
1. 同 SHA 核验:宿主 .env 的 release SHA == 容器内实际代码 SHA,
   且用容器内 grep 直查符号,不看构建日志。
2. public health/ready 端点真实响应。
3. 可观测面确认新版本在跑(不是缓存/旧 wrapper/历史 benchmark)。
4. 真实入口的真实行为至少一轮(public endpoint 或真机)。

【未闭环项必须单列】
- 后端改 Python 未 rebuild = 未部署。
- 前端/小程序未经 DevTools upload/submit = 未发布。
- 缺 Playwright 证据、缺微信真机 true-entry 证据 = 保持 FAIL/hold,不得降格。
以上任一存在时,结论写「代码已合并,未部署」,不写「已修好」。

【交付形状】
  claim:        我在声称什么(逐句)
  evidence:     每句对应的证据与级别(E0-E5)
  not_closed:   未闭环的具体项 + 它们各自卡在谁那里
  rollback:     出问题怎么回滚

【tripwire — 命中即停并报告】
- 主证不可达(metrics refused / SSH 断 / 凭据缺失)→ 写 BLOCKED,
  不要换一个可达的面顶上
- 你发现远端 SHA 与预期不符 → 停,先查是不是并发构建撞了容器
- 你想加 except 兜底让流程跑通 → 停,那是掩盖而非修复
```

---

## 这份片段封死了什么(实录)

| 逃逸路径 | 实录原文 |
|---|---|
| 脚本成功 = 发布完成 | 「脚本成功即称发布完成。原因:没有核对跨层 lineage/health/真实场景」 |
| metrics PASS = ready | 「TRUSTED metrics 或 WS PASS 就写 release-ready。原因:未读取 direct gate,或把 scope-required Playwright/WeChat evidence 降格」 |
| 主证挂了换旁证 | 「`127.0.0.1:8001/metrics` connection refused 后仍以 old/latest wrapper 或 benchmark 做 current release truth。修复:停在 BLOCKED」 |
| 部分绿 = 整体健康 | 「两大 focused pytest 和 Web shadow 都通过,就把本轮写成 repo healthy。原因:忽略 `mobile.py` contract-sensitive drift 仍可单独把 daily health 打成 RED」 |
| 方向验证 = 已闭环 | 「把这轮方向性收口写成已完全闭环……修复:明确标注 directionally validated vs closed implementation」 |
| 批量成功 = 全部完成 | 「18/18 输出成功就称所有维护完成。修复:仍核 INDEX.md 当前快照、命名迁移、链接同步和幂等重跑」 |

**关联硬约束**:阿里云 SSH 唯一可写根 `/root/deeptutor`;发布流程细则见
[deeptutor-release-launch-gate](../../deeptutor-release-launch-gate/SKILL.md)。
本片段只管「什么证据配得上发布声明」,不复制那份 runbook。
