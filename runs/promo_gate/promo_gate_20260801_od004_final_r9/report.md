# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_final_r9`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=edc52b5ead795ef658ad754271ca6ab20e4fa566
DEEPTUTOR_RELEASE_ID=1.0.0+edc52b5ead795ef658ad754271ca6ab20e4fa566+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T03:03:07  结束: 2026-07-31T03:03:57
- 结果: **0 PASS / 1 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |

## 逐场景证据摘录

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785438192426_cfd0e8e35d`; status=completed; latency=42412ms)
  - A0 **PASS** — turn status=completed; visible_len=2468(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['未作答', '漏点'] + 点名漏点['第3问', '第4问', '第5问']
  - A2 **PASS** — 得分对 [(3.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority='v1_unavailable:no_reference'; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。我注意到你提交了这道案例题的作答，但部分小问（第3、4、5问）只写了"按规范补充"没有实际作答。我先按你已写的内容进行批改，未作答部分会给你答题框架。  ---  ## 评分口径  本次按采分点推演阅卷（依据题干背景、标准答案逻辑和考点推演）。  ## 预计得分  **约 3.0 / 10 分**（第1问约 2.0/3.0，第2问约 1.0/2.0，第3~5问未作答，每问约 0/1.5~2.0）  ---  ## 第1问：现浇混凝土安全事故类型 + 安全控制主要内容（约 3.0 分）  ##

完整回复与 metadata 见 `evidence/<场景id>.md`。
