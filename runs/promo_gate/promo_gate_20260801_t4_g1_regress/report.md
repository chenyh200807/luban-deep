# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_t4_g1_regress`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=79e21ed7a41e74ef138387d191c90678a92f5d5d
DEEPTUTOR_RELEASE_ID=1.0.0+79e21ed7a41e74ef138387d191c90678a92f5d5d+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T02:11:59  结束: 2026-07-31T02:13:59
- 结果: **2 PASS / 0 FAIL / 2 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_g1_asis | 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_g1_wrong | 历史事故原题·答错版(机具/顺序/结论均改错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |

## 逐场景证据摘录

### t4_g1_asis — PASS
- 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答)(form=full; turn_id=`turn_1785435122692_1965349f91`; status=completed; latency=55458ms)
  - A0 **PASS** — turn status=completed; visible_len=3099(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(8.95, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段带出处
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 18 个采分点，部分命中 0 个，还有 1 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 8.95 / 10 分。 **采分情况：** 命中 18 个，部分命中 0 个，漏/错 1 个。  **先看最该补的地方：** 1. 第2问：混凝土浇筑施工机具使用先后顺序为：A-B-C-D-E  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ## 问题1：答出图1中B~F处的施

### t4_g1_wrong — PASS
- 历史事故原题·答错版(机具/顺序/结论均改错)(form=wrong; turn_id=`turn_1785435182936_53c2fc67e8`; status=completed; latency=55148ms)
  - A0 **PASS** — turn status=completed; visible_len=3812(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.06, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 3 个，还有 14 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 1.06 / 10 分。 **采分情况：** 命中 1 个，部分命中 3 个，漏/错 14 个。  **先看最该补的地方：** 1. 第1问：C 为布料机 2. 第1问：D 为串筒 3. 第1问：E 为振捣棒（或插入式振捣器）  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ##

完整回复与 metadata 见 `evidence/<场景id>.md`。
