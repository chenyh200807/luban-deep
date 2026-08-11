# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_r5_calib`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=c53a5d8a5ba3d6f74efa11e7732447ab514db5e3
DEEPTUTOR_RELEASE_ID=1.0.0+c53a5d8a5ba3d6f74efa11e7732447ab514db5e3+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-08-01T07:02:43  结束: 2026-08-01T07:03:47
- 结果: **2 PASS / 0 FAIL / 2 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t8_group_bundle_half | 治理组整卷案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·半答必须封顶 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS T8_BUNDLE:PASS T8_PERSUBQ:PASS T8_CAP:PASS |
| t9_full_paper_full_answer | 金标v2·Q2023-03高能力档整卷全答(金标 expected_score_ratio=0.84)·全答不得被封顶误伤 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS A7:PASS T9_PERSUBQ:PASS T9_FLOOR:PASS |

## 逐场景证据摘录

### t8_group_bundle_half — PASS
- 治理组整卷案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·半答必须封顶(form=group_bundle_half_answer; turn_id=`turn_1785538967747_40ec01b722`; status=completed; latency=28752ms)
  - A0 **PASS** — turn status=completed; visible_len=3322(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - T8_BUNDLE **PASS** — case_bundle_source='group_query' 全等期望值
  - T8_PERSUBQ **PASS** — case_per_subq_grading='4/4' 全等期望值
  - T8_CAP **PASS** — 最高得分 2.5 <= 封顶 3.0(分母=10.0 得分对 [(2.5, 10.0)])
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 2 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 26 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 8 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t9_full_paper_full_answer — PASS
- 金标v2·Q2023-03高能力档整卷全答(金标 expected_score_ratio=0.84)·全答不得被封顶误伤(form=gold_v2_high_full_paper; turn_id=`turn_1785539000011_ac639188c9`; status=completed; latency=24844ms)
  - A0 **PASS** — turn status=completed; visible_len=1516(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(9.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - T9_PERSUBQ **PASS** — case_per_subq_grading='4/4' 在场且非空
  - T9_FLOOR **PASS** — 最高得分 9.0 >= 下限 6.0(分母=10.0 得分对 [(9.0, 10.0)])
  - 回复摘录: 这道题你之前已经答过一次，得了9分，这次是重新作答。我直接按你这次的答案重新批改。  ## 批改结论  **得分预估：** 9 / 10 分 **采分情况：** 命中23个，部分命中1个，漏/错2个  **最该补的2个点：** 1. 第2问：抽检数量不应少于总桩数的 **20%**，不是10% 2. 第2问：抽检数量不应少于 **10根**，不是5根  ---  ## 第1问：工程质量计划编制和管理 + 质量控制点  **判定：** 全部命中，7/7 采分点  **采分点明细：** - ✅ 指出"开工后编制"不妥 - ✅ 正确做法：应在项目策划过程中编制 - ✅ 指出"静态管理"不妥 - ✅ 

完整回复与 metadata 见 `evidence/<场景id>.md`。
