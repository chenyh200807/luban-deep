# LOG · quality-flywheel（append-only 活动流）

> shared-brain LOG 层。charter = `domains/quality-flywheel/README.md`。
> 格式：每条 `## YYYY-MM-DD · 标题 · #tag` + **What**（1-2 行结论先行）+ **Refs**。
> 只 append，新条在**上**。详细复盘仍在 `artifacts/tutorbot_fix_test_journal.md`（倒序），
> 本 LOG 只留「飞轮活动」一行结论 + 链接，不复制 journal 正文。

## 2026-07-04 · 调度 accuracy_gate(skipped) · #scheduled

What: 三方 SHA 不齐(origin=ba6ecae615e8, host=30077fdd4ae3, container=30077fdd4ae3), 跳过本次调度跑, 未产生任何探针调用。
Refs: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/quality_gate/scheduled/20260704_144654/report.md`

## 2026-07-04 · 调度 accuracy_gate · #scheduled

What: SHA=30077fdd4ae3, exit=3(BLOCK), 六维: daowu, huizhi, leak_boundary, sev_regression, forward_liveness, content_truth; 复现阻断维度: sev_regression。metrics/accuracy.jsonl 的 append 由 accuracy_gate.py 自身完成(单一 collector 权威), 本行只记调度活动。
Refs: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/quality_gate/scheduled/20260704_142239/report.md`

## 2026-07-01 · 飞轮 V2 shared brain 落地 + metrics 时序缺口补齐 · #flywheel #shared-brain

What: 把 v1 散件按 loop-engineer-template shared-brain 结构系统化（charter / signals 频次 /
metrics 确定性时序 / LOG）。真缺口=metrics jsonl 时序（每次 eval 算的 6 维 fail_rate 跑完即丢）
已补：`accuracy_gate.py` 纯 append collector → `domains/quality-flywheel/metrics/accuracy.jsonl`，
门判定逻辑/退出码一字未改。纯新增 + 文档，零运行时/SEV 风险，调度是第二步。
Refs: `domains/quality-flywheel/README.md`；plan doc §V2；`scripts/quality_gate/accuracy_gate.py`（`_append_metrics`）。

## 2026-06-30 · organic 泄露主病：未答隐式求助 fall-through 自由 LLM · #leak #sev #root-cause

What: 泄露真根因=未答题「隐式求助」（还是不会/给点提示）fall-through 到 `tutorbot_kb_first`
自由 LLM（不消费 anti-peek）自己推出答案；reveal/anti-peek 单权威健康，病在 reachability/consumption。
统一边界：anti-peek 只压「未答+隐式求助」→ 确定性结构化提示短路（考点/思路，绝不含答案选项）。
Refs: `docs/plan/题目生命周期与助教运行时/2026-06-30-unanswered-implicit-help-leak-deterministic-hint-collapse-plan.md`；前置止血 PR#315。映射 signal S4。

## 2026-06-30 · P0 一键准确性回归门 accuracy_gate 落地（飞轮 v1 基座）· #gate #anti-self-attestation

What: 学员军团 eval 固化为「换 SHA 一键复核六维、红即阻断」。三方 SHA 反自证元门
（origin/main == host .env == container env 且 GIT_DIRTY=false，不齐 STOP exit 2）+ 6 维编排 +
失败率/复现率 + 封板判据。主裁永远确定性、读持久化 `/messages` 终态；异源判官 `JUDGE_DEGRADED` 降级。
Refs: PR #321；plan doc v1；`scripts/quality_gate/accuracy_gate.py` + `probes/`。

## 2026-06-30 · Dim1 陈旧 active-set 拒判 live 闭合 · #forward-liveness #regression

What: smoke 部署 `a13b06183` 即「出新题替换陈旧 active-set」修复 commit；核 bot 持久化终态：
出 3 题再出单题后 bare「我选B」被正确判分、无「请带题号」拒判。Dim1 探针可证伪性受控验证通过
（拒判文本 → refused=True → fail，确认非硬编码绿）。映射 signal S7。
Refs: plan doc v1 §9 实施记录；`scripts/quality_gate/probes/dim_forward_liveness.py`。
