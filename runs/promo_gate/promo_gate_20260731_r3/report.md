# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260731_r3`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=d1c2b44a2cc711a300a299607163ce395a14fc9e
DEEPTUTOR_RELEASE_ID=1.0.0+d1c2b44a2cc711a300a299607163ce395a14fc9e+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T00:40:42  结束: 2026-07-31T00:52:21
- 结果: **18 PASS / 3 FAIL / 21 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t1_full | 题库内案例(合同价款,qid=8817)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_half | 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_question_only | 题库内案例(qid=8817)·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t1_wrong | 题库内案例(qid=8817)·答错(数值与顺序均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_full | 题库内案例(2023质量检测,qid=17357)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_half | 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_question_only | 题库内案例(qid=17357)·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t2_wrong | 题库内案例(qid=17357)·答错(不妥点判断全错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t3_full | 题库外长案例(2022案例一改写)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_half | 题库外长案例·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A1 | A0:PASS A1:FAIL A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_question_only | 题库外长案例·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t3_wrong | 题库外长案例·答错(等效龄期与评定结论均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t4_g1_asis | 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_g1_wrong | 历史事故原题·答错版(机具/顺序/结论均改错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A0,A1,A6 | A0:FAIL A1:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |
| t5_correct | MCQ(qid=8731 氯离子复试)·答对并给理由 | **PASS** | - | A0:PASS A5:PASS M1:PASS L1:PASS |
| t5_question_only | MCQ(qid=8731)·只发题不作答(答题必有解析) | **PASS** | - | A0:PASS A5:PASS M1:PASS L1:PASS |
| t5_wrong | MCQ(qid=8731)·答错(选D河砂) | **PASS** | - | A0:PASS A5:PASS M1:PASS M2:PASS L1:PASS |
| t6_edge_ask | KB边界偏门题(金属幕墙板材/气密性)·只问 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t6_edge_full | KB边界偏门题·带自己的理解求核对 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |

## 逐场景证据摘录

### t1_full — PASS
- 题库内案例(合同价款,qid=8817)·全答(form=full; turn_id=`turn_1785429645488_71220323d0`; status=completed; latency=38513ms)
  - A0 **PASS** — turn status=completed; visible_len=3005(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.22, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 2 个采分点，部分命中 0 个，还有 12 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1、问题2、问题3 命中了采分点参考（题面共 5 问）；问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 2.22 / 10 分。 **采分情况：** 命中 2 个，部分命中 0 个，漏

### t1_half — PASS
- 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785429687786_0ae121ad9d`; status=completed; latency=26647ms)
  - A0 **PASS** — turn status=completed; visible_len=1923(入口必须完成且回复非空)
  - A1 **PASS** — 命中「未纳入本次判分」
  - A2 **PASS** — 得分对 [(2.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 0 个，还有 2 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 2.5 / 10 分。 **采分情况：** 命中 1 个，部分命中 0 个，漏/错

### t1_question_only — PASS
- 题库内案例(qid=8817)·只发题不作答(form=question_only; turn_id=`turn_1785429718660_37ec7ac9a7`; status=completed; latency=44685ms)
  - A0 **PASS** — turn status=completed; visible_len=3483(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3483 (>=300)
  - 回复摘录: 这道题是典型的综合案例，5 个小问覆盖合同、造价、采购、劳动力、变更索赔五大模块。下面按小问逐一拆解。  ---  ## 问题 1 · 合同签订不妥之处与文件解释顺序  ### 结论  **不妥之处：** 甲乙双方通过协商对合同协议书、专用条款、通用条款修改意见达成一致后签订了施工合同。  **正确做法：** 招标工程的合同价格、内容、范围、工期、质量等实质性内容，应与招标文件、投标文件保持一致，不得通过协商修改实质性内容。  **5 个合同文件解释优先顺序（递减）：** 合同协议书 → 中标通知书 → 投标函 → 专用合同条款 → 通用合同条款。  ### 判断依据  - 招标工程签订合同时

### t1_wrong — PASS
- 题库内案例(qid=8817)·答错(数值与顺序均错)(form=wrong; turn_id=`turn_1785429767462_ec606b5fe5`; status=completed; latency=23439ms)
  - A0 **PASS** — turn status=completed; visible_len=1705(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 3

### t2_full — PASS
- 题库内案例(2023质量检测,qid=17357)·全答(form=full; turn_id=`turn_1785429795649_6d4131affb`; status=completed; latency=21105ms)
  - A0 **PASS** — turn status=completed; visible_len=1597(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(6.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 3 个采分点，部分命中 0 个，还有 2 个需要补。后面我按小问逐一拆。  **得分预估：** 6 / 10 分。 **采分情况：** 命中 3 个，部分命中 0 个，漏/错 2 个。  **先看最该补的地方：** 1. 第1问：正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，单独列支并按照合同约定及时支付。 2. 第1问：见证记录内容还包括：取样、制样、标识、封志、送检、现场检测。  提示：本评分为 AI 阅卷草稿，

### t2_half — PASS
- 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充)(form=half; turn_id=`turn_1785429820171_f7b9572b3d`; status=completed; latency=30573ms)
  - A0 **PASS** — turn status=completed; visible_len=2406(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['见证记录内容', '见证记录']
  - A2 **PASS** — 得分对 [(2.4, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 3 个采分点，部分命中 0 个，还有 14 个需要补。后面我按小问逐一拆。  **得分预估：** 2.4 / 10 分。 **采分情况：** 命中 3 个，部分命中 0 个，漏/错 14 个。  **先看最该补的地方：** 1. 第1问：正确做法：建设单位应在编制工程概预算时合理核算检测费用，单独列支并按合同约定及时支付。 2. 第1问：见证记录内容还应包括：取样、制样、标识、封志、送检、现场检测。 3. 第2问：图1-1为麻面  提示：本

### t2_question_only — PASS
- 题库内案例(qid=17357)·只发题不作答(form=question_only; turn_id=`turn_1785429855027_ecc63fa180`; status=completed; latency=21378ms)
  - A0 **PASS** — turn status=completed; visible_len=935(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=935 (>=300)
  - 回复摘录: ## 结论  本题第1问共查找出 **2项不妥**，见证记录补充内容 **6项**。你的现有作答已命中部分采分点，但第1项不妥的责任主体判断有偏差，费用支付正确做法表述不完整。  ---  ## 第1问：不妥之处及正确做法  ### 不妥一  **试验员制作见证记录**  - **判定：** 见证记录应由见证人员（监理工程师或建设单位派驻的见证人员）制作，试验员是送检执行人，不是见证人。 - **正确做法：** 由见证人员（监理工程师）记录其取样、制样、标识、封志、送检、现场检测等情况，制作见证记录。  ### 不妥二  **总包项目部每月向检测机构支付检测费用**  - **判定：** 检测

### t2_wrong — PASS
- 题库内案例(qid=17357)·答错(不妥点判断全错)(form=wrong; turn_id=`turn_1785429880428_0114b3ef42`; status=completed; latency=31488ms)
  - A0 **PASS** — turn status=completed; visible_len=2312(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(3.89, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 4 个采分点，部分命中 0 个，还有 13 个需要补。后面我按小问逐一拆。  **得分预估：** 3.89 / 10 分。 **采分情况：** 命中 4 个，部分命中 0 个，漏/错 13 个。  **先看最该补的地方：** 1. 第1问：不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。 2. 第2问：图1-1为麻面 3. 第2问：图1-2为裂缝  提示：本轮含高风险判分点，建议教师复核后作为正式成绩。  ## 问题1：指

### t3_full — PASS
- 题库外长案例(2022案例一改写)·全答(form=full; turn_id=`turn_1785429916018_cfe35a2728`; status=completed; latency=17848ms)
  - A0 **PASS** — turn status=completed; visible_len=997(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 3 个。  **先看最该补的地方：** 1. 焊接材料的参数组合条件也需要进行焊接工艺评定 2. 焊接方法的参数组合条件也需要进行焊接工艺评定 3. 焊接位置的参数组合条件也需要进行焊接工艺评定  提示：本评分为 AI 阅卷草稿，非正式成绩。  **采分点：** - 

### t3_half — FAIL
- 题库外长案例·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785429937926_3291e19aa9`; status=completed; latency=32699ms)
  - A0 **PASS** — turn status=completed; visible_len=1774(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=['漏点', '漏掉', '漏/错'];漏点点名命中=[]
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 13 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 13 个。  **先看最该补的地方：** 1. 第1问：A：限制 2. 第1问：B：禁止 3. 第1问：C：不得用于25米及以上的建设工程  提示：本评分为 AI 阅卷草稿，非正式成绩。  ## 问题1：补充表1-1中A~G处的信息内容。 **你写的：** 这一问暂

### t3_question_only — PASS
- 题库外长案例·只发题不作答(form=question_only; turn_id=`turn_1785429975295_b963dc45f0`; status=completed; latency=42661ms)
  - A0 **PASS** — turn status=completed; visible_len=2568(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=2568 (>=300)
  - 回复摘录: ### 阅卷结论 你的作答属于“作答不完整”，系统判定为无效。你只提交了部分内容，且格式混乱，无法判断是否正确。对于问题1，你罗列了选项字母而没有给出具体内容，对于问题2、3、4则完全没有作答。本次不予评分，需要你重新完整作答。  ### 正确答案 本题为简答题，包含四个小问，正确答案如下： **问题1：** 依据《房屋建筑和市政基础设施工程危及生产安全施工工艺、设备和材料淘汰目录（第一批）》判定： A: 禁止；B: 禁止；C: 不得用于25米及以上的建设工程；D: 不得用于建设工地的生产、办公、生活等区域的照明； E: 普通钢筋调直机、数控钢筋调直切断机的钢筋调直工艺；F: 人货两用施工升降

### t3_wrong — PASS
- 题库外长案例·答错(等效龄期与评定结论均错)(form=wrong; turn_id=`turn_1785430021502_c54ddd654a`; status=completed; latency=35462ms)
  - A0 **PASS** — turn status=completed; visible_len=1579(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 17 个需要补。后面我按小问逐一拆。  **得分预估：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 17 个。  **先看最该补的地方：** 1. A：限制 2. B：禁止 3. C：不得用于25米及以上的建设工程  提示：本评分为 AI 阅卷草稿，非正式成绩。  **采分点：** - ❌ 术语不精确：A：限制（术语不精确：本采分点要求规范术语，近义/口语表述不得

### t4_g1_asis — PASS
- 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答)(form=full; turn_id=`turn_1785430061014_6954ffb38a`; status=completed; latency=45074ms)
  - A0 **PASS** — turn status=completed; visible_len=3124(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(9.11, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段带出处
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 3 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 18 个采分点，部分命中 0 个，还有 1 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 9.11 / 10 分。 **采分情况：** 命中 18 个，部分命中 0 个，漏/错 1 个。  **先看最该补的地方：** 1. 第2问：混凝土浇筑施工机具使用先后顺序为：A-B-C-D-E  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ## 问题1：答出图1中B~F处的施

### t4_g1_wrong — PASS
- 历史事故原题·答错版(机具/顺序/结论均改错)(form=wrong; turn_id=`turn_1785430110209_2c34f3cf39`; status=completed; latency=49122ms)
  - A0 **PASS** — turn status=completed; visible_len=3681(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.34, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段带出处
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 2 个采分点，部分命中 1 个，还有 17 个需要补。后面我按小问逐一拆。  **诊断得分预估：** 1.34 / 10 分。 **采分情况：** 命中 2 个，部分命中 1 个，漏/错 17 个。  **先看最该补的地方：** 1. 第1问：C: 布料机 2. 第1问：D: 串筒 3. 第1问：E: 振捣棒（或插入式振捣器）  提示：未命中题库原题/标准答案，本轮是题干推导诊断批改，不能作为正式阅卷成绩。  ##

### t4_q1_asis — FAIL
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=`turn_1785430163419_a737e757bb`; status=failed; latency=39086ms)
  - A0 **FAIL** — turn status=failed; visible_len=27(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=27 (>=300)
  - 回复摘录: 这次模型没有返回可见答案，已记录问题。请重新发送一次。

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785430206550_3bde588c76`; status=failed; latency=42497ms)
  - A0 **FAIL** — turn status=failed; visible_len=107(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=[]
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority=''; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: Let me also search for the formaldehyde standard limit and the specific detection point count requirements.

### t5_correct — PASS
- MCQ(qid=8731 氯离子复试)·答对并给理由(form=full; turn_id=`turn_1785430253610_a9ae16f39d`; status=completed; latency=20619ms)
  - A0 **PASS** — turn status=completed; visible_len=882(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - L1 **PASS** — len=882 (>=60)
  - 回复摘录: ### 阅卷结论 你答了B（外加剂），正确答案是B（外加剂）。依据教材/规范判定，本题答对，得1分。你的推理方向正确，抓住了外加剂是氯离子主要来源这一关键，值得肯定。  ### 正确答案 B. 外加剂  ### 为什么错（本题答对，转为“为什么对”） 你判断的关键依据是：外加剂（尤其是早强剂、防冻剂等）常含有氯盐，是混凝土中氯离子的主要来源，因此规范要求优先检验其氯化物含量。这一推理与教材/规范一致。  ### 知识点 混凝土原材料进场复验中的氯离子含量检测顺序。教材要点：外加剂是氯离子的首要来源，在有氯离子含量限制时，应首先检验外加剂的氯化物含量。  ### 易错点 | 易错理解 | 正确抓

### t5_question_only — PASS
- MCQ(qid=8731)·只发题不作答(答题必有解析)(form=question_only; turn_id=`turn_1785430274149_f86423bdc5`; status=completed; latency=7701ms)
  - A0 **PASS** — turn status=completed; visible_len=564(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - L1 **PASS** — len=564 (>=60)
  - 回复摘录: ## 📊 阅卷结论 这道题已命中题库原题。标准答案：B（B. 外加剂）。本题核心是先锁定题库给出的标准选项，再围绕原解析理解判断依据。  ## 🧐 解析 外加剂中常含有氯盐，是氯离子的主要来源，因此在有氯离子限制时，应首先检测外加剂的氯离子含量。粉煤灰、碎石、河砂也可能含氯，但通常含量较低，且规范要求优先检测外加剂。故选B。  ## ⚠️ 易错点 | 易错项 | 题库依据 | | :--- | :--- | | A. 粉煤灰 | 粉煤灰作为矿物掺合料，其氯离子含量通常较低，不是氯离子的主要或首要来源。 [概念混淆] | | C. 碎石 | 碎石作为粗骨料，其氯离子含量通常极低，且不易溶出，不是

### t5_wrong — PASS
- MCQ(qid=8731)·答错(选D河砂)(form=wrong; turn_id=`turn_1785430282019_df33543480`; status=completed; latency=14254ms)
  - A0 **PASS** — turn status=completed; visible_len=907(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - M2 **PASS** — contains_any['不正确', '不对', '错误', '误选', '不是', '并非'] 命中 ['错误', '不是', '并非']
  - L1 **PASS** — len=907 (>=60)
  - 回复摘录: ### 阅卷结论 你答错了。正确答案是B（外加剂），你选的是D（河砂）。诊断类型：概念混淆。  ### 正确答案 B. 外加剂  ### 为什么错 你错误地认为“河砂用量最大，所以氯离子总量贡献最大”，但混凝土中氯离子的主要来源并不是用量最大的骨料，而是外加剂（尤其是早强剂、防冻剂等常含氯盐）。规范要求在有氯离子含量限制时，应优先检验外加剂的氯离子含量。河砂确实可能含氯（如海砂），但并非首要来源，你把“用量”当成了“首要风险”的判断依据，属于概念混淆。  ### 知识点 混凝土原材料进场复试中，对有氯离子含量要求的工程，应首先检验外加剂的氯化物含量。外加剂是混凝土中氯离子的主要来源，控制其氯离

### t6_edge_ask — PASS
- KB边界偏门题(金属幕墙板材/气密性)·只问(form=question_only; turn_id=`turn_1785430296478_a0ee05de27`; status=completed; latency=15391ms)
  - A0 **PASS** — turn status=completed; visible_len=1284(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1284 (>=150)
  - 回复摘录: ## 结论  1. **金属幕墙常用板材**：铝板、不锈钢板、锌合金板、钛合金板等，以及铝塑复合板、铝蜂窝复合板等金属复合板。 2. **铝塑复合板现场加工讲究**：主要涉及切割折边时不得破坏面板涂层与芯材粘结、加工后及时做密封防腐蚀处理、折弯部位需留槽等要求。 3. **幕墙气密性能**：是交工前**必须检测**的项目，属于幕墙工程验收的强制性检测内容。  ---  ## 判断依据  ### 一、金属幕墙常用板材  按教材分类，金属幕墙板材分两类：  - **金属板幕墙**：铝板、不锈钢板、搪瓷钢板、锌合金板、钛合金板等 - **金属复合板幕墙**：铝塑复合板、铝蜂窝复合板、钛锌复合板等  

### t6_edge_full — PASS
- KB边界偏门题·带自己的理解求核对(form=full; turn_id=`turn_1785430312308_d4d3f54f6c`; status=completed; latency=30076ms)
  - A0 **PASS** — turn status=completed; visible_len=1556(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1556 (>=150)
  - 回复摘录: 让我再补充检索一下铝塑复合板加工和幕墙气密性检测的具体要求。  ## 结论  你的理解**基本正确，但有几处需要补充和修正**。金属幕墙板材的列举方向是对的，但铝塑复合板加工有专门讲究，气密性检测的适用场景也有边界条件——不是所有幕墙在交工前都必须做气密性检测。  ---  ## 一、金属幕墙常用板材  你的列举方向是对的，补充完整版如下：  **金属幕墙常用板材：** - **单层铝板** - **铝塑复合板**（铝塑板） - **蜂窝铝板** - **不锈钢板** - **彩色涂层钢板**（彩钢板） - **搪瓷板**（部分教材归入金属幕墙范畴）  > 你漏了 **彩色涂层钢板** 和 *

完整回复与 metadata 见 `evidence/<场景id>.md`。

## 门捕获的开放缺陷(对齐台账 OD-001~004;r3 对 SHA d1c2b44a 复验)

| 台账 | 场景 | r2(8d8bc5e4) | r3(d1c2b44a) | 现象 | 重放 |
|---|---|---|---|---|---|
| OD-001 | t3_half | FAIL | **FAIL(仍开放)** | 库外案例半答,未答问3/问4零提及被静默丢弃 | `python3 scripts/promo_gate/run_promo_gate.py --only t3_half` |
| OD-002 | t3_half(伴生) | 复现 | **复现(仍开放)** | 已答问1/问2被错参考判零(r3:命中0/漏错13,得分预估0/10) | 同上,看 evidence/t3_half.md |
| OD-003 | t4_q1_asis | FAIL | **FAIL(仍开放)** | #583原题只发题,39s后turn=failed,「模型没有返回可见答案」 | `python3 scripts/promo_gate/run_promo_gate.py --only t4_q1_asis` |
| OD-004 | t4_q1_half | FAIL(A6,判分产出但权威双空) | **FAIL(恶化:A0/A1/A6)** | r3 新形态:英文agent独白泄漏为可见回复(「Let me also search for…」)且turn=failed——独白剥离病复发形态 | `python3 scripts/promo_gate/run_promo_gate.py --only t4_q1_half` |

结论:r3 的 3 个 FAIL 全部对应已登记开放缺陷,无新增缺陷面;其余 18 场景
(含两条历史事故的 g1 判分线、全部 T1/T2 库内判分线、MCQ、KB 边界)全绿。
**当前状态 ≠ 可宣传态**;OD-001~004 逐个歼灭并重放复验绿后才达标。
