# 02 · 判官 temp=0 修复 / 欠切分 SEV-1 / 原子化样板

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §1限制①②。

## 判官不稳 → 根因 temp=0.7
- 现象:同一答卷判官 7/7 ↔ 5/7 抖动。
- **走错路修正**:一开始从 SHADOW 路径(`m35_artifact_shadow` 关键词匹配)得出"判官虚高不可信"——**错**。owner 点破"你没用 nexus、为什么用没有 LLM 的感知"。真判分是 V1 Nexus `rubric_grader_v1.grade_with_batch_judge_async`,grounded 于编译库 `v_case_rubric_scored`。
- **根因**:batch judge 调用未传 temperature,吃 `config.py:108` 默认 0.7。
- **治本**:`rubric_grader_v1.py` 三处 judge 调用点(1548/1564/2005)加 `temperature=0`。实测 **5/5 稳定**。
- ⚠️ 该修改在 worktree 分支,**未部署**到 test2;要 test2 生效需部署(§6 人门)。

## 欠切分 = 真 SEV-1(采分点源问题)
- 全库确定性扫描(纯读 published 编译库,零 LLM):**≥12 点欠切分大题 = 22 道**(盘点记 23,差异=含 rejected)。
- 病征:22-23 个大 qid 把多个小问混在一个 qid 下,**缺 `sub_no` 字段**。grader 机会式读 `sub_no`(`rubric_grader_v1.py:1245-1274/1580-1590`)但源数据没有 → 需**切分**(半自动 LLM + 双教研人审门)。
- **纠正早前口误**:不是"跨题污染"(source_qid 一致);全库扫**污染=0**,真病 = 100% 未校准 + 欠切分 + 零星近重复。

## 原子化切分样板(dev-anchor)
- `docs/原始数据/考点原料/成品/F16_屋面防水起鼓割补_案例题作答层样板.md`:干净原子采分点(R5-1 分档/100mm 界、R5-2~4 割补工序、R5-5~6 究因)+ 句式模板 + grounded 真题{2017,案例二}。**比编译库 qid 干净**,当 F16 dev-anchor 用。
- 域专家纠我:我早前"7 步原子拆"**过切**——真 = 4-5 点,"分层剥开"在"粘贴压实"内非独立步,"整片撕掉"应 ~0 分。样板已有正确切分。
- 样板证据:A(漏分层剥开)=1.2 / B(写了)=1.5(满分 1.5);对照污染 rubric A=B=1.36(切分不对就判不出差异)。

## 一个连带根因(别随便加护栏)
LLM 反馈曾与 verdict 矛盾(verdict=7/7 满分,② 却说"漏了分层剥开")。根因 = **我 skill prompt 的"只点最关键漏点"规则,在满分答卷上逼出一个编造漏点**,不是随机幻觉。修 = verdict 分支 prompt + "命中必信"。owner:"别随便加护栏"——修的是 skill 逻辑本身,不是下游过滤器。
