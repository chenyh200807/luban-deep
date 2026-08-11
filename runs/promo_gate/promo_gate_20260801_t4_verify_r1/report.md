# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_t4_verify_r1`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=79e21ed7a41e74ef138387d191c90678a92f5d5d
DEEPTUTOR_RELEASE_ID=1.0.0+79e21ed7a41e74ef138387d191c90678a92f5d5d+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:04:22  结束: 2026-07-31T02:06:48
- 结果: **2 PASS / 0 FAIL / 2 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |

## 逐场景证据摘录

### t4_q1_asis — PASS
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=`turn_1785434666908_55707c5656`; status=completed; latency=79630ms)
  - A0 **PASS** — turn status=completed; visible_len=3278(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3278 (>=300)
  - 回复摘录: ## 结论  这道题需要逐问拆解。我先按顺序给出完整作答框架和采分点。  ---  ## 问题1：现浇混凝土安全事故类型还有哪些？现浇混凝土安全控制主要内容还有哪些？  **结论：** 安全事故类型还有高空坠落、物体打击、触电、机械伤害、脚手架失稳、重物吊装。安全控制主要内容还有模板支撑系统设计、模板施工、混凝土浇筑用电安全、混凝土浇筑施工、混凝土浇筑用电安全、模板拆除施工安全。  **判断依据：**  **安全事故类型（补充）：** - 高空坠落 - 物体打击 - 触电 - 机械伤害 - 脚手架失稳 - 重物吊装  **安全控制主要内容（补充）：** - 模板支撑系统设计 - 模板施工（安装

### t4_q1_half — PASS
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785434750064_ae7a0f41bc`; status=completed; latency=55384ms)
  - A0 **PASS** — turn status=completed; visible_len=4436(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['问题3', '问题4', '问题5']
  - A2 **PASS** — 得分对 [(2.55, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 3 个，还有 10 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 2.55 / 10 分。 **采分情况：** 命中 1 个，部分命中 3 个，漏/错 10 个。  **先看最该补的地方：** 1. 第1问：现浇混凝土安全控制主要内容还包括：模板支撑系统搭设与拆除的安全控制、混凝土浇筑与振捣的安全控制、作业人员的安全防护、混凝土输送设备的安全使用 2. 第2问：机械设备选择的依据

完整回复与 metadata 见 `evidence/<场景id>.md`。
