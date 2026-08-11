# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_r3`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=1b91d70b9780ec7a6186d303586a91bb513a3155
DEEPTUTOR_RELEASE_ID=1.0.0+1b91d70b9780ec7a6186d303586a91bb513a3155+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:30:33  结束: 2026-07-31T02:31:13
- 结果: **0 PASS / 1 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |

## 逐场景证据摘录

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785436237390_b40d96324e`; status=completed; latency=33350ms)
  - A0 **PASS** — turn status=completed; visible_len=1706(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉'] + 点名漏点['第3问']
  - A2 **PASS** — 得分对 [(2.5, 4.0), (1.5, 3.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority='v1_unavailable:no_reference'; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。好的，我看到你的作答了。这是一道综合案例题，我先按小问逐一阅卷。题目较长，我先给你第1问和第2问的批改，再继续第3~5问。  ---  ## 第1问：现浇混凝土安全事故类型 & 安全控制主要内容  ### 评分口径 本次按采分点推演阅卷（从标准答案和考点解析投影）。  ### 预计得分 **2.5 / 4 分**  ### 命中的采分点  **安全事故类型（你写了4个，应得满分）** - ✅ **高处坠落** — 命中 - ✅ **物体打击** — 命中 - ✅ **机械伤害** — 命中 

完整回复与 metadata 见 `evidence/<场景id>.md`。
