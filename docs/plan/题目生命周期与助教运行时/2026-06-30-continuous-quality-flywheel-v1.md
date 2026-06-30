# 持续质量飞轮 v1 — P0 一键准确性回归门 accuracy_gate

- 状态: `Implemented`（P0 一键门基座落地 + smoke 验编排通过；持续维度扩充为后续）
- 单一 authority: 本文件是「TutorBot 准确性回归门」的 loop 设计入口；不新建第二套质量门主线，
  也不替代 `contracts/turn.md` 硬约束、`tutorbot-student-army-eval-loop` skill 与
  `deeptutor-aliyun-release` 发布门。门只「观测 + 阻断」，不改运行时 authority。
- 相关代码入口:
  - `scripts/quality_gate/accuracy_gate.py` — 一键门（SHA 三方门 + 6 维编排 + 失败率 + 封板判据 + 退出码）
  - `scripts/quality_gate/probes/_probe_common.py` — 共享基座（login/turn/终态读取/异源判官 + DEGRADED 降级契约）
  - `scripts/quality_gate/probes/dim_*.py` — 6 个确定性探针
  - `agent-skills/tutorbot-student-army-eval-loop/SKILL.md` §4/§6 — 反自证元门 + 接内容飞轮

## 1. 目标 / 非目标

目标:
- 把「学员军团 eval」从一次性手跑探针，固化为「换 SHA 一键复核六维，红即阻断」的 P0 封板门。
- 主裁永远确定性，异源 LLM 仅附加且假阳自动降级（不计 pass/fail），杜绝判官噪声当内容失败。
- 反自证硬前置：绝不在「不是当前 origin/main」的部署上跑 eval 并据此宣称结论。

非目标:
- 不做满意度均值打分（失败率口径，非平均分）。
- 不替代人在环复核：门负责把「确定性可复现的红」挡住；语义边界争议仍交人裁。
- 不在门里改任何 TutorBot 运行时 authority（门是观测者，不是 writer）。

## 2. Swiss Cheese 多层防御

复发类 bug（倒诬/回指/泄露/拒判/编造）单层挡不住。本门把多层串成「奶酪叠加」，
任一层漏需另一层补，全部对齐才放行：

| 层 | 机制 | 落点 |
|---|---|---|
| L0 反自证元门 | 三方 SHA 门（origin/main == host .env == container env 且 GIT_DIRTY=false） | `accuracy_gate.check_sha_gate` |
| L1 确定性主裁 | 每维断言写死、可证伪、读持久化 `/messages` 终态（非流式、非动作自报） | `dim_*.py` + `_probe_common.terminal_messages` |
| L2 异源判官（附加，可降级） | DeepSeek/GLM 仅佐证盲点；network/限流/无 key → `JUDGE_DEGRADED` 不计 pass/fail | `_probe_common.{deepseek_judge,glm_judge,is_degraded}` |
| L3 复现率 / 失败率 | 每维每 unit 跑 `--runs` 轮，统计 fail/有效轮 + reproduced 标记 | `_probe_common.run_dimension` |
| L4 封板判据 | 六维全 0 复现 → exit 0；任一复现 → exit 3 阻断 + 点名 + 证据路径 | `accuracy_gate.main` |

## 3. 六维回归门

| 维度 | 探针 | 确定性主裁 |
|---|---|---|
| 倒诬 daowu | `dim_daowu` | 显式重排后呈现面 == 原序（surface_stable o1==o2）；自由重排出新序 + 判官确认判分用不一致面 = 复现 |
| 回指 huizhi | `dim_huizhi` | 逐项分析 >=3/4 锚定原题选项值 = 绑定正确；GLM 仅附加 |
| 出题泄露+边界 leak_boundary | `dim_leak_boundary` | A 隐式求助无 REVEAL；B 显式索答有 REVEAL（不过度抑制）；C 未答回指考点无 REVEAL |
| 3-SEV 回归 sev_regression | `dim_sev_regression` | 倒诬/泄露/回指单臂回归，异源 DeepSeek 判官 + 倒诬确定性序断言 |
| 拒判 forward_liveness | `dim_forward_liveness` | 批量作答必逐题判分；Dim1 陈旧多题 active-set bug：出新题后 bare 答案必判、无「请带题号」拒判 |
| content-truth | `dim_content_truth` | 规范条文①永远输出不抑制②核不到时 hedge present（以教材/现行规范为准、AI 生成不保证） |

## 4. 裁决阶梯（owner 钉死）

