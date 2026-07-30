# 可宣传质量门 v1 — 固定场景集验收(promo gate)

**性质**:固定场景集,部署后必跑,**全绿 = 可宣传态**。断言全部确定性机器可判,
**门里不放 LLM judge**。这是"能不能对外说这个产品好用"的最后一道机器门。

## 纪律(不可协商)

- **owner 每次翻车,24h 内该事故原文永久入集**;入集测例**永不删除**、永不放水。
  只允许因真实回复格式变化去校准断言的表述形态,**A1/A2/A5 的语义不得弱化**。
- 跑挂的场景如实记 FAIL,不粉饰、不重跑洗绿。
- 全部操作对生产只读:QA 账号登录、发 turn、`ssh Aliyun-ECS-2 docker exec` 只读
  (`mode=ro`)查 `chat_history.db`。不改任何生产状态。

## 运行

```bash
cd <repo root>
python3 scripts/promo_gate/run_promo_gate.py                 # 全量 21 场景,串行
python3 scripts/promo_gate/run_promo_gate.py --only t2_half  # 只跑单场景
python3 scripts/promo_gate/run_promo_gate.py --dry-run       # 只校验场景文件
```

- 凭据:环境变量或 `--env-file`(默认 `~/Documents/CYH_2/Markzuo/deeptutor/.env`)
  里的 `WECHAT_QA_USERNAME/PASSWORD`(QA eval 账号,守 AGENTS Eval Runner Identity)。
- 运行器自动导出 `DEEPTUTOR_EVAL_RUNNER_AGENT=claude_code` 与唯一
  `DEEPTUTOR_EVAL_RUN_ID=promo_gate_<时间戳>`。
- 产出:`runs/promo_gate/<run_id>/report.md` + `report.json` + `evidence/*.md`,
  每场景跑完立即增量落盘。退出码:全绿=0,有 FAIL=1。

## 场景矩阵(v1 = 6 题 × 适用作答形态 = 21 场景)

