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

---

## 1. 世界级实践基线（调研依据，2026-05 检索）

本路线图不是凭空设计,锚定以下实践:

- **Record/Replay 是 eval 确定性的前提**:只录非确定性事件(LLM 调用、tool 结果),确定性部分回放时注入记录的输入;必须录 **model id + 解码参数(temperature/top_p/max_tokens/penalties) + tool id→stub**。参考 `llm-test-harness`(cassette + eval scoring + regression)。来源:[Get Experience from Practice: LLM Agents with Record & Replay (arXiv 2505.17716)](https://arxiv.org/html/2505.17716v1)、[Trustworthy AI Agents: Deterministic Replay](https://www.sakurasky.com/blog/missing-primitives-for-trustworthy-ai-part-8/)、[llm-test-harness (PyPI)](https://pypi.org/project/llm-test-harness/)。
- **LLM-as-judge 用 analytic rubric**(逐 criterion 打分,非单一不透明分,便于回归定位);**先用 golden 对齐人工 75–90% 再放量**;**judge 用不同模型家族**避免自增强偏置;防 position/verbosity bias(平衡排列、bias 校正)。来源:[Rubric-Based Evals & LLM-as-a-Judge (Masood)](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)、[Arize: LLM as a Judge](https://arize.com/llm-as-a-judge/)、[Position Bias in Rubric-Based LLM-as-a-Judge (arXiv 2602.02219)](https://arxiv.org/pdf/2602.02219)。
- **生产 trace → 数据集闭环**:生产失败一键变回归 case;**结构化 trace 是前提**(retrieval 分数/chunk 来源/tool 参数/延迟可独立查询);规模 **50 抓大回归 / 200 抓 3–5% 变化 / >500 边际递减**。来源:[Braintrust: LLM evaluation guide](https://www.braintrust.dev/articles/llm-evaluation-guide)、[LangChain: LLM Evals](https://www.langchain.com/articles/llm-evals)、[Building a Golden Dataset (Maxim)](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/)。
- **轨迹度量**:step 匹配(exact/in-order/any-order)、step-level precision/recall、tool 选择准确率、参数正确性、convergence、path efficiency、对召回来源的 faithfulness/groundedness。来源:[Beyond the Final Answer: Evaluating Reasoning Trajectories (arXiv 2510.02837)](https://arxiv.org/pdf/2510.02837)、[Agent Evaluation Platforms 2025 (Maxim)](https://www.getmaxim.ai/articles/top-agent-evaluation-platforms-in-2025-the-definitive-enterprise-guide/)。

---

## 2. 七阶段路线图（按杠杆排序）

> 排序原则:H1 是 keystone(一通,H2/H3/H4 都解锁);H5/H6 横切;H7 在强网下安全收尾红利项。每阶段 = 独立 PR 线,独立验收。

### H1 — Record/Replay cassette 层（keystone）★最高杠杆
- **目标**:让全量轨迹 eval **确定性、免费、秒级、每次提交可跑**——无需 live key。
- **做法(grounded)**:在唯一 LLM 出入口拦截 `factory.complete` / `llm_stream` 与 tool 出口 `tool_registry.execute`,record 模式下把(model id、解码参数、messages 指纹 → 响应)和(tool name、args 指纹 → result)写 cassette;replay 模式注入记录值、零网络;cassette 按 case 存 `tests/fixtures/cassettes/<case>.json`。
- **验收/gate**:同一 case record 一次后,replay 模式重跑 N 次**逐字节一致**;`harness_trajectory_eval` 增 `--replay` 模式进 **quick gate**(不再是 deep/需 key);故意改壳逻辑 → replay diff 红。
- **分数提升**:回归网维 4→9;解锁 H2/H3/H4 的"每次提交全量跑"。
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

**Goal:** record/replay cassette 层,让 `harness_trajectory_eval` 从"deep/需 key"变成"quick/确定性回放"。

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

- **Gating**:H1 先行(其余依赖它);H5 可与 H1 并行;H2→H3→H4 顺序;H6 在 H2 后;H7 最后。整体仍受原计划 §0 gate(launch-readiness 稳定)——但 H1–H6 多为 eval/guard 工具(不动生产 turn flow),可在 launch-readiness 推进的同时并行,**H7 才碰生产壳**。
- **风险**:cassette 漂移(模型升级致 record 失效)→ `--record` 定期刷新 + cassette 带 model id 校验;judge 偏置 → 跨家族 + 人工对齐门;case 维护成本 → H4 生产自喂养摊薄;replay 与真实分叉 → 定期 `--record` 重录 + 抽样真实对比。
- **每阶段独立可回滚**:都是新增 eval/guard,FF/gate 可关。

## 5. Self-Review
- **覆盖**:7 维评分标尺每维都有对应 Phase(§0 表)。✓
- **依赖一致**:H1 keystone 先行,H2/H3/H4/H6/H7 显式依赖已标。✓
- **grounded**:每阶段做法挂调研来源(§1)。✓
- **可执行**:H1 详化到 bite-sized + 完整代码;H2–H7 为 scoped spec,开工时各用 writing-plans 展开(scope-check:多子系统拆分)。✓
