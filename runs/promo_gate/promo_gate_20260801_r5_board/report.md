# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_r5_board`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=c53a5d8a5ba3d6f74efa11e7732447ab514db5e3
DEEPTUTOR_RELEASE_ID=1.0.0+c53a5d8a5ba3d6f74efa11e7732447ab514db5e3+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-08-01T07:04:01  结束: 2026-08-01T07:17:59
- 结果: **24 PASS / 0 FAIL / 24 场景**(全绿 = 可宣传态)

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
| t3_half | 题库外长案例·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t3_question_only | 题库外长案例·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t3_wrong | 题库外长案例·答错(等效龄期与评定结论均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS A4:PASS |
| t4_g1_asis | 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_g1_wrong | 历史事故原题·答错版(机具/顺序/结论均改错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t5_correct | MCQ(qid=8731 氯离子复试)·答对并给理由 | **PASS** | - | A0:PASS A5:PASS M1:PASS L1:PASS |
| t5_question_only | MCQ(qid=8731)·只发题不作答(答题必有解析) | **PASS** | - | A0:PASS A5:PASS M1:PASS L1:PASS |
| t5_wrong | MCQ(qid=8731)·答错(选D河砂) | **PASS** | - | A0:PASS A5:PASS M1:PASS M2:PASS L1:PASS |
| t6_edge_ask | KB边界偏门题(金属幕墙板材/气密性)·只问 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t6_edge_full | KB边界偏门题·带自己的理解求核对 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t7_goldv2_low | 金标v2·Q2023-03低能力档作答(金标 expected_score_ratio=0.21)·弱答案不得满分 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS A9:PASS |
| t8_group_bundle_half | 治理组整卷案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·半答必须封顶 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS T8_BUNDLE:PASS T8_PERSUBQ:PASS T8_CAP:PASS |
| t9_full_paper_full_answer | 金标v2·Q2023-03高能力档整卷全答(金标 expected_score_ratio=0.84)·全答不得被封顶误伤 | **PASS** | - | A0:PASS A2:PASS A5:PASS A6:PASS A7:PASS T9_PERSUBQ:PASS T9_FLOOR:PASS |

## 逐场景证据摘录

### t1_full — PASS
- 题库内案例(合同价款,qid=8817)·全答(form=full; turn_id=`turn_1785539044158_74e4459f68`; status=completed; latency=21882ms)
  - A0 **PASS** — turn status=completed; visible_len=1870(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 3 个，现在逐点比对你的作答。  这一组采分点判完了（本组 3 个点）。  逐点比对完成，正在汇总结论和讲评。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 0 个，还有 2 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 

### t1_half — PASS
- 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785539070331_74ff4269e1`; status=completed; latency=17337ms)
  - A0 **PASS** — turn status=completed; visible_len=1940(入口必须完成且回复非空)
  - A1 **PASS** — 命中「未纳入本次判分」
  - A2 **PASS** — 得分对 [(1.1, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 5 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 3 个，现在逐点比对你的作答。  这一组采分点判完了（本组 3 个点）。  逐点比对完成，正在汇总结论和讲评。  ## 批改结论 这道题我先给你一个总判断：命中 1 个采分点，部分命中 1 个，还有 1 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 

### t1_question_only — PASS
- 题库内案例(qid=8817)·只发题不作答(form=question_only; turn_id=`turn_1785539091365_2ad6272808`; status=completed; latency=48192ms)
  - A0 **PASS** — turn status=completed; visible_len=4264(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=4264 (>=300)
  - 回复摘录: 这道题是一道综合案例题，共 5 个小问，我按小问逐一拆解。  ---  ## 第 1 问 · 合同签订不妥之处 + 合同文件解释顺序  ### 结论  **（1）不妥之处：** 甲乙双方协商修改了合同协议书和通用合同条款后签订施工合同。  **正确做法：** - 合同协议书应按示范文本格式填写，不应直接修改其标准结构。 - 通用合同条款应 **不加修改地引用**，不得直接修改。如需细化或补充，应在 **专用合同条款** 中约定，且专用条款编号应与通用条款编号一致。 - 保持待签合同与招标文件、投标文件的实质性内容一致（承包范围、工期、造价、计价方式、质量要求等），否则合同无效且将被责令改正。 

### t1_wrong — PASS
- 题库内案例(qid=8817)·答错(数值与顺序均错)(form=wrong; turn_id=`turn_1785539143917_08cf72eea9`; status=completed; latency=16449ms)
  - A0 **PASS** — turn status=completed; visible_len=1813(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 5 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 3 个，现在逐点比对你的作答。  这一组采分点判完了（本组 3 个点）。  逐点比对完成，正在汇总结论和讲评。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 

### t2_full — PASS
- 题库内案例(2023质量检测,qid=17357)·全答(form=full; turn_id=`turn_1785539164162_0be0e2761d`; status=completed; latency=27449ms)
  - A0 **PASS** — turn status=completed; visible_len=3260(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.47, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 24 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 6 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 5 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t2_half — PASS
- 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充)(form=half; turn_id=`turn_1785539195636_96abe67a78`; status=completed; latency=26502ms)
  - A0 **PASS** — turn status=completed; visible_len=3057(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['见证记录内容', '见证记录']
  - A2 **PASS** — 得分对 [(1.68, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 24 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 6 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 5 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t2_question_only — PASS
- 题库内案例(qid=17357)·只发题不作答(form=question_only; turn_id=`turn_1785539226425_b786b2bc56`; status=completed; latency=18807ms)
  - A0 **PASS** — turn status=completed; visible_len=1361(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1361 (>=300)
  - 回复摘录: ## 第 1 问·工程施工质量检测管理工作中的不妥之处及正确做法  ### 结论  本题共 2 处不妥，多答不得分，直接锁定这两处：  **① 不妥之处：** 试验员如实记录了其取样、现场检测等情况，制作了见证记录。  **正确做法：** 应由 ==见证人员==（监理工程师）记录其取样、现场检测情况，制作见证记录。  **② 不妥之处：** 总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。  **正确做法：** 建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，==单独列支==并按照合同约定及时支付。  ---  ### 判断依据  根据《建设工程质量检测管理办法》（住建

### t2_wrong — PASS
- 题库内案例(qid=17357)·答错(不妥点判断全错)(form=wrong; turn_id=`turn_1785539249009_f821af9756`; status=completed; latency=22651ms)
  - A0 **PASS** — turn status=completed; visible_len=3200(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 1 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 24 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 6 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t3_full — PASS
- 题库外长案例(2022案例一改写)·全答(form=full; turn_id=`turn_1785539275644_03502bfd8c`; status=completed; latency=49733ms)
  - A0 **PASS** — turn status=completed; visible_len=3896(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(10.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  这道题没有现成的参考答案，正在按题干推导采分点，这一步最花时间（通常二十几秒）。  采分点推导中（已用时 12 秒，完成后先给结论再给逐点明细）。  采分点推导中（已用时 19 秒，完成后先给结论再给逐点明细）。  采分点拆好了，共 24 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 7 个点，共 3 组）。  第 2 组采分点判完了（本组 6 个

### t3_half — PASS
- 题库外长案例·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785539329538_8193bd4a8c`; status=completed; latency=48318ms)
  - A0 **PASS** — turn status=completed; visible_len=4265(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['第3问', '问题3', '问题4']
  - A2 **PASS** — 得分对 [(4.81, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  这道题没有现成的参考答案，正在按题干推导采分点，这一步最花时间（通常二十几秒）。  采分点推导中（已用时 10 秒，完成后先给结论再给逐点明细）。  采分点推导中（已用时 17 秒，完成后先给结论再给逐点明细）。  采分点拆好了，共 24 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 7 个点，共 3 组）。  第 2 组采分点判完了（本组 7 个

### t3_question_only — PASS
- 题库外长案例·只发题不作答(form=question_only; turn_id=`turn_1785539381819_aacd5efd1d`; status=completed; latency=59272ms)
  - A0 **PASS** — turn status=completed; visible_len=1262(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1262 (>=300)
  - 回复摘录: ### 阅卷结论 你答了“错”，但未正确写出表1中A~G的具体内容，系统判定为无效作答。本题需要补充的七个信息点，你未给出任何一项对应的正确表述，得分0分。  ### 正确答案 A: 限制 B: 禁止 C: 不得用于25米及以上的建设工程 D: /（无限制条件，因属禁止类） E: 普通钢筋调直机、数控钢筋调直切断机的钢筋调直工艺 F: 人货两用施工升降机 G: LED灯、节能灯等  ### 为什么错 你只写了“E. A. C. B. D. F”这一串字母，没有写出每个字母对应的具体内容，属于**审题遗漏**——问题要求“补充表1中A~G处的信息内容”，即需逐项填写文字，而非只标注字母；同时，字

### t3_wrong — PASS
- 题库外长案例·答错(等效龄期与评定结论均错)(form=wrong; turn_id=`turn_1785539445340_d6e02a45c3`; status=completed; latency=42417ms)
  - A0 **PASS** — turn status=completed; visible_len=3761(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **PASS** — 库外免责命中 ['诊断得分预估', '得分预估']
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  这道题没有现成的参考答案，正在按题干推导采分点，这一步最花时间（通常二十几秒）。  采分点推导中（已用时 10 秒，完成后先给结论再给逐点明细）。  采分点推导中（已用时 17 秒，完成后先给结论再给逐点明细）。  采分点拆好了，共 21 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 7 个点，共 3 组）。  第 2 组采分点判完了（本组 5 个

### t4_g1_asis — PASS
- 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答)(form=full; turn_id=`turn_1785539491484_38daa4a0d9`; status=completed; latency=37573ms)
  - A0 **PASS** — turn status=completed; visible_len=3155(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(1.89, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点推导中（已用时 12 秒，完成后先给结论再给逐点明细）。  采分点拆好了，共 19 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 3 组）。  第 2 组采分点判完了（本组 5 个点，共 3 组）。  第 3 组采分点判完了（本组 9 个点，共 3 组）。  逐点比对

### t4_g1_wrong — PASS
- 历史事故原题·答错版(机具/顺序/结论均改错)(form=wrong; turn_id=`turn_1785539533401_cfb0cc9d5a`; status=completed; latency=28953ms)
  - A0 **PASS** — turn status=completed; visible_len=3239(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 8 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 19 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 3 组）。  第 2 组采分点判完了（本组 5 个点，共 3 组）。  第 3 组采分点判完了（本组 9 个点，共 3 组）。  逐点比对完成，正在汇总结论和讲评。  ## 批改结论 这道题我先给你一个总

### t4_q1_asis — PASS
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=`turn_1785539566164_f0dfad2237`; status=completed; latency=64339ms)
  - A0 **PASS** — turn status=completed; visible_len=3321(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3321 (>=300)
  - 回复摘录: 这道题是典型的案例综合题，覆盖了安全、机械、临时用水、卫生设施、室内环境五个考点。下面按小问逐一拆解。  ---  ## 第1问：现浇混凝土安全事故类型还有哪些？安全控制主要内容还有哪些？  **结论：** 安全事故类型还有 **高处坠落、物体打击、触电、机械伤害、脚手架失稳、重物吊装**。安全控制主要内容还有 **模板支撑系统设计、混凝土浇筑用电安全、模板施工安全、混凝土浇筑安全、高处作业安全防护、机械设备安全、拆除模板安全**。  **判断依据：** - 安全事故类型：模板支撑系统整体坍塌、高空坠落、物体打击、触电、机械伤害、脚手架失稳、重物吊装。 - 安全控制主要内容：模板支撑系统设计、

### t4_q1_half — PASS
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785539634790_e0a12a0770`; status=completed; latency=59501ms)
  - A0 **PASS** — turn status=completed; visible_len=4827(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['漏点', '漏掉', '漏/错'] + 点名漏点['第3问', '问题3', '问题4']
  - A2 **PASS** — 得分对 [(4.96, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1_diagnostic; grading_rubric_provenance=derived_from_stem
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里没有匹配到这道题的原题，接下来按你贴的题干自己拆采分点。  这道题没有现成的参考答案，正在按题干推导采分点，这一步最花时间（通常二十几秒）。  采分点推导中（已用时 9 秒，完成后先给结论再给逐点明细）。  采分点推导中（已用时 16 秒，完成后先给结论再给逐点明细）。  采分点推导中（已用时 24 秒，完成后先给结论再给逐点明细）。  采分点拆好了，共 30 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 7 个点，共 

### t5_correct — PASS
- MCQ(qid=8731 氯离子复试)·答对并给理由(form=full; turn_id=`turn_1785539698739_a9619d78b4`; status=completed; latency=21027ms)
  - A0 **PASS** — turn status=completed; visible_len=905(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - L1 **PASS** — len=905 (>=60)
  - 回复摘录: ### 阅卷结论 你答对了，本题得1分。诊断类型：CORRECT。你的选择B（外加剂）与教材/规范判定一致，是正确的。  ### 正确答案 B. 外加剂。依据《混凝土结构工程施工质量验收规范》等要求，外加剂（尤其是早强剂、防冻剂）常含有氯盐，是混凝土中氯离子的主要来源，因此进场复试中应首先检验其氯化物含量。  ### 为什么错 你答对了，无需纠错。本次判断的关键依据：外加剂作为氯离子的主要来源，其掺量虽小但氯离子浓度高，对混凝土总氯离子含量影响最直接，规范要求优先检测。  ### 知识点 混凝土原材料进场复试的氯离子含量检测顺序。教材要点：外加剂是氯离子的主要来源，在有氯离子含量限制时，应优先

### t5_question_only — PASS
- MCQ(qid=8731)·只发题不作答(答题必有解析)(form=question_only; turn_id=`turn_1785539719899_9b62fbcd44`; status=completed; latency=7856ms)
  - A0 **PASS** — turn status=completed; visible_len=564(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - L1 **PASS** — len=564 (>=60)
  - 回复摘录: ## 📊 阅卷结论 这道题已命中题库原题。标准答案：B（B. 外加剂）。本题核心是先锁定题库给出的标准选项，再围绕原解析理解判断依据。  ## 🧐 解析 外加剂中常含有氯盐，是氯离子的主要来源，因此在有氯离子限制时，应首先检测外加剂的氯离子含量。粉煤灰、碎石、河砂也可能含氯，但通常含量较低，且规范要求优先检测外加剂。故选B。  ## ⚠️ 易错点 | 易错项 | 题库依据 | | :--- | :--- | | A. 粉煤灰 | 粉煤灰作为矿物掺合料，其氯离子含量通常较低，不是氯离子的主要或首要来源。 [概念混淆] | | C. 碎石 | 碎石作为粗骨料，其氯离子含量通常极低，且不易溶出，不是

### t5_wrong — PASS
- MCQ(qid=8731)·答错(选D河砂)(form=wrong; turn_id=`turn_1785539727878_1d399b5afb`; status=completed; latency=16924ms)
  - A0 **PASS** — turn status=completed; visible_len=933(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **PASS** — contains_all['外加剂'] 缺 []
  - M2 **PASS** — contains_any['不正确', '不对', '错误', '误选', '不是', '并非'] 命中 ['不是']
  - L1 **PASS** — len=933 (>=60)
  - 回复摘录: ### 阅卷结论 你答了D（河砂），正确答案是B（外加剂）。本题判定为概念混淆，得0分。  ### 正确答案 B. 外加剂  ### 为什么错 你的推理方向是“用量大→氯离子总量大”，但这忽略了氯离子在混凝土中的主要来源是外加剂（尤其是早强剂、防冻剂等含氯盐类），而非用量最大的河砂。教材和规范要求：“对有氯离子含量要求时，首先需要检验氯化物含量的是外加剂。”【教材要点】你混淆了“材料用量”与“氯离子主要来源”的关系，属于**概念混淆**。  ### 知识点 本题考点：混凝土原材料进场复试中氯离子含量的检测顺序。外加剂是氯离子的主要来源，进场复验时需优先检测其氯化物含量，以控制钢筋锈蚀风险。  

### t6_edge_ask — PASS
- KB边界偏门题(金属幕墙板材/气密性)·只问(form=question_only; turn_id=`turn_1785539744965_fd7eaae6f8`; status=completed; latency=11538ms)
  - A0 **PASS** — turn status=completed; visible_len=836(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=836 (>=150)
  - 回复摘录: ## 结论  **1. 金属幕墙常用板材**   **2. 铝塑复合板现场加工要点**   **3. 幕墙工程交工前气密性能属于必须检测项目**  ---  ## 1. 金属幕墙常用板材  金属幕墙面板按材质分两类：  - **金属板幕墙：** 铝板、不锈钢板、搪瓷钢板、锌合金板、钛合金板等 - **金属复合板幕墙：** 铝塑复合板、铝蜂窝复合板、钛锌复合板等  你问的**铝塑复合板**就属于金属复合板幕墙这一大类，是现场最常见的金属幕墙板材之一。  ---  ## 2. 铝塑复合板现场加工使用要点  教材中金属幕墙施工要点专门提到铝塑复合板加工时的两个关键讲究：  1. **切割时严禁折边*

### t6_edge_full — PASS
- KB边界偏门题·带自己的理解求核对(form=full; turn_id=`turn_1785539756949_e3e7b5828f`; status=completed; latency=26808ms)
  - A0 **PASS** — turn status=completed; visible_len=1268(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=1268 (>=150)
  - 回复摘录: ## 结论  你的理解**基本正确，但金属幕墙板材的分类口径需要调整一下**，气密性能的判断是对的。  ---  ## 一、金属幕墙常用板材——你的理解要微调  教材的分类口径是这样的：  **金属板幕墙**（狭义）：铝板、不锈钢板、搪瓷钢板、锌合金板、钛合金板等。  **金属复合板幕墙**（单独一类）：铝塑复合板、铝蜂窝复合板、钛锌复合板等。  所以你的理解问题在于——**单层铝板、铝塑复合板、蜂窝铝板虽然都是金属类面板，但教材把它们分在两个子类里**：  | 类别 | 包含板材 | 你的理解 | | --- | --- | --- | | 金属板幕墙 | 单层铝板、不锈钢板、搪瓷钢板、锌合

### t7_goldv2_low — PASS
- 金标v2·Q2023-03低能力档作答(金标 expected_score_ratio=0.21)·弱答案不得满分(form=gold_v2_low; turn_id=`turn_1785539783698_fda88879cd`; status=completed; latency=29189ms)
  - A0 **PASS** — turn status=completed; visible_len=3573(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.04, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A9 **PASS** — 最高得分率 0.204 < 0.5(得分对 [(2.04, 10.0)])
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 4 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 25 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 7 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t8_group_bundle_half — PASS
- 治理组整卷案例题(2023办公楼·题库按小问拆存)·整题4问粘贴+只答问1·半答必须封顶(form=group_bundle_half_answer; turn_id=`turn_1785539816953_1778d4322b`; status=completed; latency=25943ms)
  - A0 **PASS** — turn status=completed; visible_len=3322(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(2.5, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - T8_BUNDLE **PASS** — case_bundle_source='group_query' 全等期望值
  - T8_PERSUBQ **PASS** — case_per_subq_grading='4/4' 全等期望值
  - T8_CAP **PASS** — 最高得分 2.5 <= 封顶 3.0(分母=10.0 得分对 [(2.5, 10.0)])
  - 回复摘录: 这道案例题我已经进入逐采分点批改，会按 2 个小问逐一核对。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  先去题库里比对这道题的原题和已编译的采分点。  题库里定位到了这道题的原题，按它的编译采分点批改。  已拿到这道题的参考答案，正在把它拆成可以独立判定的采分点。  采分点拆好了，共 26 个，现在逐点比对你的作答。  第 1 组采分点判完了（本组 5 个点，共 4 组）。  第 2 组采分点判完了（本组 6 个点，共 4 组）。  第 3 组采分点判完了（本组 8 个点，共 4 组）。  第 4 组采分点判完了（本组 7 个点，共 4 组）。  逐点比对完成，正

### t9_full_paper_full_answer — PASS
- 金标v2·Q2023-03高能力档整卷全答(金标 expected_score_ratio=0.84)·全答不得被封顶误伤(form=gold_v2_high_full_paper; turn_id=`turn_1785539847213_b45cdc55e8`; status=completed; latency=29357ms)
  - A0 **PASS** — turn status=completed; visible_len=3135(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(9.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - T9_PERSUBQ **PASS** — case_per_subq_grading='4/4' 在场且非空
  - T9_FLOOR **PASS** — 最高得分 9.0 >= 下限 6.0(分母=10.0 得分对 [(9.0, 10.0)])
  - 回复摘录: ## 批改结论 这道题我先给你一个总判断：命中 23 个采分点，部分命中 1 个，还有 2 个需要补。后面我按小问逐一拆。  **得分预估：** 9 / 10 分。 **采分情况：** 命中 23 个，部分命中 1 个，漏/错 2 个。  **先看最该补的地方：** 1. 第2问：抽检数量不应少于总桩数的20% 2. 第2问：抽检数量不应少于10根 3. 第3问：现场钢筋直螺纹接头加工和安装质量检测专用工具包括：量尺、通规、止规、管钳扳手、扭力扳手  提示：本评分为 AI 阅卷草稿，非正式成绩。  ## 问题1：指出工程质量计划编制和管理中的不妥之处，并写出正确做法。工程质量计划中应设置质量控

完整回复与 metadata 见 `evidence/<场景id>.md`。
