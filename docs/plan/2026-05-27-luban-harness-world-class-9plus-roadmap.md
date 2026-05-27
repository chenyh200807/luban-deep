# 鲁班 Harness — 世界级 9+/10 路线图

> **For agentic workers:** REQUIRED SUB-SKILL：每个 Phase 是一个独立子系统,用 `superpowers:writing-plans` 把它展开成 bite-sized PR 计划,再用 `superpowers:subagent-driven-development` / `executing-plans` 执行。本文是 **master 路线图 + H1 keystone 详化**;H2–H7 是 scoped spec,开工时各自展开。
>
> **归属**：[`2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md`](./2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md) 的世界级化续篇。前序已落地:P0 单一权威 + §4 的 D1/D4/D5(详见该计划 + 前置设计文档)。

**Goal:** 把 harness 从当前 ~6/10(扎实地基)拉到 **≥9/10(世界顶尖)**:可确定性回放的全量轨迹 eval + 语义质量打分 + 真实生产面覆盖 + 生产 trace 自喂养闭环 + 架构级单一权威 + 趋势化质量门。

**Architecture:** keystone 是 **record/replay cassette 层**——录制真实 LLM/tool 的非确定性事件,之后确定性回放,使"全量、真实面、每次提交、免费、秒级"的轨迹+质量 eval 成为可能。其余阶段都建立在这一层之上。

**Tech Stack:** Python/pytest;现有 `core/stream.py`/`trace.py`、`services/llm/factory.py`(`complete`/`llm_stream`)、`runtime/registry/tool_registry`、`eval/gates.yaml`、Langfuse、`services/observability/failed_turn_promotion.py`;新增 cassette 存储 + rubric judge + trajectory scorer。

---

## 0. 评分标尺(让 9+ 可度量)

当前 6/10 的判断与差距见会话评估。把"世界级"拆成 7 个可验收维度,每维 0–10,加权得总分。**9+ 要求每一维 ≥8、且无单维 <7。**

| 维度 | 当前 | 9+ 目标 | 由哪个 Phase 关闭 |
|---|---|---|---|
| 单一权威收敛 | 7.5 | 9（架构级强制） | H5 |
| 回归网确定性/可每次提交 | 4 | 9（cassette 回放） | **H1** |
| 语义/质量打分 | 2 | 9（rubric+judge，对齐人工） | H2 |
| 真实面覆盖+规模 | 3 | 9（200+ case，RAG/tutorbot/多轮） | H3 |
| 生产反馈闭环 | 2 | 9（失败 turn 自动晋级） | H4 |
| 趋势/成本/延迟可观测门 | 4 | 8（dashboard+delta gate） | H6 |
| 红利项落地（D2/D4/D5 全） | 5 | 8 | H7 |
| 工程纪律/过程 | 8.5 | 9（保持） | 全程 |
| **经验性命中率(真·9+ 判据,见 C3)** | 未测 | 9（拦住真回归、低误报，有数据） | 全程度量 |

> **重要(v2/C3)**:上表前 7 维是"能力维",但**世界级的最终判据是最后一行——harness 经验性地拦住了多少真回归、误报多少**。能力维全满但从没拦住过真问题,不算 9+。所以本路线图把"命中率度量"作为贯穿全程的一等产物,而非附属。

---

## 1. 世界级实践基线（调研依据，2026-05 检索）

本路线图不是凭空设计,锚定以下实践:

