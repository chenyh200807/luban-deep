# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_final_r7`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=edc52b5ead795ef658ad754271ca6ab20e4fa566
DEEPTUTOR_RELEASE_ID=1.0.0+edc52b5ead795ef658ad754271ca6ab20e4fa566+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:57:54  结束: 2026-07-31T02:58:46
- 结果: **0 PASS / 1 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |

## 逐场景证据摘录

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785437876971_f4342317a1`; status=completed; latency=46729ms)
  - A0 **PASS** — turn status=completed; visible_len=3059(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点'] + 点名漏点['第3问', '第4问', '第5问']
  - A2 **PASS** — 得分对 [(2.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority='v1_unavailable:no_reference'; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。我先整体看一下你的作答，再逐问拆采分点。  ---  ## 整体判断  **诊断得分预估：** 约 2.5 / 10 分（按采分点推演，非正式阅卷成绩）  **你的主要问题：** - 第1问：安全事故类型漏了最关键的"模板支撑系统整体坍塌"——题干背景已经给了，你没用上 - 第2问：依据和原则混在一起写，且漏了"可靠性"原则 - 第3问：完全没作答，丢分最多 - 第4、5问：也没写  **先看最该补的地方：** 第3问是计算题+改错题，分值最重，你直接空着，这是最亏的。  ---  ## 第

完整回复与 metadata 见 `evidence/<场景id>.md`。
