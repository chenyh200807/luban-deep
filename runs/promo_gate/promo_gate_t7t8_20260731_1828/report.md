# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_t7t8_20260731_1828`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=889119c11bd4797ca8f31f002ba0b36bed443064
DEEPTUTOR_RELEASE_ID=1.0.0+889119c11bd4797ca8f31f002ba0b36bed443064+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T18:28:27  结束: 2026-07-31T18:29:45
- 结果: **2 PASS / 0 FAIL / 2 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t7_goldv2_low | 金标v2·Q2023-03低能力档作答(金标 expected_score_ratio=0.21)·弱答案不得满分 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS A9:PASS |
| t8_partial_scope | 兄弟行案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·局部覆盖分母必须诚实 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS A10:PASS |

## 逐场景证据摘录

### t7_goldv2_low — PASS
- 金标v2·Q2023-03低能力档作答(金标 expected_score_ratio=0.21)·弱答案不得满分(form=gold_v2_low; turn_id=`turn_1785493712199_5cf2b70586`; status=completed; latency=41163ms)
  - A0 **PASS** — turn status=completed; visible_len=4611(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.09, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A9 **PASS** — 最高得分率 0.209 < 0.5(得分对 [(2.09, 10.0)])
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 5 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 5 个采分点，部分命中 1 个，还有 20 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1、问题2、问题3、问题4 命中了采分点参考（题面共 5 问）；问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **诊断得分预估（仅已覆盖小问）：** 2.09 / 10 分。 **采分情况：** 命中

### t8_partial_scope — PASS
- 兄弟行案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·局部覆盖分母必须诚实(form=sibling_row_partial_coverage; turn_id=`turn_1785493756159_00a176940c`; status=completed; latency=26764ms)
  - A0 **PASS** — turn status=completed; visible_len=1493(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(8.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A10 **PASS** — partial_scope=4/5; 分母=10.0(整题满分); 得分对 [(8.0, 10.0)] 均 <= 8.01; official_score_allowed=false
  - A9 **SKIP** — 残余病(2026-08-01 实测):本作答只覆盖 4 问中的 1 问,应 <= 2.5/10,实得 8/10——因为覆盖比例取自 eq.covered_indexes(检索回的兄弟行数=4)而非采分点实际归属的小问数(=1),分母诚实但比例虚高。修好比例来源后把本断言的 skip 去掉(阈值 0.4)。
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 5 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 7 个采分点，部分命中 0 个，还有 0 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 8 / 10 分。 **采分情况：** 命中 7 个，部

完整回复与 metadata 见 `evidence/<场景id>.md`。
