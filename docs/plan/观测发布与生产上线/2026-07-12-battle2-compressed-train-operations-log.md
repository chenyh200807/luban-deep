# Battle2 压缩列车过程志 — 发现→分析→解决(给后来者的破案笔记)

> owner 指令:记录所有动作——怎么发现问题、怎么分析思考、怎么解决,方便后来者学习应用。
> 本文是 2026-07-12 压缩列车(PR-1 合并→部署#1→基线→PR-2/3→部署#2→配对批)的完整过程志。
> 结果数字见 `2026-07-12-battle2-paired-batch-results.md`;本文只讲**过程与方法**。

## 事件 1:PR#447 CI 红(Security Scan + Test Summary)

- **发现**:`gh pr checks 447` 报 2 FAIL,且 PR 状态 BEHIND(main 被 PR#446 推进)。
- **分析**:先合 main 再本地复现。跑 `detect-secrets-hook` 得 EXIT=3——第一直觉是"有新密钥",但对比 baseline diff 发现只有 generated_at 变化。**关键破案**:EXIT=3 不是"发现密钥",是"baseline 未 staged"的专用错误码;`git add .secrets.baseline` 后重跑 EXIT=0,hook 顺手把 2 处测试文件的行号刷新了。
- **解决**:提交 2 处行号更新(无新 hash),CI 转绿。
- **教训**:detect-secrets-hook 的 exit code 语义要分清:3=baseline没staged,1=真发现;别看到非零就开始找"泄漏"。

## 事件 2:部署#1「env 新代码旧」假绿(本日最重要的坑)

- **发现**:部署脚本 exit 0、五层核验全绿(host .env SHA=容器 env SHA=目标、healthy、公网、observability),但**容器内符号 grep=0**(completion_start_time 在 4 个文件全查不到)。若没做符号取证,这次部署就以"成功"记录在案而实际观测基座根本没上线。
- **分析路径**(逐层收窄):
  1. 本地 release 树 grep → 符号在(排除"代码本来就没有")。
  2. 远端 `/root/deeptutor` 源码 grep → 符号在(排除"rsync 没同步")。
  3. 容器内 grep=0 + 镜像构建时间戳=刚刚 → **镜像是新构建的却含旧代码**。
  4. md5 比对容器文件 vs 宿主源码 → 不一致,实锤。
  5. 回看部署日志:SSH 在"远端运行态备份"步被 remote host 断开——脚本中段夭折,但某个构建仍以旧上下文完成并 recreate 了容器(带上了已注入的新 .env)。
- **解决**:确认无并行构建在跑(防两构建撞容器)后重跑部署脚本并**全量留日志**;这次看到完整 COPY 层重跑;完成后 md5 逐字一致才放行。
- **教训(已写进 memory 与 runbook)**:五层核验+容器 just-now 仍可假绿;**终极门=md5 比对容器内文件 vs 宿主源码**。SSH 断连后禁止盲目重跑,先三查(远端构建进程/origin SHA/容器代码内容)。

## 事件 3:远端读数三连坑(写边界/py3.6/metrics 鉴权)

- **发现**:上传 Langfuse 读数脚本被本地 hook 拦(阿里云写边界只许 /root/deeptutor);改落点后报 UnicodeDecodeError;Prometheus curl 返回 401。
- **分析/解决**:①临时脚本落 `/root/deeptutor/tmp_*.py` 用完即删;②宿主是 python3.6:open 必须显式 `encoding="utf-8"`,没有 `datetime.fromisoformat`,用 strptime 兼容;③metrics 鉴权模式别自己猜——**读仓库里现成的 `verify_aliyun_observability.sh`**,它示范了 `X-Metrics-Token`(.env 的 DEEPTUTOR_METRICS_TOKEN)+ 127.0.0.1:8001。
- **教训**:服务器侧读数的正确姿势永远先看仓库既有 verify 脚本怎么做,别重新发明鉴权。

## 事件 4:owner 挑战基线窗 → 实验设计重构

- **发现**:owner 指出"没什么会员,等 24-48h 有意义吗?"
- **分析**:对——自然流量≈0 时窗口采不到样本,这恰是终审"别为不存在的负载优化"的镜像。但直接跑批也有坑,过 eval-design 排雷后发现**最大的设计风险不是混淆,是指标错位**:PR-2/3 无 flag 项砍的是成本+异步尾巴,不是首字延迟;只测 TTFT 会得出"没效果"的假阴性。
- **解决(设计四件套)**:①指标对准刀落点(每 turn LLM 调用数/token/成本/trace 总时长),TTFVT 只作"无恶化"回滚门;②两臂贴着部署跑(<25min)控 provider 时段;③两臂各埋 10 个相同 ping 作漂移哨兵(>30% 判混淆);④**可证伪声明先写死**(TTFVT 恶化>10%=回滚)再跑。
- **教训**:被质疑时先判断质疑对不对,对就重构方案而不是辩护;实验设计的第一问是"这个结果会不会因为设计而无意义"。

## 事件 5:批跑 agent 的三个生产坑(全部现场破案)

1. **eval-bypass 静默失效**:`claude_` 前缀不在服务端 cohort 白名单(只认 qa_/test_/operator_),X-Eval-Bypass 静默 `identity_out_of_scope`,撞 free_trial 每日 3 条配额。破案法=单用户 4 连发验证配额行为。改 `qa_claude_*` 前缀后 bypass 真生效。
2. **注册限流 3/60s**:改为 3 用户池 login 复用,每会话独立 conversation。
3. **夭折批污染差分**:前两次夭折批的 13 turn 会污染 Prometheus 差分——解法=重拍批前快照,把夭折批隔离在窗口外。
- **教训**:合成批跑的身份/配额/限流问题都是静默失败,每一步要有"真生效"的独立验证,不能只看请求 200。

## 事件 6:Langfuse 名匹配陷阱(两臂 summary=0 之谜)

- **发现**:PRE 臂 Langfuse 按名字搜 "summary"/"heartbeat" 全是 0——一度误判"合成会话不触发摘要维护"。
- **分析**:POST 臂部署了专用 Prometheus 计数器后真相出现:summary_maintainer 42 决策全覆盖(实跑 31/skip 11)。它的 LLM 调用在 Langfuse 里叫 `llm.complete`,**名字口径搜索完全不可靠**。
- **解决/教训**:观测断言必须锚定专用计数器(这正是先部署观测基座的价值);用名字模糊匹配下"没调用"的结论是危险的。本文作者自己也在中途报告里犯了这个误判,靠新计数器纠正——**误判要留痕,后来者才知道这个坑长什么样**。

## 事件 7:能力分支融合审计(owner 问"你只看 tutorbot?")

- **发现**:owner 指出关注面偏 tutorbot,问 deep_question 等分支是否都融进统一对话、还有什么可优化。
- **分析方法**:不靠记忆回答,派只读测绘 agent 拿当前 main 的 file:line 证据,回答三问:能力清单/旁路清单、旁路×底座收益矩阵、残余优化点。
- **结论**:见同目录 `2026-07-12-capability-branch-fusion-audit.md`。要点:orchestrator 只有 7 个真 capability,mcq/case 判分是 scene 复用 deep_question(已融合);摸底/报告/错题本/轻练进度是 REST 旁路(设计如此,但系统性缺 turn 专属底座:TTFVT/摘要门控/turn 落库);揪出两个"同病兄弟"(memory_service 无门控双 LLM、JSONL 每 turn 双次全文件线性读)。

## 编排方法(这趟列车怎么跑并行的)

- **双 Opus agent 并行**:批跑 agent(PRE 臂)与 PR 组装 agent 同时开跑,互不碰文件;主控只做裁决与放行。
- **同 agent 跑两臂**:POST 臂用 SendMessage 续同一个批跑 agent(带着 PRE 臂全部上下文与驱动脚本),保证两臂方法逐字一致——配对实验的"同一把尺子"。
- **CI 用 Monitor 盯**:收敛才唤醒,不轮询烧上下文。
- **合并≠上线**:PR 合并不影响生产(部署才是闸),所以 PRE 臂还在跑时就可以放心合 PR,省串行等待。
- **工件抢救**:批跑结果在会话级 scratchpad,会话结束即蒸发——收线前必须把 json/md/驱动脚本 cp 进 git。

## 本趟列车的失败尝试清单(诚实账)

1. 部署#1 首跑失败(SSH 断+假绿)——重跑治愈,教训进 memory。
2. Langfuse 读数脚本连报 3 错(写边界/编码/fromisoformat)——逐个修,模板已沉淀。
3. PRE 臂前两批夭折(前缀 cohort 坑)——隔离后重跑。
4. 主控中途误判"合成会话不触发摘要维护"——被新计数器证伪,已在终报纠正。
5. W2-T4 微基准脚本"入库"任务发现脚本从未被提交过(当时是临时文件)——按"不凭空重写"跳过,而不是造一个假装还原的。
