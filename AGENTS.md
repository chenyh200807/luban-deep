# DeepTutor — Agent Working Agreement

## What This File Is

本文件 = **硬约束 + 唯一启动门 + 原则(一遍)+ 路由指针**。方法论正文沉在
[agent-skills/](./agent-skills/)(fat skills),架构与环境事实在
[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)。本文件只保留"每次任务都必须成立"的内容;
其他文档与本文件重复处,以本文件与被指向的 skill 为准。

> 遗留锚点:代码注释与脚本中引用的 `AGENTS §3.7` = 下文 **Aliyun SSH Write Boundary**;
> `AGENTS §5.7` = 下文 **Single Authority Hard Gate**。2026-07-12 重构前的完整历史版本见 git 历史。

## Hard Invariants — 可机械判定的铁律

- **唯一流式入口 `/api/v1/ws`**;禁止新增专用聊天 WebSocket 路由(如 `/api/v1/mobile/tutorbot/ws/...`)。
- **Aliyun SSH Write Boundary(原 §3.7)**:阿里云 SSH 上唯一可写根是 `/root/deeptutor`;其他路径(含 `/root/luban`、`/etc`、nginx、系统服务)一律只读观察面。越界需求必须停下向用户说明。细则与只读命令白名单:[deeptutor-release-launch-gate](./agent-skills/deeptutor-release-launch-gate/SKILL.md)。(Claude Code 本机另有 PreToolUse hook 拦明显违规;Codex 及其他 agent 无此 hook,同样受本条约束——hook 只是止血带,本条散文才是权威。)
- **Eval Runner Identity**:所有会创建/登录/绑定手机号/产生会员活跃的 eval/smoke/QA,必须用 `qa_eval_`/`eval_`/`qa_` 前缀账号,写 `account_kind="eval_runner"`、`actor_type="machine"`、`created_by="eval_runner"`、`is_internal_test=true` 四字段,复用 `external_auth.ensure_external_auth_user()` 路径;跑前先导出 `DEEPTUTOR_EVAL_RUNNER_AGENT` 与 `DEEPTUTOR_EVAL_RUN_ID`(命令见 skill);测试账号不得计入会员/活跃指标。细则:[deeptutor-test-verification-gate](./agent-skills/deeptutor-test-verification-gate/SKILL.md)。
- **灰度旗标毕业纪律(2026-07-30 指挥官裁决,owner 授权)**:每个灰度/shadow/rollout 类
  feature flag 登记进 `contracts/env_registry.yaml` 时必须带 `graduation` 字段(YYYY-MM-DD,
  建议 ≤30 天);到期必须 promote(转 killswitch 或删 flag 直连)或 delete,禁止永久影子。
  依据:KnowQL/PGO 全套高级件在 default-off flag 后沉睡六周无人问(`killed_by_switch`),
  影子评测 MAE 0.013 的引擎从未服务过一个真实学生——能力活在 flag 里,死亡不可见。
- **降级路径必须发声(同批裁决)**:任何降级/兜底/fail-open 分支必须写一个可导出的
  authority marker(如 `score_authority="v1_unavailable:<status>:<reason>"` 样板)并进导出
  白名单;静默 `return {}`/`return None`/warning-then-degrade 一律违规。依据:open-world
  判分死链四周不可见(V1 失败静默返 None 不落 score_authority),tier1 bank 六条
  fail-open 路径只 warning。新代码违反即 review blocker;存量逐步清偿。
- **contract-guard**:改 `deeptutor/contracts/index.yaml` 登记的 protected 文件必须同步登记 `test_files`;合并/push 前 `python scripts/check_contract_guard.py <files>` 必须 passed。
- **双拷贝同步**:`contracts/index.yaml` 与 `deeptutor/contracts/index.yaml` 必须同步修改(后者是 packaged runtime copy)。
- **计划纪律**:计划/PRD/runbook/gate checklist 统一放 `docs/plan/`,新增或修改后必须同步更新 [docs/plan/INDEX.md](./docs/plan/INDEX.md);新计划优先挂既有主线,不造平行规划;禁止 `doc/plan/` 路径。
- **git 纪律**:并行 agent 场景禁 `git add -A`/`git add .`(互扫工作,已发生两次;Claude Code 本机有 hook 拦,其他 agent 无 hook 同样必须遵守),脏分支用 `git commit --only -- <文件>`;诊断/合并命令禁夹带 `git stash`;只有用户明确要求时才 commit;默认不因新任务开分支;多任务并行必须独立 worktree。细则:[deeptutor-git-workflow-gate](./agent-skills/deeptutor-git-workflow-gate/SKILL.md)。
- **skill 一致性**:新增/删除/改名 `agent-skills/*/SKILL.md` 后必须跑 `python agent-skills/scripts/validate_agent_skills.py`(Claude Code 本机有 PostToolUse hook 自动跑,其他 agent 需手动执行)。
- **Web/BI 内存护栏**:任何 Web/BI/前端/浏览器/截图/Playwright/微信开发者工具任务,先过 [deeptutor-web-bi-frontend-gate](./agent-skills/deeptutor-web-bi-frontend-gate/SKILL.md) 的内存 preflight;**禁止任何 AI agent 托管长驻 `next dev`/`next-server`/浏览器进程**(2026-06-06 事故:201.6GB/3927 node 进程)。普通后端/文档/只读任务豁免。
- **测试不可跳过**:改代码必须跑与改动直接相关的测试;缺运行环境(如 `node`/`npm`/`deno`)时**先自行安装补齐再继续**,不得停下询问或以环境缺失为由跳过;前端/小程序改动还必须过微信开发者工具回归。

