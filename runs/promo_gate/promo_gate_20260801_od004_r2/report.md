# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_r2`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=1b91d70b9780ec7a6186d303586a91bb513a3155
DEEPTUTOR_RELEASE_ID=1.0.0+1b91d70b9780ec7a6186d303586a91bb513a3155+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:29:51  结束: 2026-07-31T02:30:32
- 结果: **1 PASS / 0 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |

## 逐场景证据摘录

### t4_q1_half — PASS
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785436193769_aa344f5f23`; status=completed; latency=36142ms)
  - A0 **PASS** — turn status=completed; visible_len=5237(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['问题3', '问题4', '问题5']
  - A2 **PASS** — 得分对 [(1.93, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 8 个采分点，部分命中 2 个，还有 26 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 1.93 / 10 分。 **采分情况：** 命中 8 个，部分命中 2 个，漏/错 26 个。  **先看最该补的地方：** 1. 第1问：现浇混凝土安全控制主要内容还包括：模板支撑系统搭设与拆除的安全技术措施 2. 第1问：现浇混凝土安全控制主要内容还包括：混凝土浇筑过程的安全控制（如防止侧压力过大、模板倒塌）

完整回复与 metadata 见 `evidence/<场景id>.md`。