| 题 | 来源 | full 全答 | half 半答* | wrong 答错 | question_only 只发题 |
|---|---|---|---|---|---|
| T1 题库内案例(qid=8817,2019 合同价款,计算题) | questions_bank | ✓ | ✓ | ✓(数值改错) | ✓ |
| T2 题库内案例(qid=17357,2023 质量检测) | questions_bank | ✓ | ✓ | ✓ | ✓ |
| T3 题库外长案例(2022 案例一改写,库外) | 真题改写 | ✓ | ✓ | ✓(数值改错) | ✓ |
| T4 历史事故原文(#583 拒答 / 判分死亡) | 事故 replay 原文 | ✓(g1) | ✓(q1) | ✓(g1 改错) | ✓(q1 原文) |
| T5 MCQ(qid=8731,氯离子复试) | questions_bank | ✓ | — | ✓ | ✓ |
| T6 KB 边界偏门题(金属幕墙/气密性) | 教材边缘 | ✓(带自己理解) | — | — | ✓ |

\* 半答 = 只答部分小问 + 「其余小问按规范补充」——owner 实际翻车形态,必须常驻。
MCQ 无半答形态、KB 边界题无判分形态,故 v1 为 21 场景而非 4×6=24。

**T1 通道待补**:指挥官裁决 T1 应走练题流带 int qid;练题流驱动过重,v1 降级为
「聊天粘贴同题」。练题流真入口通道(带 qid 的 practice 驱动)登记为 v2 待补项。

## 断言清单(每场景取适用项,配置在 scenarios/*.json)

| id | 语义 | 判据(确定性) |
|---|---|---|
| A0 | 入口必须完成 | turn status=completed 且回复非空(内置,所有场景) |
| A1 | 半答卷必须点破漏答 | 含「未纳入本次判分」,或 miss 用语 + 点名具体漏点 token(67% 全好话病杀招) |
| A2 | 得分不许注水 | 所有 X/Y 型得分 X≤Y,且不超场景配置的官方满分 |
| A3 | 禁假口诀 | 「口诀」段必须带出处或为模板句;只由漏点标题+顿号拼接即红 |
| A4 | 库外题必须免责 | 含「诊断得分预估/不硬估/非官方」类表述(仅 T3) |
| A5 | 禁罐头拒答 | 「拆小」「一道一道发」类语句出现即红(所有场景) |
| A6 | 判分权威可溯源 | result 事件 metadata 的 `score_authority` 与 `grading_rubric_provenance` 均非空(远端只读 DB 取证) |
| A7 | 案例必须走 deep | result metadata `selected_mode` 含 deep |
| A8 | 错因码分布 | 预留,拍板后启用,当前 SKIP |
| L1/M1/M2 | 场景私有 | min_length / contains_all / contains_any(如 MCQ 必点名正确选项「外加剂」) |

案例只发题场景(question_only)不强断 A6/A7(未发生判分),但 metadata 照抓入
evidence 作观测面。

## 门捕获的开放缺陷登记册(对齐指挥官台账 OD-001~004)

每轮运行捕获的**产品真病**(非断言校准、非环境失败)在此登记;歼灭一条→用重放
命令复验→复验绿后标记 CLOSED(条目不删,留痕)。测例本身永不删除。

### OPEN

**OD-004 — agent-loop 旁路:判分产出但权威双空**(t4_q1_half, A6;首捕获 r2)
**仍开放,已部分修复。** live 三轮(run `promo_gate_20260801_t4_verify_r1/2/3`,
SHA `79e21ed7`)结果 2/3:
- r1/r3 PASS:`execution_path=tutorbot_case_grading_v1_direct`,
  `score_authority=rubric_scored_v1_diagnostic`,`grading_rubric_provenance=derived_from_stem`。
- r2 FAIL:同一输入掉回 `execution_path=tutorbot_kb_first_full_agent_policy`,
  `score_authority=v1_unavailable:no_reference`(降级已发声,较 r3 的全空是进步),
  但 `grading_rubric_provenance` 仍空。
根因面:**admission 非确定性**——判分入闸对同一半答卷 2/3 命中、1/3 漏判,
落回通用 agent 路径现编。r3 的英文独白泄漏形态三轮均未复现(公共流无英文过程叙述)。
重放:`python3 scripts/promo_gate/run_promo_gate.py --only t4_q1_half`

### CLOSED

**OD-001 — 库外案例半答:未答小问被静默丢弃** — CLOSED 2026-08-01
修复:PR #610(作答标记族单一权威+参考入判 fail-closed),SHA `b039ae8d`。
关闭证据:run `promo_gate_20260801_t3_od001_verify` t3_half A1 PASS——
miss用语[漏点/漏掉/漏错] + 点名[第3问/问题3/问题4],未答内容(评定方法/构造柱/坎台)
逐条出现在判分卡。t3 全组 4/4 无回归。

**OD-002 — 库外案例已答小问被错参考判零** — CLOSED 2026-08-01
修复:同 PR #610,SHA `b039ae8d`。关闭证据:同 run,t3_half 命中 13(r3 时为 0)、
得分预估 5.85/10;grading_rubric_provenance=`derived_from_stem`(参考改锚题面);
分数梯度 t3_full 10/10 > t3_half 5.85/10 > t3_wrong 1.52/10 合理。

**OD-003 — #583 拒答事故原题只发题:模型空返回收束为 failed** — CLOSED 2026-08-01
修复:PR #612(修复轮结构差异化——剥工具形态,不依赖 provider tool_choice=none),
SHA `79e21ed7`。关闭证据:run `promo_gate_20260801_t4_verify_r1/2/3` 连续三轮
3/3 turn=completed、回复 3278/2928/3299 字非模板、终轮 finish_reason=stop
(r1/r2 经 `agent_loop_repair` 收束 content_chunk 415/381,r3 主循环直接 stop)。
t4_g1 两场景防回归 run `promo_gate_20260801_t4_g1_regress` 2/2 PASS。

(暂无其他)

## 事故入集登记

| 日期 | 事故 | 入集场景 |
|---|---|---|
| 2026-07(journal PR#583) | 5 小问长案例被罐头拒答(「拆小一点再发」) | t4_q1_asis / t4_q1_half |
| 2026-07 | 案例判分死亡(碳排放案例带作答判分无响应) | t4_g1_asis / t4_g1_wrong |

## 文件布局

```
scripts/promo_gate/
  run_promo_gate.py        # 运行器(串行、只读、增量落盘)
  scenarios/*.json         # 每场景:id/title/form/query_file/assertions/官方满分
  scenarios/queries/*.txt  # 题面+作答原文,全部自含入 repo(不依赖外部路径)
runs/promo_gate/<run_id>/  # report.md / report.json / evidence/*.md
```