## Contract Discipline

凡涉及 turn/session/stream/replay/resume、聊天入口、TutorBot 接入、trace/observability 的改动,
先读 [CONTRACT.md](./CONTRACT.md) 与 [contracts/index.yaml](./contracts/index.yaml)。
只有对外稳定边界才允许升级为 contract/schema,普通内部实现不滥加。

## Concept Discipline

同一业务事实只能有一个一等概念:

- `TutorBot` 是唯一业务身份(完整、持久、可多实例、可技能扩展的 runtime);禁止并行第二套执行身份;轻量绑定/入口 hint/风格 profile 不得叫 TutorBot。
- `rag` 是唯一知识召回工具;知识库只是工具绑定,不包"grounded mode"概念。
- `bot_runtime_defaults` 只是 `bot_id → 默认工具/知识库` 绑定;`teaching_mode` 只表示表达风格(fast/deep/smart);`product_surface`/`source`/`entry_role` 只表达入口表面信息——都不得升级成业务身份、知识链或执行引擎语义。
- alias 允许存在但必须在入口层立即归一化,不得参与执行决策。发现两个名字表达同一语义,优先删重复概念。
- 新概念进代码前三问:是否旧概念换名?表达的是身份/工具/绑定/风格中的哪个?能否直接复用现有控制面?

## Weight Gate — 先定档,再决定过不过门

**这一节优先于下面两道门。** 简单的事情必须简单做——重型协议用在轻任务上,
代价不只是慢,是**稀释了它在真正重要时候的严肃性**。

分档判据只有一个,**不看任务类型(主观),看错了的代价(客观)**:

| 档 | 判据:如果这次做错了…… | 该做什么 |
|---|---|---|
| **轻** | 重跑一次 / 改回来就好,用户看不到 | **直接做**。不写 Start Frame,不过 Stop Gate。收尾一句话说明改了什么 |
| **中** | 需要回滚,或用户会看到错误状态 | Start Frame + Stop Gate。**不派专家,不做对抗审查** |
| **重** | 资损 / 数据不可逆 / 信任损失 / 生产事故 | 全套:算子 + 专家并行 + 对抗证伪 + E3 以上验证 |

**轻档的例子**(直接做):改文案、加日志、补注释、只读查询、单文件小改、
调整格式、加一个测试、更新文档链接。

**重档的例子**(全套):动 authority / 并发语义 / 持久化格式 / 钱相关 / 发布 / 删数据。

**判不准就问一句「这次做错了会怎样」**——答不出「会怎样」的,按轻档做。
**宁可轻档做错一次重跑,不要每件事都上全套。**

## Start Gate — 唯一启动门

(取代旧 §0.0 Karpathy Gate、§5.6 六件事、§5.7 五件事、§5.8 六件事的全部重复门槛,只此一道。)
**先过 Weight Gate 定档;轻档任务整节豁免。**

- **非平凡任务**(会改代码/状态/路由/测试/发布/文档治理):动手前写
  [deeptutor-engineering-lifecycle-gate](./agent-skills/deeptutor-engineering-lifecycle-gate/SKILL.md)
  的 Start Frame(assumptions / simplest path / change boundary / verification target 等)。
- **状态/路由/上下文承接/follow-up/authority 类设计或修复**:追加
  [deeptutor-authority-debugging](./agent-skills/deeptutor-authority-debugging/SKILL.md)
  的 root-cause frame(one business fact / one authority / competing authorities / canonical path / delete-or-demote)。
- **blind spots(必填,不可留空)**:动手前写两栏——**我的盲区**(本次查不到/判不准/
  没有雷达的层)与**你的盲区**(owner 这次请求隐含了什么假设、可能不成立)。
  写「本次未发现」合法;泛泛提醒(注意测试/注意性能/注意兼容)**不合法**,按未填处理。
- 写不出即不许编码。简单拼写、一行注释、只读查询豁免。
- 修复完成后必须额外说明三件事:真正坏掉的一等业务事实;哪些地方曾争夺 authority;
  为何修完系统更接近单一 authority 而非多一层补丁。

