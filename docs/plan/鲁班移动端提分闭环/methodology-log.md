# 方法志(methodology-log)— 发现→分析→解决的完整叙事,倒序追加

> owner 常设指令(2026-07-12):记录所有动作的"怎么发现/怎么分析/怎么解决",供后来者学习应用。
> 五段式模板:①现象(证据) ②发现路径(含走错的岔路) ③分析(root cause+shared failure shape) ④修法与理由(file:line) ⑤验证+教训(带数字;一句可迁移的话)。
> **失败的尝试和被证伪的假设必须写——这是最值钱的一栏。** 分层:方法志=操作级(repo 内)/memory=项目级 playbook/skill=跨项目方法论。
> 战役级完整编年另见各战役 ops-log(如 `docs/plan/观测发布与生产上线/2026-07-12-battle2-compressed-train-operations-log.md`)。

---

## 2026-07-12 部署「env 新代码旧」假绿(五层核验全绿仍是假的)

1. **现象**:部署#1 脚本 exit 0,五层核验全绿(host .env SHA=容器 env SHA=目标/healthy/公网/observability),但容器内 `grep completion_start_time`=0——观测基座实际没上线。
2. **发现路径**:靠"容器符号取证"这第六道非标准动作撞出来的;若只走标准五层就记成功了。歧路:一度怀疑并行部署者覆盖(查了 origin SHA 与构建进程,排除)、怀疑 grep 路径错(用容器内 python import __file__ 证实路径对)。
3. **分析**:SSH 在部署脚本中段(远端备份步)被断,某次构建以**旧源码上下文**完成镜像并 recreate 容器,而 .env 注入发生在断连前——env 是新的,镜像是旧的。shape=**自证陷阱**(脚本自报+SHA 标签都不是终态观测)。
4. **修法**:确认无并行构建后重跑完整部署(全量留日志);判据升级=md5 比对容器内文件 vs 宿主 `/root/deeptutor` 源码(`docker compose exec -T deeptutor md5sum <f>` vs `ssh md5sum`)。
5. **验证+教训**:重跑后 3 关键文件 md5 逐字一致;写回 memory(aliyun-deploy 防假成功)与 runbook。**可迁移**:「容器 just-now+SHA 对齐」仍可假绿,发布终极门=容器内文件指纹与源码逐字比对。

## 2026-07-12 eval-bypass 静默失效(前缀 cohort 坑)

1. **现象**:合成批跑 turn 到第 4 条撞 free_trial_daily=3 配额,X-Eval-Bypass 看似带上了却不生效。
2. **发现路径**:先怀疑 bypass key 错(核 ~/.deeptutor_eval_key,对);再单用户 4 连发做最小复现,读响应发现 `identity_out_of_scope`——bypass 是**静默**降级,不报错。
3. **分析**:服务端 eval cohort 白名单只认 `qa_/test_/operator_` 前缀,自拟的 `claude_` 前缀不在册。shape=**静默 fail-open**(越权身份不拒绝而是当普通用户)。
4. **修法**:前缀改 `qa_claude_*`;两次夭折批(13 turn)靠**重拍批前 Prometheus 快照**隔离出窗口,不污染差分。
5. **验证+教训**:改后单用户 4 连发全通过;42/42 turn 完成。**可迁移**:合成流量的身份/配额/限流失败都是静默的,每一步要独立验证"真生效",HTTP 200 不算数。

## 2026-07-12 Langfuse 名字口径陷阱(两臂 summary=0 之谜)

1. **现象**:配对批 PRE 臂按名字搜 "summary"/"heartbeat" 的 generation=0,一度得出"合成会话不触发摘要维护"的结论(主控自己误判,已留痕)。
2. **发现路径**:POST 臂部署了专用 Prometheus 计数器,读到 summary_maintainer **42 决策全覆盖**(实跑 31/skip 11)——与 Langfuse 名字口径矛盾,矛盾即线索。
3. **分析**:summary maintainer 的 LLM 调用在 Langfuse 里名叫 `llm.complete`,不含 "summary"。shape=**名字≠语义**(用命名模糊匹配做存在性断言)。
4. **修法**:观测断言一律锚定专用计数器/结构化字段;名字匹配只用于探索不用于结论。
5. **验证+教训**:计数器 42=42 turn 对账。**可迁移**:「按名字搜=0」永远不能证明"没发生",只能证明"没这么命名"。

## 2026-07-12 基线窗被 owner 挑战 → 实验重设计(假阴性风险)

1. **现象**:原计划采 24-48h 自然流量基线;owner 问"没会员,等有意义吗"。
2. **发现路径**:核对留存事实(42 注册/60% 零消息/D1≈0)——窗口期采样≈0,质疑成立。
3. **分析**:更深的坑是**指标错位**:本轮改动砍的是成本+异步尾巴,不是首字延迟;若只对比 TTFT 会得出"没效果"的假阴性。shape=**测量目标与干预目标错位**。
4. **修法**:压缩为部署前后同题配对批(间隔<25min 控时段),指标对准刀落点(LLM 调用数/token/成本/trace 总时长),TTFVT 只作回滚门;漂移哨兵×10;可证伪声明先写死再跑;过 eval-design 排雷。
5. **验证+教训**:结果成本 -27.7%/尾巴 -33.5%/TTFVT -13.2%,哨兵 +18%<30% 阈无混淆。**可迁移**:被质疑先判真伪,真则重构方案;实验设计第一问="这个指标测的是我改的东西吗"。

## 2026-07-12 能力分支融合审计(回答"你只看 tutorbot?")

1. **现象**:owner 质疑优化只覆盖 tutorbot,deep_question 等分支被忽略。
2. **发现路径**:不用记忆答,派只读测绘 agent 对 main 逐文件取证(capability 注册表→scene 分发→REST 旁路→底座矩阵)。
3. **分析**:orchestrator 真 capability 仅 7 个;mcq/case 判分、轻练出题是 scene **复用** deep_question(已融合,自动吃到全部 turn 底座);五模块是设计性 REST 旁路。"tutorbot.llm.stream" 只是 LLM 命名口径,不代表优化范围。
4. **修法**(产出):旁路×底座矩阵+残余优化点清单(followup flag 白拿项/memory_service 无门控双 LLM/JSONL 双次线性读/repair 全量重发/摸底直连 LLM 无观测),入档 `2026-07-12-capability-branch-fusion-audit.md`。
5. **验证+教训**:全部论断带 file:line,不确定项显式标"未证实"。**可迁移**:回答覆盖面质疑,用当前代码证据测绘,不用战役记忆;修完一个病灶要主动扫"同病兄弟"。
