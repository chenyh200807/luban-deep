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

**OD-001 — 库外案例半答:未答小问被静默丢弃**(t3_half, A1;首捕获 r2, SHA 8d8bc5e4)
未答的问3/问4 在判分卡零提及(「评定方法/构造柱/坎台」全文不出现),半张卷被当
全卷收束——owner 翻车形态在库外题复发(库内 t1_half/t2_half 已能点破)。
重放:`python3 scripts/promo_gate/run_promo_gate.py --only t3_half`

**OD-002 — 库外案例已答小问被错参考判零**(t3_half 伴生;首捕获 r2)
已答的问1/问2 被判「命中0/漏错10」,判分参考答案与题面数据对不上(如参考
「1F柱等效龄期19d、累计616℃·d」与表2累计口径不符),疑似库外题错锚编译 rubric
而非题面自证。当前无独立确定性断言(需语义比对),经 t3_half evidence 人工复核。
重放:`python3 scripts/promo_gate/run_promo_gate.py --only t3_half`(看 evidence 判零面)

**OD-003 — #583 拒答事故原题只发题:模型空返回收束为 failed**(t4_q1_asis, A0;首捕获 r2)
50s 后 turn 终态 failed,可见回复仅「这次模型没有返回可见答案…请重新发送一次」。
非「拆小」罐头拒答(A5 绿),但事故原题仍不能稳定出答案。
重放:`python3 scripts/promo_gate/run_promo_gate.py --only t4_q1_asis`

**OD-004 — agent-loop 旁路:判分产出但权威双空**(t4_q1_half, A6;首捕获 r2)
回复完成逐点判分(A1 过),但 result metadata 的 score_authority 与
grading_rubric_provenance 均空,execution_path=tutorbot_kb_first_full_agent_policy——
判分由通用 agent 路径现编,未走判分权威链(违反「降级路径必须发声」硬不变量)。
重放:`python3 scripts/promo_gate/run_promo_gate.py --only t4_q1_half`

**r3 复验(SHA d1c2b44a,含 #601-#607)**:OD-001/002/003 原样复现;OD-004 恶化——
turn 直接 failed 且英文 agent 独白泄漏为可见回复(「Let me also search for…」,
独白剥离病复发形态)。详见 runs/promo_gate/promo_gate_20260731_r3/report.md。

### CLOSED

(暂无)

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
