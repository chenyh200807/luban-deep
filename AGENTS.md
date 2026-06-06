# DeepTutor — Agent-Native Architecture

## Overview

DeepTutor is an **agent-native** intelligent learning companion built around
a two-layer plugin model (Tools + Capabilities) with three entry points:
CLI, WebSocket API, and Python SDK.

## Contract Discipline

凡是涉及 turn/session/stream/replay/resume、聊天入口、TutorBot 接入、trace/observability 的改动，必须先遵守：

- [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
- [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)

## Plan Directory Discipline

凡是要写 PRD、审查 PRD、规划模块改造、判断某条能力是否已经落地，或想理解某个模块未来方向，必须先看：

- [docs/plan/INDEX.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/INDEX.md)

执行规则：

- 先用 `docs/plan/INDEX.md` 确认该模块属于哪条计划主线，再读取具体 PRD / implementation plan / checklist。
- 新增或修改计划文件后，必须同步更新 `docs/plan/INDEX.md`，否则后续 agent 会失去计划地图。
- 不要再新增 `doc/plan/` 路径；计划、PRD、runbook、gate checklist 统一放在 `docs/plan/`。
- 如果新计划只是既有计划的补充，优先挂到既有主线下，不要制造第二套平行规划。

硬约束：

- 只能有一个流式入口：`/api/v1/ws`
- 控制面 contract 走“总纲 + 专项 contract + machine-readable index”
- 只有对外稳定边界才允许升级为 contract / schema，普通内部实现不要滥加
- 禁止新增 `/api/v1/mobile/tutorbot/ws/...` 之类的专用聊天 WebSocket 路由

### Concept Discipline

以下规则用于约束概念层，防止系统长出两套重复语义：

- 同一业务事实只能有一个一等概念，禁止用多个名字表达同一件事。
- `TutorBot` 是唯一业务身份；不要再并行创造第二套执行身份，如历史遗留的 `mini_tutor`。
- `TutorBot` 只指完整、持久、可多实例、可心跳、可技能扩展的 TutorBot runtime；不要再把轻量默认绑定、入口 hint 或风格 profile 也叫作 `TutorBot`。
- `rag` 是唯一知识召回工具；知识库如 `construction-exam` 只是工具绑定，不要再包一层重复的“grounded mode”概念。
- `bot_runtime_defaults` 只表示 `bot_id -> 默认工具/默认知识库` 的绑定契约；它不是 TutorBot 本体，也不能承担执行引擎语义。
- `teaching_mode` 只表示表达风格或交互节奏，如 `fast / deep / smart`；不得承担知识链、身份路由、工具启用等职责。
- `product_surface`、`source`、`entry_role` 这类字段只表达入口表面信息，不得升级成新的业务身份。
- 允许存在兼容旧字段的 alias，但必须在入口层立即归一化，不能让 alias 继续参与执行决策。
- 如果发现两个模块、两个字段、两个模式名在表达同一语义，优先删除重复概念，而不是继续补同步逻辑。
- 任何新设计在进入代码前，先回答三个问题：
  1. 这是不是一个已经存在的概念换了个名字？
  2. 它表达的是身份、工具、知识库绑定、还是表现风格？
  3. 不新增这个概念，能否直接复用现有控制面？

## Execution Discipline

以下规则用于约束 agent 的执行方式；它们补充项目规则，但不替代 contract 约束。

本节已吸收 `multica-ai/andrej-karpathy-skills` 的四条核心行为准则：`Think Before Coding`、`Simplicity First`、`Surgical Changes`、`Goal-Driven Execution`。不要把外部通用 `CLAUDE.md` 机械粘贴进来；在 DeepTutor 中必须先落到本仓库的 contract、single authority、thin wrappers / fat skills 和真实链路验证上。

### 0.0 Karpathy Gate — Start Every Non-Trivial Task Here

这不是额外流程，而是防止 agent 在复杂任务里“替用户做错误假设、过度工程、顺手改无关代码、缺少验收标准”的启动门槛。简单拼写、一行注释、只读查询可以轻量处理；凡是涉及代码、架构、状态、路由、测试、发布、文档治理或产品行为，都必须先过这道门。

开始前先写清楚四件事：

1. `assumptions`：我准备采用的需求解释是什么，哪些地方还不确定；如果有多种解释，不能静默选择。
2. `simplest path`：最短、最少概念、最少状态的实现路径是什么；如果当前代码诱导出更重方案，要先说明为什么不用。
3. `change boundary`：本次允许触碰哪些文件、模块、行为面；哪些相邻问题只记录不顺手修。
4. `verification target`：完成标准是什么，准备用哪条测试、日志、真实页面、DevTools、Langfuse 或线上链路证明。

执行中持续用两个问题自检：

- 如果一个实现从 50 行膨胀到 200 行，先停下来问是不是把一次性逻辑做成了框架。
- 如果 diff 里出现无法直接追溯到用户请求的行，默认删掉或拆出去，不要把“顺手优化”混进本次任务。

### 0. Thin Wrappers, Fat Skills

这是本项目当前最高优先级原则，排在 First Principles 和 Less Is More 之前。

- 默认架构形态必须是 `thin wrappers and fat skills`：入口、router、adapter、compat wrapper、API wrapper 只负责归一化、鉴权、转发、错误语义和观测，不承载业务理解、策略判断或长期状态真相。
- 真正的业务能力、教学策略、安全策略、评分协议、上下文解释、输出约束，必须沉到明确命名的 Skill / Kernel / Service authority 中，形成可测试、可复用、可审查的胖能力内核。
- wrapper 不能成为第二套 policy engine。任何 wrapper 中出现不断增长的 regex、fallback、特殊 case、prompt 拼接、状态推断或路由判断，都默认是架构异味，必须优先下沉到对应 fat skill 或删除重复逻辑。
- fat skill 不是“堆大文件”。它必须代表单一业务事实的唯一 authority：谁写、谁读、谁校验、谁输出、谁被测试，都要清楚。
- 新增 wrapper / classifier / interpreter / fallback 前，必须先证明四件事：
  1. 现有 fat skill / authority 不能承担这个职责
  2. 这个 wrapper 不会制造第二套业务真相
  3. 它只做边界适配，不做语义理解和策略决策
  4. 它有明确删除条件或长期稳定边界
- 修 bug 时，默认先问：这个补丁是不是应该进 fat skill，而不是进 wrapper。若答案不清楚，不允许开始编码。
- 测试也必须跟着这个原则走：wrapper 测委托关系和边界行为；fat skill 测完整策略矩阵；端到端测试证明 wrapper 没有绕开 fat skill。

### 0.5 First Principles

- 先回到问题本质，再决定实现方式。不要直接沿用现有代码路径、历史补丁或表面症状作为默认前提。
- 先分清楚：用户真正要解决的是什么问题，系统当前为什么会这样，约束来自业务、contract、兼容性，还是只是历史实现。
- 如果现有设计本身就是问题来源，应先指出根因，再决定是局部修复、结构调整，还是 contract 澄清。
- 不要把“目前代码就是这么写的”当成充分理由；要说明这样改在逻辑上为什么成立。

### 1. Think Before Coding

- 不要默默假设需求。开始实现前，先明确本次改动的假设、影响范围、涉及层次（API / Orchestrator / Capability / Tool / TutorBot / storage / trace）。
- 如果需求存在多种解释，不要静默选择其一；先列出你准备采用的解释和理由。
- 如果改动可能触碰 `turn/session/stream/replay/resume`、聊天入口、TutorBot、trace/observability，必须先检查 `CONTRACT.md` 和 `contracts/index.yaml`，再实施修改。
- 如果存在更简单的实现路径，先说明更简单的方案，不要直接走更重的方案。
- 遇到不清楚的地方，先指出具体不清楚的点；不要带着疑问直接编码。

### 2. Simplicity First

- 只写解决当前问题所需的最少代码，不为“以后可能会用”预留抽象、配置项、扩展点、额外 schema 或路由。
- 单次使用的逻辑不要提前抽象成通用框架，除非当前需求已经明确要求复用。
- 不要为了“灵活性”引入未被需求要求的参数、模式、状态机分支或层级。
- 不要为不现实的内部场景补充复杂错误处理；但对外稳定边界、contract 边界、用户输入边界仍需保持明确校验和错误语义。
- 改完后回看一次：如果 200 行能收敛成 50 行且不损失清晰度，就继续简化。

### 2.5 Less Is More

- 更少的代码、更少的分支、更少的状态，通常意味着更低的维护成本和更少的隐患。
- 优先删除多余复杂度，而不是在原有复杂度上继续叠加判断、兼容分支或“临时兜底”。
- 能通过澄清数据流、收敛责任边界、去掉例外分支来解决的问题，不要改成额外补丁层。
- 当两个方案都可行时，默认选择更短路径、更少依赖、更少概念、更容易验证的那个。

### 3. Surgical Changes

- 只修改与当前需求直接相关的代码；不要顺手重构相邻模块、改注释、改命名、重排 import、统一格式或清理历史问题。
- 保持现有代码风格和组织方式，除非本次任务明确要求调整。
- 只清理“因本次改动而产生”的无用 import、变量、函数或分支；不要顺手删除既有死代码。
- 如果发现无关但值得处理的问题，可以说明，但不要在同一改动里一起修。
- 每一处改动都应能直接追溯到本次需求；无法追溯的改动不要提交。
- 聊天相关能力必须继续复用统一流式入口 `/api/v1/ws`；禁止新增专用聊天 WebSocket 路由。

### 3.5 Main Merge Workflow

- 当用户要求“合并到 main”时，除了在干净 worktree 里完成 merge / push / 部署验证，还必须把当前 Codex 本地工作区的可见分支状态一并收口到 `main`。
- 如果当前工作区存在未提交改动，禁止强行切换到 `main`；必须先明确说明哪些脏改动阻塞切换，并让用户决定是提交、暂存、丢弃还是保留在当前分支。
- 合并到 `main` 后的最终汇报必须分别说明：远端 `origin/main` 的 commit、部署状态、当前本地工作区是否已经切回 `main`，以及如果没切回的具体原因。

### 3.6 Branch and Worktree Discipline

- 默认不要因为“新任务”就自动创建或切换 Git 分支；除非用户明确要求新建分支、切分支、创建 worktree、开 PR，或当前任务存在必须隔离的高风险改动。
- 开始任何会修改文件的任务前，先查看当前 `git status --short --branch`，并把当前分支和未提交改动纳入执行判断。
- 如果当前分支已经承载同一条任务线，优先继续在当前分支完成；不要为连续修复、同一功能的 follow-up、文档补充或小范围测试修复额外开分支。
- 如果用户要求多个功能并行开发，必须使用独立 `git worktree` 做物理目录隔离，除非用户明确要求不要创建 worktree；不要在同一个工作区里靠频繁切分支来并行开发。
- 创建 worktree 前必须说明：新 worktree 路径、基线分支、目标分支名、该 worktree 负责的任务范围；创建后该 Codex 会话只在对应 worktree 内工作。
- 如果当前工作区有未提交改动，禁止为了切分支而强行 stash、reset、checkout 或移动用户改动；必须先说明冲突文件，并让用户决定如何处理。
- 只有在用户明确要求提交时才提交；提交时必须保持 scope narrow，只 stage 本次任务直接相关文件，不把并行任务、生成产物或无关脏改动混进同一个 commit。

### 3.7 Aliyun SSH Write Boundary

- 铁律：DeepTutor 在阿里云 SSH 上只能修改 `/root/deeptutor` 目录内的文件内容；其他路径一概不允许修改。
- 任何 `ssh Aliyun-ECS-2`、远端脚本、`rsync`、`scp`、`docker cp`、热修、备份、回滚、部署验证，只要会写远端宿主机文件，目标路径必须先证明落在 `/root/deeptutor` 内。
- `/root/luban`、`/etc`、`/usr`、`/var`、`/opt`、`/home`、nginx 系统配置、系统服务、全局 cron、宿主机 Docker 配置等非 `/root/deeptutor` 路径全部视为只读观察面；不得创建、编辑、删除、移动、覆盖。
- 需要查看非 `/root/deeptutor` 路径时，只允许执行只读命令，如 `ls`、`cat`、`sed -n`、`grep/rg`、`docker ps`、`docker logs`；不得带重定向、`tee`、`rm`、`mv`、`cp`、`chmod`、`chown`、包管理安装或任何会改变宿主机状态的动作。
- 如果某个修复看似必须改 `/root/deeptutor` 之外的文件，必须停止执行，先向用户说明原因、目标路径、风险和替代方案；未获得用户新的明确授权前，一律不改。
- 所有阿里云发布脚本和运维 runbook 必须把 `/root/deeptutor` 作为唯一写入根目录；不要通过临时目录绕开这条边界。

### 4. Goal-Driven Execution

- 开始前先把任务改写成可验证目标，而不是“差不多能用”。
- 任何代码变更都必须执行与本次改动直接相关的测试；如果缺少运行环境，先补齐环境再测试，不能跳过。
- 修 bug 时：先写一个能复现问题的测试，再定位根因，最后修改实现让测试通过。
- 加功能时：先定义验收标准，再实现，并补足最小必要测试。
- 做重构时：先说明“行为不变”的验证方式，并确保改动前后相关测试通过。
- 多步骤任务先给出简短计划；每一步都要写明对应验证方式。
- 完成后明确汇报：改了什么、如何验证、还有哪些未覆盖风险；若确实存在无法执行的测试，必须说明具体阻塞，而不是笼统写“未测”。
- 缺少 `node` / `npm` / `deno` 等运行环境时，先自行安装补齐后再继续，不得以环境缺失为由跳过验证。
- 只要改了代码，就必须执行与改动直接相关的测试，不能只改不测；前端或微信小程序改动，除自动化测试外，还必须至少完成一次微信开发者工具中的模拟器或真机回归验证。

### 4.1 WeChat DevTools CLI Discipline

微信开发者工具 CLI 是 DeepTutor 微信前端日常 QA 的默认可用工具，不是临时人工补充。涉及 `wx_miniprogram`、`yousenwebview/packageDeeptutor`、TutorBot 微信端、微信渲染、聊天入口、WS、登录态、报告页、题卡或行为埋点的测试时，默认优先用终端调用 DevTools CLI / 自动化端口，而不是让 Codex Desktop 控制 GUI。

CLI 路径固定为：

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli
```

默认执行梯度：

1. 先跑 `/wechat-harness`、node contract、backend harness 等快速检查，覆盖可见行为和确定性 contract。
2. 再用 DevTools CLI 打开主微信包 `yousenwebview/packageDeeptutor`，只把实际打开并执行过场景的结果记为 `real_wechat_package` 证据。
3. 只有涉及真机特有风险、发布前验证、授权/登录/网络环境差异、或用户明确要求时，再补真机/线上小程序。

推荐命令：

```bash
WX_DEVTOOLS_CLI=/Applications/wechatwebdevtools.app/Contents/MacOS/cli
$WX_DEVTOOLS_CLI islogin
$WX_DEVTOOLS_CLI open --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor --lang zh
$WX_DEVTOOLS_CLI auto --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor --auto-port 9420
```

证据边界：

- `islogin` 只证明微信开发者工具登录态可用，不证明项目打开、页面渲染、网络链路或 TutorBot 对话通过。
- `open --project` 只证明项目可被 DevTools 打开；必须跑到具体页面、操作或自动化脚本，才能写 `real_wechat_package` pass。
- `auto --project ... --auto-port ...` 可作为 miniprogram-automator / Minium 的入口；只有脚本实际驱动页面并记录结果，才算自动化证据。
- `/wechat-harness`、`wx_miniprogram`、backend harness、node contract 仍不能替代 `yousenwebview/packageDeeptutor` 的主微信入口 closure。
- 如果为了不打扰用户环境没有执行 DevTools project-open / auto，最终结论必须写 `partial` 或 `true-entry pending`，不能把 Web/contract 绿灯说成真微信入口 PASS。
- 默认不执行 `upload`；小程序上传/预览流水线优先考虑 `miniprogram-ci`，除非用户明确要求使用 DevTools CLI 发布相关命令。

### 5. Fix Root Causes, Not Symptoms

- 修复问题时必须优先寻找根因，不能只对表面症状做妥协性补丁。
- 禁止陷入“打补丁漩涡”：不要在原有例外上再套一层例外、在旧分支外再包一层特殊判断，或靠增加兜底逻辑掩盖真实问题。
- 如果一个问题反复出现，默认说明抽象、边界、状态流转或 contract 理解存在缺陷，应优先修正源头。
- 只有在明确受兼容性、发布窗口或外部依赖限制时，才允许临时缓解；但必须明确说明为什么不能一次治本，以及后续根治路径。
- 任何“临时修复”都必须被明确标记为权衡，而不能伪装成最终方案。

### 5.5 Root-Cause Thinking Method

- 调问题时，先把“怎么修”压住，先回答“真正坏掉的业务事实是什么”。不要直接从实现细节、现成补丁、表面输入形式出发。
- 任何复杂 bug，先做四层抽象：
  1. `业务事实`：系统本来应该保证什么成立？
  2. `authority`：这个事实应由谁唯一负责写入、保存、恢复、读取？
  3. `断点`：最后一个正确点和第一个错误点之间，哪一层把事实丢了、改了、绕开了？
  4. `修法类型`：应该做减法、收权、删重复判断，还是确实需要新增能力？
- 优先用 first principles 重述问题，而不是沿用现有模块名、历史补丁名、前人解释。模块名只是实现，业务事实才是本体。
- 遇到看起来很多样的症状，先找它们共同的失败形状，不要急着按场景拆分。很多问题表面是 A 场景、B 场景、C 输入，根上其实都是同一个 state continuity、authority drift、terminal truth 或 object continuity 问题。
- 默认先问“为什么系统会需要这么多补丁”。如果一个问题只能靠越来越多特例维持，优先怀疑：概念重复、authority 不唯一、路由重复决策、状态流转断裂、边界没有收紧。
- Thin wrappers, fat skills 是最高优先级的结构门槛；first principles 用来确认业务事实，less is more 用来减少概念和状态，但实现落点必须先遵守“薄 wrapper、胖 skill”。
- Less is more 的真正含义不是“代码少一点”，而是：
  1. 概念更少
  2. authority 更单一
  3. 决策点更少
  4. 状态更少
  5. 链路更短
  6. 验证更直接
- 方案选择时，默认先比较“系统复杂度净变化”，不是只比较“眼前能不能过”。如果一个方案让未来多一个解释器、多一套路由、多一份状态、多一个 mirror truth，它通常不是好方案，即便短期能 work。
- 遇到“是不是要加一层分类器 / interpreter / wrapper / fallback / special case”的冲动时，先停下来问：
  1. 这是不是在修 authority，还是在绕开 authority？
  2. 这是不是把语义问题错误降级成模式匹配问题？
  3. 主链路为什么不能直接承担这个判断？
  4. 删除一层旧逻辑后，问题会不会反而更清楚？
- 面对新技术选型时，不要被“更高级”“更智能”迷惑。LLM、regex、规则、状态机、路由器都只是手段。关键问题是：哪一种手段最符合当前业务事实，且不会制造第二套 authority。
- 对依赖上下文的理解问题，默认优先“利用已有 authoritative context 的主链路理解”；对格式稳定、边界明确的问题，才优先用确定性规则。不要反过来。
- 每次复盘都必须提炼到可迁移的层级，至少写出三件事：
  1. 这次真正的一等业务事实是什么
  2. 我之前为什么把问题想窄了
  3. 更符合 first principles / less is more 的通用思路是什么

### 5.6 Why Teams Repeat The Same Mistakes

- 光写“thin wrappers, fat skills”“first principles”“less is more”“不要打补丁”还不够。团队和 agent 之所以反复犯老错误，通常不是因为不知道这些口号，而是因为没有把它们变成设计前的强制门槛。
- 常见复发机制有五种：
  1. 把原则当价值观，而不是当设计约束
  2. 把当前症状当问题本体，跳过业务事实抽象
  3. 把“快速可过”误当成“正确方向”
  4. 习惯沿现有字段、模块、补丁名继续思考，而不是回到一等事实
  5. 文档只说“不要这样”，却没有规定“如果想这样做，必须先证明什么”
- 以后凡是涉及状态、路由、上下文承接、follow-up、router、interpreter、fallback、wrapper、skill、kernel 的设计，开始前必须先写出六件事：
  1. `thin wrapper / fat skill split`：哪些代码只是边界薄适配，哪个 skill / kernel / service 是胖能力 authority
  2. `一等业务事实`：系统真正要维护的唯一事实是什么
  3. `单一 authority`：这个事实由谁唯一写、存、恢复、读
  4. `概念收敛`：这次准备删除、降级或归一化哪些旧概念
  5. `加法理由`：如果要新增字段 / router / wrapper / state，为什么删不掉旧层
  6. `LLM vs deterministic`：为什么这件事应该由主 LLM 判断，或者为什么必须 deterministic
- 如果这六件事写不出来，不允许开始设计，更不允许开始编码。
- 旧版五件事仍然可以作为检查清单，但不得跳过 thin wrapper / fat skill split。
- 对任何新增的 router / classifier / interpreter / fallback / special-case state，一律默认先做“有罪推定”：
  1. 它是不是在制造第二套 authority？
  2. 它是不是在把语义问题错误降级成规则问题？
  3. 它会不会让系统多一个无法删除的中间状态？
  4. 它未来会不会诱发更多特例补丁？
- 文档内容设计也必须防复发：原则章节后面必须跟“复发机制”和“硬门槛”，否则 agent 很容易在高压 debugging 场景里重新滑回熟悉但错误的套路。

### 5.7 Single Authority Hard Gate

- `单一权威` 不是建议，而是设计和修复时的硬门槛。同一业务事实只能有一个 canonical truth source，必须能明确回答：谁唯一写、谁唯一存、谁唯一恢复、谁唯一读取。
- 凡是涉及状态、路由、上下文承接、follow-up、resume、router、interpreter、fallback、trace 对齐、final 输出组装，开始前必须先写清楚：
  1. `one business fact`：这次真正要维护的唯一业务事实是什么
  2. `one authority`：这个事实由谁唯一写、唯一存、唯一恢复、唯一读取
  3. `competing authorities`：现在有哪些模块、字段、状态、fallback、transport 层在偷偷争夺这个 authority
  4. `canonical path`：从 writer 到 persistence / transfer / routing / assembly，再到 reader 的唯一主链路是什么
  5. `delete or demote`：这次准备删除、降级、归一化哪些 mirror state、重复决策点、旁路 reader、兼容别名或 transport 再加工
- 如果上面五件事写不出来，说明你还停留在症状层，不允许开始 patch。
- 默认修法顺序必须是“先收权，再补逻辑”。优先删除：
  1. mirror state competing with canonical state
  2. duplicate decision points
  3. bypass routing / bypass readers
  4. transport 层对 canonical result 的二次改写
  5. 兼容层中继续参与执行决策的 alias
- 任何新增字段 / 状态 / router / classifier / interpreter / wrapper / fallback，默认先视为可疑。只有先证明下面四件事，才允许加：
  1. 它没有制造第二套 authority
  2. 它没有把语义问题错误降级成模式匹配问题
  3. 它不会成为未来新的 patch anchor
  4. 旧层确实不能删，且主链路确实不能直接承担
- 遇到 follow-up / routing / state continuity 问题时，默认先排查 authority，而不是先补 regex。先确认：
  1. 是否已经存在 authoritative context
  2. 主链路是否真的使用了这份 context
  3. route / final / resume 是否基于这份 context 做判断
  4. 第一个错误 reader 或错误 decision 点到底在哪
- `regex`、`fallback`、确定性规则只允许在两种情况下承担辅助职责：
  1. 输入格式稳定、边界清晰、歧义很低
  2. 主链路已经正确，只需要低成本保底
- 如果 `regex`、`fallback`、wrapper、classifier 开始承担主要理解职责，视为 authority 越权，必须回到主链路收权。
- 任何修复完成后，除功能回归外，还必须额外说明三件事：
  1. 这次真正坏掉的一等业务事实是什么
  2. 哪些地方曾经在争夺 authority
  3. 为什么修完后系统比之前更接近单一 authority，而不是又多了一层补丁

### 5.8 Post-QA Root-Cause Gate

以下规则来自 2026-06-06 WeChat TutorBot authority loop 的复盘，用于防止后续 agent 把同类问题再次修窄、修散或修成补丁堆。

凡是 TutorBot / WeChat / question authority / follow-up / refusal / state continuity / terminal answer 问题，开始修复前必须先写清：

1. `one business fact`：本轮真正要维护的业务事实是什么
2. `one authority`：该事实由谁唯一写、存、恢复、读取
3. `competing authorities`：哪些模块、字段、fallback、transport、frontend projection 或 artifact 可能在抢权
4. `canonical path`：从 writer 到 persistence / transfer / routing / final assembly 的主链路是什么
5. `delete or demote`：这次准备删除、降级或归一化哪些 mirror truth / duplicate decision / bypass reader
6. `deterministic vs LLM boundary`：哪些只允许规则识别稳定格式，哪些必须交给已有 authoritative context 与主语义链路

修复后必须额外检查：

- 是否把 `/wechat-harness`、`wx_miniprogram`、near-real HTTP+WS 或 backend harness 证据误写成真实 `yousenwebview/packageDeeptutor` closure
- 是否把 DevTools CLI 的 `islogin` 或 `open --project` 误写成真实微信场景已通过；没有页面/操作/自动化脚本结果时只能算环境预检或 partial
- 是否把 regex / fallback / wrapper 升级成语义 authority
- 是否至少有一个反例验证没有过拟合某个 marker phrase 或 QA 样例
- 是否证明 visible terminal answer、hidden answer authority、runtime state / active object 三者一致

项目级 agent workflow skills 放在 [agent-skills/](./agent-skills/)；它们是开发与 QA 工作法，不是 TutorBot runtime skills，不得移动到 `deeptutor/tutorbot/skills/`。优先使用：

- [deeptutor-authority-debugging](./agent-skills/deeptutor-authority-debugging/SKILL.md)：状态丢失、拒答、上下文断裂、follow-up 误路由、authority drift。
- [wechat-tutorbot-real-entry-qa](./agent-skills/wechat-tutorbot-real-entry-qa/SKILL.md)：真实微信 TutorBot 链路、DevTools、near-real / shadow 证据分级、客户满意度 QA。
- [anti-overfit-repair-review](./agent-skills/anti-overfit-repair-review/SKILL.md)：regex / fallback / special-case 修复后的过拟合复审、局部撤回或收敛。

## Architecture

```
Entry Points:  CLI (Typer)  |  WebSocket /api/v1/ws  |  Python SDK
                    ↓                   ↓                   ↓
              ┌─────────────────────────────────────────────────┐
              │              ChatOrchestrator                    │
              │   routes to ChatCapability (default)             │
              │   or a selected deep Capability                  │
              └──────────┬──────────────┬───────────────────────┘
                         │              │
              ┌──────────▼──┐  ┌────────▼──────────┐
              │ ToolRegistry │  │ CapabilityRegistry │
              │  (Level 1)   │  │   (Level 2)        │
              └──────────────┘  └────────────────────┘
```

### Level 1 — Tools

Lightweight single-function tools the LLM calls on demand:

| Tool                | Description                                    |
| ------------------- | ---------------------------------------------- |
| `rag`               | Knowledge base retrieval (RAG)                 |
| `web_search`        | Web search with citations                      |
| `code_execution`    | Sandboxed Python execution                     |
| `reason`            | Dedicated deep-reasoning LLM call              |
| `brainstorm`        | Breadth-first idea exploration with rationale  |
| `paper_search`      | arXiv academic paper search                    |
| `geogebra_analysis` | Image → GeoGebra commands (4-stage vision pipeline) |

### Level 2 — Capabilities

Multi-step agent pipelines that take over the conversation:

| Capability       | Stages                                         |
| ---------------- | ---------------------------------------------- |
| `chat`           | responding (default, tool-augmented)           |
| `deep_solve`     | planning → reasoning → writing                 |
| `deep_question`  | ideation → evaluation → generation → validation |

### Playground Plugins

Extended features in `deeptutor/plugins/`:

| Plugin            | Type       | Description                          |
| ----------------- | ---------- | ------------------------------------ |
| `deep_research`   | playground | Multi-agent research + reporting     |

## CLI Usage

```bash
# Install CLI
pip install -r requirements/cli.txt && pip install -e .

# Run any capability (agent-first entry point)
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2=4" -t rag --kb my-kb
deeptutor run deep_question "Linear algebra" --config num_questions=5

# Interactive REPL
deeptutor chat

# Knowledge bases
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf

# Plugins & memory
deeptutor plugin list
deeptutor memory show

# API server (requires server.txt)
deeptutor serve --port 8001
```

## Key Files

| Path                          | Purpose                              |
| ----------------------------- | ------------------------------------ |
| `deeptutor/runtime/orchestrator.py` | ChatOrchestrator — unified entry     |
| `deeptutor/core/stream.py`          | StreamEvent protocol                 |
| `deeptutor/core/stream_bus.py`      | Async event fan-out                  |
| `deeptutor/core/tool_protocol.py`   | BaseTool abstract class              |
| `deeptutor/core/capability_protocol.py` | BaseCapability abstract class    |
| `deeptutor/core/context.py`         | UnifiedContext dataclass             |
| `deeptutor/runtime/registry/tool_registry.py` | Tool discovery & registration |
| `deeptutor/runtime/registry/capability_registry.py` | Capability discovery & registration |
| `deeptutor/runtime/mode.py`         | RunMode (CLI vs SERVER)              |
| `deeptutor/capabilities/`           | Built-in capability wrappers         |
| `deeptutor/tools/builtin/`          | Built-in tool wrappers               |
| `deeptutor/plugins/`                | Playground plugins                   |
| `deeptutor/plugins/loader.py`       | Plugin discovery from manifest.yaml  |
| `deeptutor_cli/main.py`             | Typer CLI entry point                |
| `deeptutor/api/routers/unified_ws.py` | Unified WebSocket endpoint         |

## Plugin Development

Create a directory under `deeptutor/plugins/<name>/` with:

```
manifest.yaml     # name, version, type, description, stages
capability.py     # class extending BaseCapability
```

Minimal `manifest.yaml`:
```yaml
name: my_plugin
version: 0.1.0
type: playground
description: "My custom plugin"
stages: [step1, step2]
```

Minimal `capability.py`:
```python
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

class MyPlugin(BaseCapability):
    manifest = CapabilityManifest(
        name="my_plugin",
        description="My custom plugin",
        stages=["step1", "step2"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        async with stream.stage("step1", source=self.name):
            await stream.content("Working on step 1...", source=self.name)
        await stream.result({"response": "Done!"}, source=self.name)
```

## Dependency Layers

```
requirements/cli.txt            — CLI full (LLM + RAG + providers + tools)
requirements/server.txt         — CLI + FastAPI/uvicorn (for Web/API)
requirements/math-animator.txt  — Manim addon (for `deeptutor animate`)
requirements/dev.txt            — Server + test/lint tools
```
