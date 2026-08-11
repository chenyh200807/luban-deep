# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260731_r2`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=8d8bc5e42e778016413bbbb271ec4afcb7abb0e7
DEEPTUTOR_RELEASE_ID=1.0.0+8d8bc5e42e778016413bbbb271ec4afcb7abb0e7+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T00:20:14  结束: 2026-07-31T00:33:30
- 结果: **16 PASS / 5 FAIL / 21 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t1_full | 题库内案例(合同价款,qid=8817)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_half | 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_question_only | 题库内案例(qid=8817)·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t1_wrong | 题库内案例(qid=8817)·答错(数值与顺序均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_full | 题库内案例(2023质量检测,qid=17357)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_half | 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充) | **FAIL** | A1 | A0:PASS A1:FAIL A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_question_only | 题库内案例(qid=17357)·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t2_wrong | 题库内案例(qid=17357)·答错(不妥点判断全错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t3_full | 题库外长案例(2022案例一改写)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_half | 题库外长案例·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A1 | A0:PASS A1:FAIL A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_question_only | 题库外长案例·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t3_wrong | 题库外长案例·答错(等效龄期与评定结论均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t4_g1_asis | 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_g1_wrong | 历史事故原题·答错版(机具/顺序/结论均改错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |
| t5_correct | MCQ(qid=8731 氯离子复试)·答对并给理由 | **FAIL** | A0,M1,L1 | A0:FAIL A5:PASS M1:FAIL L1:FAIL |
| t5_question_only | MCQ(qid=8731)·只发题不作答(答题必有解析) | **PASS** | - | A0:PASS A5:PASS M1:PASS L1:PASS |
| t5_wrong | MCQ(qid=8731)·答错(选D河砂) | **PASS** | - | A0:PASS A5:PASS M1:PASS M2:PASS L1:PASS |
| t6_edge_ask | KB边界偏门题(金属幕墙板材/气密性)·只问 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t6_edge_full | KB边界偏门题·带自己的理解求核对 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |

## 逐场景证据摘录

### t1_full — PASS
- 题库内案例(合同价款,qid=8817)·全答(form=full; turn_id=`turn_1785428418208_3253514953`; status=completed; latency=41952ms)
  - A0 **PASS** — turn status=completed; visible_len=2916(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.36, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 2 个采分点，部分命中 0 个，还有 11 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1、问题2、问题3 命中了采分点参考（题面共 5 问）；问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 2.36 / 10 分。 **采分情况：** 命中 2 个，部分命中 0 个，漏

### t1_half — PASS
- 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785428464237_07eef862b5`; status=completed; latency=26663ms)
  - A0 **PASS** — turn status=completed; visible_len=1585(入口必须完成且回复非空)
  - A1 **PASS** — 命中「未纳入本次判分」
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 3

### t1_question_only — PASS
- 题库内案例(qid=8817)·只发题不作答(form=question_only; turn_id=`turn_1785428495237_16c64078d2`; status=completed; latency=38733ms)
  - A0 **PASS** — turn status=completed; visible_len=3438(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3438 (>=300)
  - 回复摘录: 这道题是典型的综合案例题，5问覆盖合同、造价、采购、劳动力、变更索赔5个模块。我按小问逐一拆。  ---  ## 第1问·合同签订不妥与文件解释顺序  **结论：** 两处不妥，合同文件解释顺序按9个层级递减排列。  ### 不妥之处  **不妥一：** 甲乙双方通过协商修改了合同协议书、专用条款、通用条款后签订施工合同。  **正确做法：** 待签合同应与招标文件、投标文件保持一致性（承包范围、工期、造价、计价方式、质量要求等实质性内容），否则合同无效且将被责令改正。  **不妥二：** 背景资料只列出了5个合同文件，但《建设工程施工合同（示范文本）》规定的解释顺序共9个层次，不应只列5个。

### t1_wrong — PASS
- 题库内案例(qid=8817)·答错(数值与顺序均错)(form=wrong; turn_id=`turn_1785428537947_6966ebd3c0`; status=completed; latency=21166ms)
  - A0 **PASS** — turn status=completed; visible_len=1585(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 3

### t2_full — PASS
- 题库内案例(2023质量检测,qid=17357)·全答(form=full; turn_id=`turn_1785428564712_01ce8ad674`; status=completed; latency=20636ms)
  - A0 **PASS** — turn status=completed; visible_len=1594(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(5.84, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 3 个采分点，部分命中 1 个，还有 1 个需要补。后面我按小问逐一拆。  **得分预估：** 5.84 / 10 分。 **采分情况：** 命中 3 个，部分命中 1 个，漏/错 1 个。  **先看最该补的地方：** 1. 第1问：正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，单独列支并按照合同约定及时支付。 2. 第1问：见证记录内容还包括：取样、制样、标识、封志、送检、现场检测。  提示：本评分为 AI 阅卷

### t2_half — FAIL
- 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充)(form=half; turn_id=`turn_1785428588323_9f945350e0`; status=completed; latency=22295ms)
  - A0 **PASS** — turn status=completed; visible_len=1374(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=['见证记录内容', '见证记录']
  - A2 **PASS** — 得分对 [(6.68, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 4 个采分点，部分命中 0 个，还有 1 个需要补。后面我按小问逐一拆。  **得分预估：** 6.68 / 10 分。 **采分情况：** 命中 4 个，部分命中 0 个，漏/错 1 个。  **先看最该补的地方：** 1. 第1问：见证记录内容还包括：取样、制样、标识、封志、送检、现场检测。  提示：本评分为 AI 阅卷草稿，非正式成绩。  ## 问题1：指出工程施工质量检测管理工作中的不妥之处，并写出正确做法。（本问题2项不妥，多答不

### t2_question_only — PASS
- 题库内案例(qid=17357)·只发题不作答(form=question_only; turn_id=`turn_1785428614763_5c2ff8cc0b`; status=completed; latency=13848ms)
  - A0 **PASS** — turn status=completed; visible_len=1082(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1082 (>=300)
  - 回复摘录: ## 结论  **第1问共2处不妥，见证记录还需补充6项内容。** 你写到的"试验员制作见证记录不妥"命中了第1处，但第2处（检测费用支付主体）和见证记录内容补充项需要补上。  ---  ## 问题1拆解  ### 不妥之处①  **不妥：** 试验员如实记录了其取样、现场检测等情况，制作了见证记录。  **正确做法：** 应由 ==见证人员==（监理工程师或建设单位人员）负责记录其取样、现场检测情况，制作见证记录。试验员是施工方人员，不能代替见证人填写见证记录。  ### 不妥之处②  **不妥：** 总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。  **正确做法：** 建设单

### t2_wrong — PASS
- 题库内案例(qid=17357)·答错(不妥点判断全错)(form=wrong; turn_id=`turn_1785428632851_d2aadfeb15`; status=completed; latency=22027ms)
  - A0 **PASS** — turn status=completed; visible_len=1571(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.67, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 0 个，还有 4 个需要补。后面我按小问逐一拆。  **得分预估：** 1.67 / 10 分。 **采分情况：** 命中 1 个，部分命中 0 个，漏/错 4 个。  **先看最该补的地方：** 1. 第1问：正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。 2. 第1问：指出不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。 3. 第1问：正确做法：建设单位应当在编制工程概预算时

### t3_full — PASS
- 题库外长案例(2022案例一改写)·全答(form=full; turn_id=`turn_1785428658876_87d0f057fa`; status=completed; latency=17762ms)
  - A0 **PASS** — turn status=completed; visible_len=803(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 4 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 4 个。  **先看最该补的地方：** 1. 焊接材料 2. 焊接方法 3. 焊接位置  提示：本评分为 AI 阅卷草稿，非正式成绩。  **采分点：** - ❌ 漏点：焊接材料（你的作答没有覆盖这个得分含义） - ❌ 漏点：焊接方法（你的作答没有覆盖这个得分含义） 

### t3_half — FAIL
- 题库外长案例·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785428680911_3a3658fab7`; status=completed; latency=26891ms)
  - A0 **PASS** — turn status=completed; visible_len=1370(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=[]
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 10 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 10 个。  **先看最该补的地方：** 1. A: 限制 2. B: 禁止 3. C: 不得用于25米及以上的建设工程  提示：本评分为 AI 阅卷草稿，非正式成绩。  **采分点：** - ❌ 术语不精确：A: 限制（术语不精确：本采分点要求规范术语，近义/口语

### t3_question_only — PASS
- 题库外长案例·只发题不作答(form=question_only; turn_id=`turn_1785428711966_17e7212c7f`; status=completed; latency=116532ms)
  - A0 **PASS** — turn status=completed; visible_len=708(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=708 (>=300)
  - 回复摘录: ### 阅卷结论 你的答案“错”未按问题要求填写具体信息，本题判定为不得分。诊断类型为“答题不规范”——你没有针对问题1-4中的任何一问写出具体内容，因此无法获得任何采分点。  ### 正确答案 问题1：A—限制；B—禁止；C—不得用于25米及以上的建设工程；D—普通钢筋调直机、数控钢筋调直切断机的钢筋调直工艺；E—人货两用施工升降机；F—LED灯、节能灯等；G—LED灯、节能灯等。 问题2：1F柱等效龄期19d，累计气温611℃·d；2F柱等效龄期18d，累计气温600.5℃·d；3F柱等效龄期18d，累计气温616.5℃·d。 问题3：两种方法为统计方法（标准差已知/未知）和非统计方法。1

### t3_wrong — PASS
- 题库外长案例·答错(等效龄期与评定结论均错)(form=wrong; turn_id=`turn_1785428832711_c38d0b14b6`; status=completed; latency=33995ms)
  - A0 **PASS** — turn status=completed; visible_len=1502(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 14 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 14 个。  **先看最该补的地方：** 1. A: 限制 2. B: 禁止 3. C: 不得用于25米及以上的建设工程  提示：本评分为 AI 阅卷草稿，非正式成绩。  **采分点：** - ❌ 术语不精确：A: 限制（术语不精确：本采分点要求规范术语，近义/口语

### t4_g1_asis — PASS
- 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答)(form=full; turn_id=`turn_1785428871090_db868bd691`; status=completed; latency=43666ms)
  - A0 **PASS** — turn status=completed; visible_len=3137(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(9.11, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段带出处
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 4 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 18 个采分点，部分命中 0 个，还有 1 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 9.11 / 10 分。 **采分情况：** 命中 18 个，部分命中 0 个，漏/错 1 个。  **先看最该补的地方：** 1. 第2问：混凝土浇筑施工机具使用先后顺序为：A-B-C-D-E  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ## 问题1：答出图1中B~F处的施

### t4_g1_wrong — PASS
- 历史事故原题·答错版(机具/顺序/结论均改错)(form=wrong; turn_id=`turn_1785428918837_7d55b4f24f`; status=completed; latency=58917ms)
  - A0 **PASS** — turn status=completed; visible_len=4087(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.92, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 2 个，还有 17 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 0.92 / 10 分。 **采分情况：** 命中 1 个，部分命中 2 个，漏/错 17 个。  **先看最该补的地方：** 1. 第1问：C: 布料机 2. 第1问：D: 串筒 3. 第1问：E: 振捣棒（或插入式振捣器）  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ##

### t4_q1_asis — FAIL
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=`turn_1785428981675_6b82e8e10d`; status=failed; latency=50452ms)
  - A0 **FAIL** — turn status=failed; visible_len=27(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=27 (>=300)
  - 回复摘录: 这次模型没有返回可见答案，已记录问题。请重新发送一次。

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785429036299_8cbf25bd79`; status=completed; latency=62110ms)
  - A0 **PASS** — turn status=completed; visible_len=3535(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['未作答', '未答'] + 点名漏点['第3问', '第4问', '第5问']
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority=''; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这是一道综合案例题，你答了第1、2问，其余小问标注了"按规范补充"。下面我按5个小问逐一拆解，把你已答的部分一起判。  ---  ## 问题1：现浇混凝土安全事故类型还有哪些？安全控制主要内容还有哪些？  **你写的：** 类型：高处坠落、物体打击、机械伤害、触电。安全控制主要内容：模板拆除安全控制、泵送混凝土管路固定与作业安全、临边洞口防护。  **判定：** 部分命中，漏了关键点。  ### 采分点  **安全事故类型（还有哪些）：** - ✅ 高处坠落（你写了） - ✅ 物体打击（你写了） - ✅ 机械伤害（你写了） - ✅ 触电（你写了） - ❌ **脚手架失稳**（漏了） - ❌ *

### t5_correct — FAIL
- MCQ(qid=8731 氯离子复试)·答对并给理由(form=full; turn_id=`turn_1785429102506_33470f7d82`; status=ws_timeout; latency=10694ms)
  - A0 **FAIL** — turn status=ws_timeout; visible_len=0(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **FAIL** — contains_all['外加剂'] 缺 ['外加剂']
  - L1 **FAIL** — len=0 (>=60)
  - 回复摘录: 

### t5_question_only — PASS
- MCQ(qid=8731)·只发题不作答(答题必有解析)(form=question_only; turn_id=`turn_1785429113611_175923526d`; status=completed; latency=17715ms)
  - A0 **PASS** — turn status=completed; visible_len=564(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - L1 **PASS** — len=564 (>=60)
  - 回复摘录: ## 📊 阅卷结论 这道题已命中题库原题。标准答案：B（B. 外加剂）。本题核心是先锁定题库给出的标准选项，再围绕原解析理解判断依据。  ## 🧐 解析 外加剂中常含有氯盐，是氯离子的主要来源，因此在有氯离子限制时，应首先检测外加剂的氯离子含量。粉煤灰、碎石、河砂也可能含氯，但通常含量较低，且规范要求优先检测外加剂。故选B。  ## ⚠️ 易错点 | 易错项 | 题库依据 | | :--- | :--- | | A. 粉煤灰 | 粉煤灰作为矿物掺合料，其氯离子含量通常较低，不是氯离子的主要或首要来源。 [概念混淆] | | C. 碎石 | 碎石作为粗骨料，其氯离子含量通常极低，且不易溶出，不是

### t5_wrong — PASS
- MCQ(qid=8731)·答错(选D河砂)(form=wrong; turn_id=`turn_1785429131230_97727a91c9`; status=completed; latency=33521ms)
  - A0 **PASS** — turn status=completed; visible_len=1022(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - M2 **PASS** — contains_any['不正确', '不对', '错误', '误选', '不是', '并非'] 命中 ['错误', '不是']
  - L1 **PASS** — len=1022 (>=60)
  - 回复摘录: ### 阅卷结论 你答了D（河砂），正确答案是B（外加剂）。判定为错误，诊断类型：概念混淆——误将“用量大”等同于“氯离子首要来源”。  ### 正确答案 **B. 外加剂** 外加剂（尤其是早强剂、防冻剂等）常含有氯盐，是混凝土中氯离子的主要来源，规范要求在有氯离子含量限制时优先检验。  ### 为什么错 你的推理“河砂用量最大，氯离子总量贡献最大”是典型的**概念混淆**。混凝土中氯离子的首要来源不是用量最大的骨料，而是外加剂中的氯盐成分（如氯盐类早强剂、防冻剂）。河砂虽可能含氯（如海砂），但通常含量较低，且规范明确要求优先检验外加剂。你忽略了外加剂作为“活性组分”的特殊性，用“总量”思维

### t6_edge_ask — PASS
- KB边界偏门题(金属幕墙板材/气密性)·只问(form=question_only; turn_id=`turn_1785429165201_53161ee607`; status=completed; latency=17149ms)
  - A0 **PASS** — turn status=completed; visible_len=1293(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1293 (>=150)
  - 回复摘录: ## 结论  1. **金属幕墙常用板材**：铝板（含铝塑复合板、铝蜂窝复合板）、不锈钢板、搪瓷钢板、锌合金板、钛合金板等。 2. **铝塑复合板现场加工讲究**：核心是**严禁现场开槽**，必须工厂预制加工；现场只能做切割、折边等不破坏面板结构的工序。 3. **幕墙气密性能**：**是必须检测的项目**，属于幕墙工程交工前"四性"检测之一。  ---  ## 判断依据  ### 一、金属幕墙常用板材  教材《建筑工程管理与实务》将金属幕墙板材分为两类：  - **金属板幕墙**：铝板、不锈钢板、搪瓷钢板、锌合金板、钛合金板等 - **金属复合板幕墙**：铝塑复合板、铝蜂窝复合板、钛锌复合板

### t6_edge_full — PASS
- KB边界偏门题·带自己的理解求核对(form=full; turn_id=`turn_1785429182499_ea70a70c71`; status=completed; latency=29336ms)
  - A0 **PASS** — turn status=completed; visible_len=1236(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1236 (>=150)
  - 回复摘录: 检索证据已覆盖三个问题。下面逐一核对你说的。  ---  ## 结论  你的理解**基本正确，但不全面**。金属幕墙板材你漏了锌合金板、钛合金板、搪瓷钢板三大类；气密性能的理解方向对，但幕墙工程检测的是"四性"而非"三性"。  ---  ## 一、金属幕墙常用板材  检索证据显示，教材口径分两类：  **金属板幕墙**（单一金属板）：铝板、不锈钢板、搪瓷钢板、锌合金板、钛合金板等。  **金属复合板幕墙**（复合构造）：铝塑复合板、铝蜂窝复合板、钛锌复合板等。  ✅ 你说的单层铝板、铝塑复合板、蜂窝铝板、不锈钢板都正确。 ❌ 漏了：**搪瓷钢板、锌合金板、钛合金板、钛锌复合板**。  > 考试

完整回复与 metadata 见 `evidence/<场景id>.md`。