## Stop Gate — 唯一收工门

(与 Start Gate 对称。Start Gate 管「能不能开始」,本门管「配不配说完成」。
依据:`~/.codex/memories` 351 条实录失败聚类,绝大多数不发生在动手前,发生在收工时。)

- **claim level 标给 owner 看,不是自己心里过。** 每个「完成/修好/已验证」级声明旁边直接标
  E0-E5。**标注是 agent 的义务,不是 owner 的追问。**
- **架构类改动主动上异源,不等 owner 问**(判据:影响 ≥3 文件,或动到并发/持久化/权限)。
  owner 判断得出「太复杂」,判断不出「架构不成立」——异源是这个缺口的唯一补丁,实证见 skill。
- 任何「完成/修好/已验证/已上线/查过了/没问题/ready」级声明,发出前过
  [deeptutor-evidence-discipline](./agent-skills/deeptutor-evidence-discipline/SKILL.md)
  的证据阶梯:写下 claim level(E0-E5)、evidence level、差的几级由谁承担。
  **结论强度必须 ≤ 证据强度**;跨级即为 351 条里最高频的那个病。
- 全称结论(整体/都/全部/基本没问题)必须显式写出**分母**与**未覆盖面**;写不出即降级
  为「就已查项而言」。
- 后端改 Python 未 rebuild、前端未 DevTools 上传 = **未部署**,claim 封顶 E1。
- **交付末尾附「你没问但我必须说」**:①前提质疑 ②层盲区(本次改动落在哪个技术层、
  该层还有哪些高频反模式本次没扫) ③坏消息(未做的/被阻塞的/我不确定的)。
  同样:允许「本次未发现」,禁止泛泛提醒充数。
- 未做的、被阻塞的、不确定的必须单列。省略坏消息按虚假声明处理。

## Principles(一遍,后文与其他文档不再复述)

- **Thin wrappers, fat skills**(最高优先级):入口/router/adapter/wrapper 只做归一化、鉴权、转发、错误语义、观测;业务理解、教学/安全/评分策略、状态真相必须沉入明确命名的 skill/kernel/service authority。wrapper 里不断增长的 regex/fallback/特判/prompt 拼接默认是架构异味,优先下沉或删除。
  薄还必须**薄在执行维度**:`async` 入口内不得内联同步 IO(含经由 service/store 的间接同步往返)。
  **逻辑薄 ≠ 非阻塞,两者正交**——一个「只组装转发」的合规 handler 照样可以同步打 6 次 DB 把事件循环占死。
  判据:`python scripts/scan_asyncio_blocking.py`;修法与坑见 [blindspot-asyncio](./agent-skills/deeptutor-evidence-discipline/references/blindspot-asyncio.md)。
- **Single Authority Hard Gate(原 §5.7)**:同一业务事实只能有一个 canonical truth source,必须答得出"谁唯一写、唯一存、唯一恢复、唯一读"。默认修法是**先收权再补逻辑**:优先删 mirror state、重复决策点、旁路 reader、transport 层二次改写、参与决策的 alias。新增字段/state/router/classifier/interpreter/wrapper/fallback 一律有罪推定,加之前必须证明:①不造第二套 authority;②不把语义问题降级成模式匹配;③不会成为未来 patch anchor;④旧层确实不能删、主链路确实不能直接承担。
- **First principles**:先回到业务事实再定实现;"目前代码就这么写"不是理由;现有设计本身是病因时先指出根因。
- **Think before coding**:不默默假设需求;多种解释不静默选一;先给更简单的方案;带着疑问不编码。
- **Simplicity first / less is more**:只写解决当前问题的最少代码;不为"以后可能用"预留抽象/配置项/扩展点/schema/路由;less is more 的本义是更少概念、更单一 authority、更少决策点、更少状态、更短链路、更直接验证。
- **Surgical changes**:只改与需求直接相关的行;不顺手重构/改名/格式化/清历史问题;diff 里无法追溯到需求的行默认删掉。
- **Goal-driven execution**:先把任务改写成可验证目标;修 bug 先写复现测试再定位根因;完成后如实汇报改了什么/如何验证/剩余风险,无法执行的测试要写具体阻塞。
- **Fix root causes**:禁止补丁漩涡;问题反复出现说明抽象/边界/authority 有缺陷,修源头;临时缓解必须显式标记并给根治路径。
- **LLM vs deterministic**:依赖上下文语义的问题,优先用已有 authoritative context 的主链路理解;格式稳定、边界清晰的才用确定性规则。regex/fallback 只许做高置信快路径或低成本保底;开始承担主要理解职责即为越权,必须回主链路收权。

## Main Merge Workflow(原 §3.5 精要)

