# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_t3_od001_verify`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=b039ae8d168efed6dcbaffd130617eeacb207d4c
DEEPTUTOR_RELEASE_ID=1.0.0+b039ae8d168efed6dcbaffd130617eeacb207d4c+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T01:12:51  结束: 2026-07-31T01:16:32
- 结果: **4 PASS / 0 FAIL / 4 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t3_full | 题库外长案例(2022案例一改写)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_half | 题库外长案例·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_question_only | 题库外长案例·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t3_wrong | 题库外长案例·答错(等效龄期与评定结论均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |

## 逐场景证据摘录

### t3_full — PASS
- 题库外长案例(2022案例一改写)·全答(form=full; turn_id=`turn_1785431575459_a7aef36c0a`; status=completed; latency=79580ms)
  - A0 **PASS** — turn status=completed; visible_len=3643(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(10.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段带出处
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 25 个采分点，部分命中 0 个，还有 0 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 10 / 10 分。 **采分情况：** 命中 25 个，部分命中 0 个，漏/错 0 个。  **先看结论：** 主要采分点覆盖不错，后面重点看表达优化和易错点。  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ## 问题1：补充表1中A~G处的信息内容。 **你写的：** 能

### t3_half — PASS
- 题库外长案例·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785431658595_b0372761f3`; status=completed; latency=46661ms)
  - A0 **PASS** — turn status=completed; visible_len=3261(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['第3问', '问题3', '问题4']
  - A2 **PASS** — 得分对 [(5.85, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 13 个采分点，部分命中 0 个，还有 6 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 5.85 / 10 分。 **采分情况：** 命中 13 个，部分命中 0 个，漏/错 6 个。  **先看最该补的地方：** 1. 第3问：两种混凝土强度检验评定方法为：统计方法评定和非统计方法评定 2. 第3问：1F~3F柱C40混凝土实体强度评定不合格 3. 第3问：评定理由：1F柱实体强度38.5N/mm²

### t3_question_only — PASS
- 题库外长案例·只发题不作答(form=question_only; turn_id=`turn_1785431709551_4d04d7f932`; status=completed; latency=26005ms)
  - A0 **PASS** — turn status=completed; visible_len=1498(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1498 (>=300)
  - 回复摘录: ### 阅卷结论 你答错了这道题。系统诊断为“INVALID”，但基于题目内容和检索依据裁决，你未能正确补充表1中A~G的信息。诊断类型为：记忆偏差与概念混淆。  ### 正确答案 依据检索依据中的标准答案，表1中A~G的正确信息应为： A: 限制 B: 禁止 C: 不得用于25米及以上的建设工程 D: 普通钢筋调直机、数控钢筋调直切断机的钢筋调直工艺 E: 人货两用施工升降机 F: LED灯、节能灯等 G: 不得用于建设工地的生产、办公、生活等区域的照明  ### 为什么错 你本题的作答格式混乱，不是对A~G的逐一补充，而是直接写了“错”，这表明你未能识别出这是需要填空的题目，属于审题遗漏。

### t3_wrong — PASS
- 题库外长案例·答错(等效龄期与评定结论均错)(form=wrong; turn_id=`turn_1785431739394_fb82513f2b`; status=completed; latency=49892ms)
  - A0 **PASS** — turn status=completed; visible_len=3806(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.52, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 4 个采分点，部分命中 0 个，还有 20 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 1.52 / 10 分。 **采分情况：** 命中 4 个，部分命中 0 个，漏/错 20 个。  **先看最该补的地方：** 1. 第1问：E处应为“钢筋调直机调直工艺”或“机械调直工艺” 2. 第1问：F处应为“施工升降机”或“人货两用电梯” 3. 第1问：G处应为“LED灯”或“节能灯”或“其他高效照明灯具”

完整回复与 metadata 见 `evidence/<场景id>.md`。
