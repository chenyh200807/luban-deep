# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_final_r4`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=edc52b5ead795ef658ad754271ca6ab20e4fa566
DEEPTUTOR_RELEASE_ID=1.0.0+edc52b5ead795ef658ad754271ca6ab20e4fa566+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:54:51  结束: 2026-07-31T02:55:51
- 结果: **0 PASS / 1 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |

## 逐场景证据摘录

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785437695430_db7cd2206c`; status=completed; latency=53478ms)
  - A0 **PASS** — turn status=completed; visible_len=3518(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['未作答', '漏点'] + 点名漏点['临时用水', '厕所', '浴室']
  - A2 **PASS** — 得分对 [(3.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority='v1_unavailable:no_reference'; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。# 批改结果  ## 评分口径  本次按采分点推演阅卷（从题面标准答案与教材考点投影）。  **诊断得分预估：** 3.5 / 10 分（按各小问分值加权估算，非正式阅卷成绩）  ---  ## 第 1 问 · 现浇混凝土安全事故类型 & 安全控制主要内容（预估 2.5 分）  ### 你写的 - 安全事故类型：高处坠落、物体打击、机械伤害、触电 - 安全控制主要内容：模板拆除安全控制、泵送混凝土管路固定与作业安全、临边洞口防护  ### 判定  **安全事故类型：** 部分命中  | 采分

完整回复与 metadata 见 `evidence/<场景id>.md`。