1. 确定性断言主裁（写死可证伪、读持久化终态）。
2. owner 独立 review 源码/终态。
3. 异源 LLM（DeepSeek/GLM）仅附加盲点检测，绝不主裁；不可信即降级，不计 pass/fail。

内容分歧（哪个答案对）与结构 SEV（绑定/呈现面/是否判分）**确定性分离**，
别让内容争议污染结构判定。

## 5. 反自证元门（真相 authority 三性）

门自身的可信度取决于「观测者独立于被观测者」。真相 authority 必须同时满足:
- **独立**: 判据不依赖被测 bot 的自报（读持久化 `/messages` 终态，不信流式/动作自报；
  异源判官非同一模型家族）。
- **可证伪**: 每个断言写死失败判据（如 REJ→refused=True→fail；自由重排+判官 DAOWU→fail）。
- **可重复终态观测**: `--runs` 多轮、全新会话、清白持久态→触发→查持久态，复现率而非单次。

L0 三方 SHA 门是这条原则的硬前置：在「不是当前 origin/main」的部署上跑出的绿，
是自证的假绿，门直接 STOP（exit 2）。

## 6. 自动化 vs 人在环

- **自动阻断（门负责）**: 确定性可复现的红（拒判复现、自由重排倒诬、显式 REVEAL 泄露、内容抑制/无 hedge）。
- **人在环（门只标，不替判）**: 全维 inconclusive（judge 全降级/采集失败 → exit 4，无法判定非内容失败）；
  语义边界争议（topic precision drift、题源忠实度）继续走 student-army skill 人读裁决。

## 7. 接内容飞轮（P3）

fabrication（编造规范条文/采分点/题目）是**内容补全信号**，不是只在运行时压制。
当 content_truth / sev_regression 反复在某知识缺口现编时，把该缺口回灌到内容生产飞轮:
- 采分点缺 → `scoring_point_compile.v1` 编译管道补该母题采分点（真值唯一源，bot 只引用）。
- 教材条文缺 → 教材逐字签发管道（讲义 `*_v8` chunk）补该章节，使运行时核得到、不必现编。

即：质量门不只是「挡红」，它的红是**内容生产的需求清单**，闭合「辅导用户 → 暴露缺口 → 内容补全 → 复测」的飞轮。

## 8. 用法

```bash
cd <repo>; set -a; source .env; set +a
export DEEPTUTOR_QA_USERNAME="$WECHAT_QA_USERNAME" DEEPTUTOR_QA_PASSWORD="$WECHAT_QA_PASSWORD"
# 封板（默认每维每 unit 3 轮，三方 SHA 门前置）:
python scripts/quality_gate/accuracy_gate.py --runs 3
# smoke（每维 1 轮，验编排通）:
python scripts/quality_gate/accuracy_gate.py --runs 1
```

退出码: `0` GO（六维全 0 复现）｜`2` SHA 门 STOP｜`3` 复现阻断（点名 + 证据路径）｜`4` 无法判定。

## 9. 实施记录 / 落地证据（2026-06-30）

- 6 探针固化走 `_probe_common`（4 个从 scratchpad 整理：daowu/huizhi/sev/leak-boundary 口径一字不改；
  2 个新建：forward_liveness 含 Dim1 known-bug 断言、content_truth 不抑制+hedge）。
- L0 SHA 门 live 验证: 部署 `a13b06183`（host .env == container，GIT_DIRTY=false）≠ origin/main `1247376785`
  （main 领先一个 observability commit）→ 门正确 STOP（exit 2），证明反自证前置生效。
- 6 维编排 smoke（`--skip-sha-gate`，对 `a13b06183` 部署，`--runs 1`）: 六维全绿、judge 降级路径在位、
  exit 0。注: `a13b06183` 即「出新题替换陈旧 active-set」的 **Dim1 修复 commit**，故 Dim1 已
  live 闭合（核 bot 终态: 出 3 题再出单题后 bare「我选B」被正确判分、无「请带题号」拒判）。
  这是真实状态推进（部署从 686fe37bb 前移到 Dim1 修复），非口径软化。
- Dim1 探针可证伪性: 受控验证拒判文本（「你这轮有多道题请带题号」）→ refused=True → fail，
  确认探针非硬编码绿、能挡回归。

## 10. 后续（非本 P0 scope）

- 待 main 与部署对齐后，跑一次三方 SHA 门齐的 `--runs 3` 全量封板，落 GO 证据。
- 维度扩充: 案例题采分点判分忠实度、topic-source 忠实度、长对话稳定性（按内容飞轮缺口优先级）。
- 接 CI / 定时: 作为 release 前置门挂 `deeptutor-aliyun-release` 流程后段（部署后真窗复核）。
