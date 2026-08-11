# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_t4_verify_r3`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=79e21ed7a41e74ef138387d191c90678a92f5d5d
DEEPTUTOR_RELEASE_ID=1.0.0+79e21ed7a41e74ef138387d191c90678a92f5d5d+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:08:46  结束: 2026-07-31T02:10:47
- 结果: **2 PASS / 0 FAIL / 2 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |

## 逐场景证据摘录

### t4_q1_asis — PASS
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=`turn_1785434929507_03e3e5a6d5`; status=completed; latency=47761ms)
  - A0 **PASS** — turn status=completed; visible_len=3299(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3299 (>=300)
  - 回复摘录: 好，这道题题面较长，共5问。我先按你之前提交的作答继续批改，同时把后续各问的完整答案一起给你。  ---  ## 第1问：现浇混凝土安全事故类型还有哪些？安全控制主要内容还有哪些？  ### 你的答案  > 安全事故类型还有：高处坠落、物体打击、机械伤害、触电。 > 安全控制主要内容还有：模板拆除安全控制、泵送混凝土管路固定与作业安全、临边洞口防护。  ### 判分  **安全事故类型（满分3分）**  | 采分点 | 状态 | 得分 | |-------|------|:----:| | 高处坠落 | ✅ 命中 | 0.5 | | 物体打击 | ✅ 命中 | 0.5 | | 机械伤害 | ✅

### t4_q1_half — PASS
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785434981366_d2eec77060`; status=completed; latency=63161ms)
  - A0 **PASS** — turn status=completed; visible_len=5127(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['问题3', '问题4', '问题5']
  - A2 **PASS** — 得分对 [(0.84, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 3 个采分点，部分命中 0 个，还有 25 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 0.84 / 10 分。 **采分情况：** 命中 3 个，部分命中 0 个，漏/错 25 个。  **先看最该补的地方：** 1. 第1问：现浇混凝土安全事故类型还包括：脚手架失稳 2. 第1问：现浇混凝土安全事故类型还包括：重物吊装伤害 3. 第1问：现浇混凝土安全控制主要内容还包括：混凝土浇筑施工方案  提示

完整回复与 metadata 见 `evidence/<场景id>.md`。
