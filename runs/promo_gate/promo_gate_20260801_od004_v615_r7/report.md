# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_v615_r7`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=35ce8b226cf23997faf1974e4c798089bf514231
DEEPTUTOR_RELEASE_ID=1.0.0+35ce8b226cf23997faf1974e4c798089bf514231+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T03:30:08  结束: 2026-07-31T03:32:56
- 结果: **1 PASS / 0 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |

## 逐场景证据摘录

### t4_q1_half — PASS
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785439914642_627d3077bb`; status=completed; latency=60463ms)
  - A0 **PASS** — turn status=completed; visible_len=4587(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['问题3', '问题4', '问题5']
  - A2 **PASS** — 得分对 [(1.55, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 5 个采分点，部分命中 0 个，还有 21 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 1.55 / 10 分。 **采分情况：** 命中 5 个，部分命中 0 个，漏/错 21 个。  **先看最该补的地方：** 1. 第1问：现浇混凝土安全事故类型：脚手架失稳（或脚手架坍塌） 2. 第1问：现浇混凝土安全控制主要内容：模板支撑系统设计计算与搭设验收 3. 第1问：现浇混凝土安全控制主要内容：混凝土

完整回复与 metadata 见 `evidence/<场景id>.md`。