用户要求合并 main 时:在干净 worktree 完成 merge/push/部署验证;当前工作区有脏改动禁止强切 main,先说明冲突文件让用户决定;最终汇报 `origin/main` commit、部署状态、本地是否已切回 main 及原因。细则:[deeptutor-git-workflow-gate](./agent-skills/deeptutor-git-workflow-gate/SKILL.md) + [deeptutor-release-launch-gate](./agent-skills/deeptutor-release-launch-gate/SKILL.md)。

## Routing — 指针不复制

默认调用合同:除只读一行查询、简单翻译、纯解释外,非平凡任务先读
[deeptutor-engineering-lifecycle-gate](./agent-skills/deeptutor-engineering-lifecycle-gate/SKILL.md),
再按任务面选窄 skill。触发目标是"有工程风险的任务近乎必触发",不是所有消息 100%。
**skill 描述的唯一权威是各 SKILL.md frontmatter,机器清单是 [agent-skills/catalog.yaml](./agent-skills/catalog.yaml);本文件不内联描述。**

高频任务面 → skill:

- CI/Actions 失败:[deeptutor-ci-runtime-fix-gate](./agent-skills/deeptutor-ci-runtime-fix-gate/SKILL.md) + [docs/runbook/ci-runtime-smoke-guardrails.md](./docs/runbook/ci-runtime-smoke-guardrails.md)
- 微信真机/DevTools QA(证据分级、`yousenwebview` 唯一 project root):[wechat-tutorbot-real-entry-qa](./agent-skills/wechat-tutorbot-real-entry-qa/SKILL.md)
- 鲁班数据资产/教材/真题/考频:[luban-okf-context](./agent-skills/luban-okf-context/SKILL.md)
- gstack 任何命令:[external-tool-absorption-boundary](./agent-skills/external-tool-absorption-boundary/SKILL.md) 的 references/gstack.md

全部 repo-local skills(零描述,防镜像漂移):

- [anti-overfit-repair-review](./agent-skills/anti-overfit-repair-review/SKILL.md)
- [compiled-knowledge-shadow-eval](./agent-skills/compiled-knowledge-shadow-eval/SKILL.md)
- [deeptutor-api-contract-design](./agent-skills/deeptutor-api-contract-design/SKILL.md)
- [deeptutor-code-simplification](./agent-skills/deeptutor-code-simplification/SKILL.md)
- [deeptutor-docs-adr-gate](./agent-skills/deeptutor-docs-adr-gate/SKILL.md)
- [deeptutor-evidence-discipline](./agent-skills/deeptutor-evidence-discipline/SKILL.md)
- [deeptutor-incremental-implementation](./agent-skills/deeptutor-incremental-implementation/SKILL.md)
- [deeptutor-observability-gate](./agent-skills/deeptutor-observability-gate/SKILL.md)
- [deeptutor-resource-registry-gate](./agent-skills/deeptutor-resource-registry-gate/SKILL.md)
- [deeptutor-review-quality-gate](./agent-skills/deeptutor-review-quality-gate/SKILL.md)
- [deeptutor-schema-authority-gate](./agent-skills/deeptutor-schema-authority-gate/SKILL.md)
- [deeptutor-security-hardening-gate](./agent-skills/deeptutor-security-hardening-gate/SKILL.md)
- [deeptutor-source-grounded-change](./agent-skills/deeptutor-source-grounded-change/SKILL.md)
- [deeptutor-spec-plan-gate](./agent-skills/deeptutor-spec-plan-gate/SKILL.md)
- [deeptutor-storm-source-inspection](./agent-skills/deeptutor-storm-source-inspection/SKILL.md)
- [deeptutor-test-verification-gate](./agent-skills/deeptutor-test-verification-gate/SKILL.md)
- [deeptutor-web-bi-frontend-gate](./agent-skills/deeptutor-web-bi-frontend-gate/SKILL.md)
- [luban-case-answer-layer](./agent-skills/luban-case-answer-layer/SKILL.md)
- [luban-diagram-microlesson](./agent-skills/luban-diagram-microlesson/SKILL.md)
- [luban-learning-pack-factory](./agent-skills/luban-learning-pack-factory/SKILL.md)
- [luban-rich-leaf-compiler](./agent-skills/luban-rich-leaf-compiler/SKILL.md)
- [tutorbot-student-army-eval-loop](./agent-skills/tutorbot-student-army-eval-loop/SKILL.md)

这些是开发/QA 工作法 skill,不是 TutorBot runtime skills,不得移动到 `deeptutor/tutorbot/skills/`。

## Repo Facts(最小环境事实)

- 架构/CLI/Key Files:[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)(查代码结构优先 CodeGraph)。
- 依赖层:`requirements/{cli,server,tutorbot,math-animator,dev}.txt`。
- 全量 pytest 有隔离污染:失败文件先单独跑,单独 PASS = 污染而非真红。