- **Record/Replay 是 eval 确定性的前提**:只录非确定性事件(LLM 调用、tool 结果),确定性部分回放时注入记录的输入;必须录 **model id + 解码参数(temperature/top_p/max_tokens/penalties) + tool id→stub**。参考 `llm-test-harness`(cassette + eval scoring + regression)。来源:[Get Experience from Practice: LLM Agents with Record & Replay (arXiv 2505.17716)](https://arxiv.org/html/2505.17716v1)、[Trustworthy AI Agents: Deterministic Replay](https://www.sakurasky.com/blog/missing-primitives-for-trustworthy-ai-part-8/)、[llm-test-harness (PyPI)](https://pypi.org/project/llm-test-harness/)。
- **LLM-as-judge 用 analytic rubric**(逐 criterion 打分,非单一不透明分,便于回归定位);**先用 golden 对齐人工 75–90% 再放量**;**judge 用不同模型家族**避免自增强偏置;防 position/verbosity bias(平衡排列、bias 校正)。来源:[Rubric-Based Evals & LLM-as-a-Judge (Masood)](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)、[Arize: LLM as a Judge](https://arize.com/llm-as-a-judge/)、[Position Bias in Rubric-Based LLM-as-a-Judge (arXiv 2602.02219)](https://arxiv.org/pdf/2602.02219)。
- **生产 trace → 数据集闭环**:生产失败一键变回归 case;**结构化 trace 是前提**(retrieval 分数/chunk 来源/tool 参数/延迟可独立查询);规模 **50 抓大回归 / 200 抓 3–5% 变化 / >500 边际递减**。来源:[Braintrust: LLM evaluation guide](https://www.braintrust.dev/articles/llm-evaluation-guide)、[LangChain: LLM Evals](https://www.langchain.com/articles/llm-evals)、[Building a Golden Dataset (Maxim)](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/)。
- **轨迹度量**:step 匹配(exact/in-order/any-order)、step-level precision/recall、tool 选择准确率、参数正确性、convergence、path efficiency、对召回来源的 faithfulness/groundedness。来源:[Beyond the Final Answer: Evaluating Reasoning Trajectories (arXiv 2510.02837)](https://arxiv.org/pdf/2510.02837)、[Agent Evaluation Platforms 2025 (Maxim)](https://www.getmaxim.ai/articles/top-agent-evaluation-platforms-in-2025-the-definitive-enterprise-guide/)。

---

## 1.5 v2 对抗自审：载荷级修正（principal-engineer 复核）

v1 路线图方向对,但有几处**会让整套 harness 在真实使用中烂掉**的隐患。逐条修正:

**C1 — replay 的两个真相(H1 最关键)。**
(a) **replay 冻结模型输出 → 它验的是"编排/轨迹结构"不是"答案质量"**。prompt 改了,recorded 输出不变(只是 key 不命中),所以 **replay 抓不到 prompt 改动带来的质量回归**。v1 "H1 让质量 eval 每次提交免费跑"是错的——质量(H2)本质上需要**定期 live 跑**(夜间/按需),不是每次提交免费。修正:H1 的价值 = 每次提交确定性验**编排/轨迹结构**;质量门是**定期 live + judge**。
(b) **cassette key 必须对良性非确定性鲁棒**(归一化 turn_id / 时间戳 / uuid / dict-set 顺序),否则 prompt 拼装里任何易变字段都会让 key 漂移→"假回归"。naive message-digest 会 brutally flaky——这是 record/replay harness 烂掉的头号原因。cassette miss 要**区分"良性漂移 vs 真实变更"**(给 diff 让人判,不是无脑红)。
(c) shim 必须**断言拦截完整性**(捕获了全部 LLM/tool 调用次数),否则生产路径变更后 shim 静默失效 → 假绿。

**C2 — 有 ground truth 的地方,确定性 oracle > LLM-judge(H2)。** 建造考试的 **exact 答案本身就是 ground truth** → exact 保真度用**确定性精确匹配 oracle**(便宜、无 judge、无偏置)。LLM-judge 只留给开放式(讲解忠实度 / 教学性 / grounding faithfulness)。judge 本身要**版本钉死 + judge 调用也 cassette 化 + 定期对人工重校准**;人工标注是真实瓶颈(种子 ~30 起步、逐步长)。

**C3 — 9+ 的唯一可信证明是"经验性命中率",不是我自评的 rubric(最深的一条)。** 世界级 harness 由**它实际拦住多少真回归**证明,不是自打分。必须把 **harness 自身的 precision/recall** 做成一等指标:近 N 次变更/线上事故里,网在合并前拦住的比例 + 误报率。**"9+" 重新定义为:可证明地拦住会真正伤到你的回归,且误报低。** 没有这条,9 分只是我的观点。

**C4 — 不要另造,建在现有基建上(降工作量+降风险)。** 仓库已有:`services/benchmark/runner.py`(多套件 `_run_semantic/context/rag/long_dialog/surface` + `_compute_baseline_diff` + `_aggregate_failure_taxonomy` + `_build_blind_spots`)、`failed_turn_promotion.py`(失败 turn → incident candidate)。修正:**H1 把这个 runner 做成可 replay;H3 扩它的 case 集;H4 把 failed_turn_promotion 的 candidate 接进 case 语料**——不另起平行 harness。

**C5 — 永不把生产 trace 原文提交进 git(H4)。** 生产对话=真实用户数据。即便脱敏,把用户对话提交进仓库是隐私/合规风险。修正:生产派生 case 要**合成/重写成代表性 case**,原始语料放**私有存储(git 外)**;且要**采样通过的 turn**(不只失败),否则语料偏向失败、抓不到对"当前正常行为"的回归。

**C6 — build-vs-buy(已核验):** 仓库 Langfuse 集成**只有 tracing/cost,无 dataset/evaluator/experiment**——"用 Langfuse 当 eval 平台"是**新集成工作,不是 drop-in**。可选但不免费。决策:H2/H6 的打分/趋势优先复用**现有 runner 的 baseline-diff + failure-taxonomy**,Langfuse datasets 作为"若投入产出比合适再接"的备选,不作前提。

**C7 — H5 防过度工程。** "让第二套 authority 写不出来"在 Python 里做成运行时 provenance 框架会**违反本项目 §2/§0(thin wrappers/less is more)** 且拖慢热路径。修正:H5 收敛为**廉价的 AST import-graph CI 检查**(抓 alias/间接 import,比 grep 强、仍静态/零运行时开销),不做运行时框架。

**C8 — 按 launch-readiness 约束 right-size(ROI)。** 7 阶段大干会和上线抢预算。修正排序为**最便宜最高 ROI 先行**:① 确定性 oracle(C2,便宜、立刻覆盖 exact 质量)② 在现有 runner 上做最小 cassette(C1/C4)③ H4-lite(失败→合成 case)。**重 judge/全覆盖/架构强制等"网证明了命中率(C3)"之后再投**。先让网自证价值,再扩。

**C9 — H3 的两个硬约束。** (a) grounding case 依赖 KB,**KB 一变 cassette 就过期** → 固定 KB 快照 或 cassette 化检索结果(检索本身也非确定:embedding/ranking)。(b) **tutorbot 自主壳可回放性是真难题**(有状态、bus/cron/heartbeat、多轮)→ 需 event-sourced 回放,v1 严重低估;修正:H3 先覆盖 chat 同步壳,tutorbot 壳**单独立项或窄范围**,不混进通用 cassette。

> **不确定性 + 验证/替代**:① cassette 归一化规则的"良性 vs 真实"边界——**验证**:先在 chat 同步壳 10 case 上试录试放、统计一周内的 key-miss 是良性还是真实,再决定归一化粒度;**替代**:若归一化做不稳,退到"决策层 golden(已有 P0.1,确定性、无 LLM)+ 定期 live 质量抽检",放弃全量 replay。② judge-人工一致率能否到 75-90%——**验证**:30 条种子先标;**替代**:达不到就缩到"确定性 oracle + 规则检查",judge 只作非阻断参考。③ 命中率指标需要时间积累——**验证**:从现在起记录每次"网拦住/漏掉"的真回归;**替代**:短期用"故意注入已知回归,网能否抓"做代理指标。

---

## 2. 七阶段路线图（按杠杆排序）

> 排序原则:H1 是 keystone(一通,H2/H3/H4 都解锁);H5/H6 横切;H7 在强网下安全收尾红利项。每阶段 = 独立 PR 线,独立验收。

### H1 — Record/Replay cassette 层（keystone）★最高杠杆
- **目标**:让全量轨迹 eval **确定性、免费、秒级、每次提交可跑**——无需 live key。
- **做法(grounded)**:在唯一 LLM 出入口拦截 `factory.complete` / `llm_stream` 与 tool 出口 `tool_registry.execute`,record 模式下把(model id、解码参数、messages 指纹 → 响应)和(tool name、args 指纹 → result)写 cassette;replay 模式注入记录值、零网络;cassette 按 case 存 `tests/fixtures/cassettes/<case>.json`。
- **验收/gate**:同一 case record 一次后,replay 模式重跑 N 次**逐字节一致**;`harness_trajectory_eval` 增 `--replay` 模式进 **quick gate**(不再是 deep/需 key);故意改壳逻辑 → replay diff 红。
- **分数提升**:回归网维 4→9——但**仅限编排/轨迹结构**(见 C1a:replay 冻结模型输出,验编排不验质量);质量门(H2)仍需**定期 live**,不是每次提交免费。H1 让 H3 的 200 case **编排/结构回归**每次提交确定性跑。
- 详化见 §3。

### H2 — 语义/质量打分(rubric + LLM-judge)
- **目标**:抓"答得对不对",不只"有没有答"。
- **做法(grounded)**:`services/benchmark/judge.py`——analytic rubric(逐 criterion:答案正确性 / grounding 忠实度 / exact 答案保真度 / scene 适配),judge 走**与被测不同模型家族**(被测 deepseek → judge 用 anthropic/openai,经 factory),**先用 ≥30 条人工标注 golden 对齐到 75–90% 一致**再放量;防 verbosity/position bias(简洁 rubric + 平衡排列)。judge 调用本身经 H1 cassette 回放确定化。
- **验收/gate**:judge-人工一致率 ≥80% 写入报告;rubric 分数进轨迹 golden;质量回归(某 criterion 掉分超阈值)→红。
- **分数提升**:语义打分维 2→9。
- **依赖**:H1(judge 调用要可回放)。

### H3 — 真实面覆盖 + 规模 + 轨迹度量
- **目标**:覆盖真实生产面,case 规模到 **200+**,加轨迹结构度量。
- **做法(grounded)**:扩 case 集覆盖 {RAG grounding 带真实 KB、exact by kind(mcq/free_text/case_study)端到端、tutorbot 自主壳、多轮连续性/follow-up、全部 lifecycle scene、低信息考试查询};录成 cassette;实现 `services/benchmark/trajectory_metrics.py`:step in-order/any-order 匹配、tool 选择准确率、参数正确性、convergence、groundedness(对 sources 的忠实度)。规模按调研:200 条给 3–5% 变化的统计置信。
- **验收/gate**:覆盖矩阵入册(每条生产面 ≥N case);轨迹度量进 golden;`harness_trajectory_eval --replay` 在 200+ case 上秒级全绿。
- **分数提升**:覆盖维 3→9。
- **依赖**:H1(否则 200 case live 跑不起)。

### H4 — 生产 trace 自喂养闭环
- **目标**:eval 语料从生产 trace 自动生长,不靠手写。
- **做法(grounded)**:接 `services/observability/failed_turn_promotion.py` → 把失败/低分 turn 的 trace **一键转 cassette + golden case**(trace-to-dataset);夜间 job 采样生产 trace 补充覆盖;PII 脱敏走既有 `source_compiler/pii_guard.py`。结构化 trace 字段(retrieval 分数/chunk 来源/tool 参数/延迟)确保可独立查询(已有 Langfuse + trace.py,补 schema)。
- **验收/gate**:构造一个失败生产 trace → 自动出现一条新回归 case + cassette;脱敏断言无敏感字段。
- **分数提升**:生产反馈维 2→9。
- **依赖**:H1(cassette)+ H3(case schema)。

### H5 — 架构级单一权威强制(超越 grep)
- **目标**:第二套 authority **写不出来/加载即失败**,而非靠扫字符串(你们 readiness R1 已指出"grep gate 不是安全边界")。
- **做法**:把 scene/grounding/exact/model 的 authority 入口收成**唯一可 import 的模块函数**,在执行壳侧加 **import-time / 运行时断言**(如壳模块禁止 import legacy detector;authority 决策对象带 provenance,reader 校验来源);`check_harness_authority.py` 升级为 AST 调用图分析(不止字符串)+ 运行时 guard 测试。
- **验收/gate**:构造"用 alias/间接 import 绕过"的改动 → guard 红;运行时断言测试覆盖旁路 reader。
- **分数提升**:单一权威维 7.5→9。
- **依赖**:无(可与 H1 并行)。

### H6 — 趋势盘 + 成本/延迟门 + 跨模型 eval
- **目标**:每次改动看质量/成本/延迟漂移,换模型有数据。
- **做法**:把 rubric 分数 / token 成本 / 延迟 / KV 命中率写 Langfuse 维度,出 harness 趋势盘;CI 加 **quality-delta gate**(质量掉超阈值阻断);model-swap 单点(已由 D5 guard 守)之上加**跨模型 eval**(同 case 集换 model 跑,对比报告)。
- **验收/gate**:一次 PR 的质量/成本/延迟 delta 可视;跨模型对比报告产出。
- **分数提升**:趋势维 4→8。
- **依赖**:H2(质量分)+ H1(确定化)。

### H7 — 红利项收尾(D2/D4/D5 全量)
- **目标**:在强网下安全完成此前 defer 的实现。
- **做法**:D2 chat 多跳(按 `2026-05-27-luban-harness-d2-bounded-iteration-implementation-plan.md` 执行,replay 断言由 H1+H3 提供);D4 tutorbot 壳 partition + KV 命中率(H6 测量);D5 轨迹 golden 扩到 H3 的 200+。
- **验收/gate**:各自 PR 的出口 gate;全量 replay 网绿。
- **分数提升**:红利维 5→8。
- **依赖**:H1/H2/H3/H6。

---

## 3. H1 keystone 详化(PR-ready)

> **执行前必读 v2 修正**:H1 必须吸收 **C1**(cassette key 归一化 turn_id/时间戳/uuid/顺序等易变字段;shim 断言拦截完整性;replay 验编排不验质量;cassette-miss 区分良性漂移 vs 真实变更)与 **C4**(优先做成 `services/benchmark/runner.py` 的可 replay 层,而非另起平行 harness)。下面的 cassette 数据结构是基础件,接入点按 C4 对齐现有 runner。**先按 C8 第 1 步只覆盖 chat 同步壳 ~10 case 验证归一化稳定性**,再扩。

**Goal:** record/replay cassette 层,让轨迹/编排回归 eval 从"deep/需 key"变成"quick/确定性回放"。

**Architecture:** 在单一 LLM/tool 出入口拦截非确定性事件;record 写 cassette,replay 注入;不改业务逻辑,只在出入口加可开关的拦截。

**File Structure:**
- Create `deeptutor/services/benchmark/cassette.py`:cassette 数据结构 + record/replay 存取(纯函数 + 文件 IO 分离)。
- Create `deeptutor/services/benchmark/llm_replay.py`:对 `factory.complete` / `llm_stream` 与 `tool_registry.execute` 的拦截 shim(record/replay/passthrough 三态,env/参数控制)。
- Create `tests/fixtures/cassettes/`(tracked):每 case 一个 `<case>.json`。
- Modify `scripts/run_harness_trajectory_eval.py`:加 `--record` / `--replay` 模式;replay 模式不需 keyed env。
- Modify `eval/gates.yaml`:`harness_trajectory_eval` 改 `--replay` 后归入 quick gate(确定性、无需 key)。
- Test `tests/services/benchmark/test_cassette.py`、`tests/services/benchmark/test_llm_replay.py`。

### Task H1.1 — cassette 数据结构 + 存取
- [ ] **Step 1: 失败测试** `tests/services/benchmark/test_cassette.py`
```python
from deeptutor.services.benchmark.cassette import Cassette, llm_key
def test_llm_key_is_stable_for_same_inputs():
    k1 = llm_key(model="deepseek-v4-flash", messages=[{"role":"user","content":"hi"}], params={"temperature":0,"max_tokens":10})
    k2 = llm_key(model="deepseek-v4-flash", messages=[{"role":"user","content":"hi"}], params={"max_tokens":10,"temperature":0})
    assert k1 == k2  # param order-independent
def test_cassette_records_and_replays_llm():
    c = Cassette()
    k = llm_key(model="m", messages=[{"role":"user","content":"q"}], params={})
    c.record_llm(k, "ANSWER")
    assert c.replay_llm(k) == "ANSWER"
def test_replay_miss_raises():
    import pytest
    with pytest.raises(KeyError):
        Cassette().replay_llm("absent")
```
- [ ] **Step 2: 跑红** `pytest tests/services/benchmark/test_cassette.py -v` → FAIL（模块不存在）
- [ ] **Step 3: 实现** `deeptutor/services/benchmark/cassette.py`
```python
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from typing import Any

def _digest(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

def llm_key(*, model: str, messages: list[dict[str, Any]], params: dict[str, Any]) -> str:
    # 录 model id + 解码参数 + messages 指纹（调研要求的三要素）
    return _digest({"model": model, "messages": messages, "params": params})

def tool_key(*, name: str, args: dict[str, Any]) -> str:
    return _digest({"name": name, "args": args})

@dataclass
class Cassette:
    llm: dict[str, str] = field(default_factory=dict)
    tool: dict[str, Any] = field(default_factory=dict)
    def record_llm(self, key: str, response: str) -> None: self.llm[key] = response
    def replay_llm(self, key: str) -> str:
        if key not in self.llm: raise KeyError(f"cassette miss (llm): {key}")
        return self.llm[key]
    def record_tool(self, key: str, result: Any) -> None: self.tool[key] = result
    def replay_tool(self, key: str) -> Any:
        if key not in self.tool: raise KeyError(f"cassette miss (tool): {key}")
        return self.tool[key]
    def to_json(self) -> str: return json.dumps({"llm": self.llm, "tool": self.tool}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    @classmethod
    def from_json(cls, text: str) -> "Cassette":
        d = json.loads(text); return cls(llm=d.get("llm", {}), tool=d.get("tool", {}))
```
- [ ] **Step 4: 跑绿** `pytest tests/services/benchmark/test_cassette.py -v` → PASS
- [ ] **Step 5: commit** `git add ... && git commit -m "feat: harness cassette record/replay store (H1.1)"`

### Task H1.2 — LLM/tool 拦截 shim（record/replay/passthrough）
- [ ] **Step 1: 失败测试** `tests/services/benchmark/test_llm_replay.py`：mock `factory.complete`,验证 record 模式存进 cassette、replay 模式不调底层只读 cassette、passthrough 模式直透。（完整测试代码在执行时按 factory 实际签名补全——`complete(prompt, system_prompt=..., messages=..., model=...) -> str`,`llm_stream(...)` async 生成器。）
- [ ] **Step 2–5**:实现 `llm_replay.py` 的三态 shim（monkeypatch `factory.complete`/`llm_stream` 与 `tool_registry.execute`,按 §1 录 model/params/tool id），跑红→绿→commit。

> **关键设计约束**:shim 只在 eval 入口启用(不污染生产路径);replay miss = 显式报错(测试暴露"轨迹变了"——正是回归信号);stream 回放按 chunk 还原或整段还原(取决于断言粒度,轨迹结构断言用整段即可)。

### Task H1.3 — 接入 trajectory eval 的 `--record` / `--replay`
- [ ] 改 `run_harness_trajectory_eval.py`:`--record`(keyed env,跑真实 + 写 cassette)、`--replay`(无 key,从 cassette 回放 + 断言结构/轨迹不变量)、默认 `--check` 保持现状兼容。
- [ ] 为现有 3 case 录 cassette → `tests/fixtures/cassettes/`,验证 `--replay` 多次跑逐字节一致。
- [ ] commit。

### Task H1.4 — gate 升级
- [ ] `eval/gates.yaml`:新增 `harness_trajectory_replay`(quick,`--replay`,无需 key);保留 `harness_trajectory_eval`(deep,`--record` 刷新 cassette)。
- [ ] 故意改 `_build_messages` 一处 → `--replay` 红(证明确定性网有效)→ 还原。
- [ ] contract_guard 满足(改 agentic 相关需同步 domain 测试,参 D4 先例)。
- [ ] commit。

**H1 出口 gate**:`harness_trajectory_replay` quick gate 绿、确定性(多跑逐字节一致)、无需 key;故意改壳 → 红。

---

## 4. Gating / 风险

- **Gating(v2/C8 right-sized,最便宜最高 ROI 先行)**:
  - **第 0 步(最便宜、立刻见效)**:确定性 oracle(C2)——exact 答案精确匹配,接进现有 `runner.py` 的 rag/case 套件;无需 cassette、无需 judge、无需 key。立刻给 exact 质量一张确定性网。
  - **第 1 步**:H1 最小 cassette,**做在现有 runner 上**(C4),先只覆盖 chat 同步壳 ~10 case(C9a),验证归一化稳不稳(见不确定性①)。
  - **第 2 步**:H4-lite——把 `failed_turn_promotion` 的 candidate **合成**成 case(C5),并开始记录 **命中率指标(C3)**。
  - **闸门**:**网证明了命中率(拦住过真回归、误报低)之后**,再投 H2 重 judge / H3 全覆盖 / H5 架构强制 / H6 趋势盘 / H7 红利。先自证价值再扩,不big-bang。
  - H5(AST import-graph 检查,C7)廉价,可任意时点并行。
  - 整体仍受原计划 §0 gate(launch-readiness 稳定);第 0–2 步均为 eval/guard 工具(不动生产 turn flow),可与 launch-readiness 并行,**只有 H7 碰生产壳**。
- **风险**:cassette 漂移(模型升级致 record 失效)→ `--record` 定期刷新 + cassette 带 model id 校验;judge 偏置 → 跨家族 + 人工对齐门;case 维护成本 → H4 生产自喂养摊薄;replay 与真实分叉 → 定期 `--record` 重录 + 抽样真实对比。
- **每阶段独立可回滚**:都是新增 eval/guard,FF/gate 可关。

## 5. Self-Review
- **覆盖**:7 维评分标尺每维都有对应 Phase(§0 表)。✓
- **依赖一致**:H1 keystone 先行,H2/H3/H4/H6/H7 显式依赖已标。✓
- **grounded**:每阶段做法挂调研来源(§1)。✓
- **可执行**:H1 详化到 bite-sized + 完整代码;H2–H7 为 scoped spec,开工时各用 writing-plans 展开(scope-check:多子系统拆分)。✓
