# DeepTutor — Agent-Native Architecture

## Overview

DeepTutor is an **agent-native** intelligent learning companion built around
a two-layer plugin model (Tools + Capabilities) with three entry points:
CLI, WebSocket API, and Python SDK.

## Contract Discipline

凡是涉及 turn/session/stream/replay/resume、聊天入口、TutorBot 接入、trace/observability 的改动，必须先遵守：

- [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
- [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)

硬约束：

- 只能有一个流式入口：`/api/v1/ws`
- 控制面 contract 走“总纲 + 专项 contract + machine-readable index”
- 只有对外稳定边界才允许升级为 contract / schema，普通内部实现不要滥加
- 禁止新增 `/api/v1/mobile/tutorbot/ws/...` 之类的专用聊天 WebSocket 路由

### Concept Discipline

以下规则用于约束概念层，防止系统长出两套重复语义：

- 同一业务事实只能有一个一等概念，禁止用多个名字表达同一件事。
- `TutorBot` 是唯一业务身份；不要再并行创造第二套执行身份，如历史遗留的 `mini_tutor`。
- `TutorBot` 只指完整、持久、可多实例、可心跳、可技能扩展的 TutorBot runtime；不要再把轻量默认绑定、入口 hint 或风格 profile 也叫作 `TutorBot`。
- `rag` 是唯一知识召回工具；知识库如 `construction-exam` 只是工具绑定，不要再包一层重复的“grounded mode”概念。
- `bot_runtime_defaults` 只表示 `bot_id -> 默认工具/默认知识库` 的绑定契约；它不是 TutorBot 本体，也不能承担执行引擎语义。
- `teaching_mode` 只表示表达风格或交互节奏，如 `fast / deep / smart`；不得承担知识链、身份路由、工具启用等职责。
- `product_surface`、`source`、`entry_role` 这类字段只表达入口表面信息，不得升级成新的业务身份。
- 允许存在兼容旧字段的 alias，但必须在入口层立即归一化，不能让 alias 继续参与执行决策。
- 如果发现两个模块、两个字段、两个模式名在表达同一语义，优先删除重复概念，而不是继续补同步逻辑。
- 任何新设计在进入代码前，先回答三个问题：
  1. 这是不是一个已经存在的概念换了个名字？
  2. 它表达的是身份、工具、知识库绑定、还是表现风格？
  3. 不新增这个概念，能否直接复用现有控制面？

## Execution Discipline

以下规则用于约束 agent 的执行方式；它们补充项目规则，但不替代 contract 约束。

### 0. First Principles

- 先回到问题本质，再决定实现方式。不要直接沿用现有代码路径、历史补丁或表面症状作为默认前提。
- 先分清楚：用户真正要解决的是什么问题，系统当前为什么会这样，约束来自业务、contract、兼容性，还是只是历史实现。
- 如果现有设计本身就是问题来源，应先指出根因，再决定是局部修复、结构调整，还是 contract 澄清。
- 不要把“目前代码就是这么写的”当成充分理由；要说明这样改在逻辑上为什么成立。

### 1. Think Before Coding

- 不要默默假设需求。开始实现前，先明确本次改动的假设、影响范围、涉及层次（API / Orchestrator / Capability / Tool / TutorBot / storage / trace）。
- 如果需求存在多种解释，不要静默选择其一；先列出你准备采用的解释和理由。
- 如果改动可能触碰 `turn/session/stream/replay/resume`、聊天入口、TutorBot、trace/observability，必须先检查 `CONTRACT.md` 和 `contracts/index.yaml`，再实施修改。
- 如果存在更简单的实现路径，先说明更简单的方案，不要直接走更重的方案。
- 遇到不清楚的地方，先指出具体不清楚的点；不要带着疑问直接编码。

### 2. Simplicity First

- 只写解决当前问题所需的最少代码，不为“以后可能会用”预留抽象、配置项、扩展点、额外 schema 或路由。
- 单次使用的逻辑不要提前抽象成通用框架，除非当前需求已经明确要求复用。
- 不要为了“灵活性”引入未被需求要求的参数、模式、状态机分支或层级。
- 不要为不现实的内部场景补充复杂错误处理；但对外稳定边界、contract 边界、用户输入边界仍需保持明确校验和错误语义。
- 改完后回看一次：如果 200 行能收敛成 50 行且不损失清晰度，就继续简化。

### 2.5 Less Is More

- 更少的代码、更少的分支、更少的状态，通常意味着更低的维护成本和更少的隐患。
- 优先删除多余复杂度，而不是在原有复杂度上继续叠加判断、兼容分支或“临时兜底”。
- 能通过澄清数据流、收敛责任边界、去掉例外分支来解决的问题，不要改成额外补丁层。
- 当两个方案都可行时，默认选择更短路径、更少依赖、更少概念、更容易验证的那个。

### 3. Surgical Changes

- 只修改与当前需求直接相关的代码；不要顺手重构相邻模块、改注释、改命名、重排 import、统一格式或清理历史问题。
- 保持现有代码风格和组织方式，除非本次任务明确要求调整。
- 只清理“因本次改动而产生”的无用 import、变量、函数或分支；不要顺手删除既有死代码。
- 如果发现无关但值得处理的问题，可以说明，但不要在同一改动里一起修。
- 每一处改动都应能直接追溯到本次需求；无法追溯的改动不要提交。
- 聊天相关能力必须继续复用统一流式入口 `/api/v1/ws`；禁止新增专用聊天 WebSocket 路由。

### 4. Goal-Driven Execution

- 开始前先把任务改写成可验证目标，而不是“差不多能用”。
- 修 bug 时：先写一个能复现问题的测试，再定位根因，最后修改实现让测试通过。
- 加功能时：先定义验收标准，再实现，并补足最小必要测试。
- 做重构时：先说明“行为不变”的验证方式，并确保改动前后相关测试通过。
- 多步骤任务先给出简短计划；每一步都要写明对应验证方式。
- 完成后明确汇报：改了什么、如何验证、还有哪些未覆盖风险。

### 5. Fix Root Causes, Not Symptoms

- 修复问题时必须优先寻找根因，不能只对表面症状做妥协性补丁。
- 禁止陷入“打补丁漩涡”：不要在原有例外上再套一层例外、在旧分支外再包一层特殊判断，或靠增加兜底逻辑掩盖真实问题。
- 如果一个问题反复出现，默认说明抽象、边界、状态流转或 contract 理解存在缺陷，应优先修正源头。
- 只有在明确受兼容性、发布窗口或外部依赖限制时，才允许临时缓解；但必须明确说明为什么不能一次治本，以及后续根治路径。
- 任何“临时修复”都必须被明确标记为权衡，而不能伪装成最终方案。

## Architecture

```
Entry Points:  CLI (Typer)  |  WebSocket /api/v1/ws  |  Python SDK
                    ↓                   ↓                   ↓
              ┌─────────────────────────────────────────────────┐
              │              ChatOrchestrator                    │
              │   routes to ChatCapability (default)             │
              │   or a selected deep Capability                  │
              └──────────┬──────────────┬───────────────────────┘
                         │              │
              ┌──────────▼──┐  ┌────────▼──────────┐
              │ ToolRegistry │  │ CapabilityRegistry │
              │  (Level 1)   │  │   (Level 2)        │
              └──────────────┘  └────────────────────┘
```

### Level 1 — Tools

Lightweight single-function tools the LLM calls on demand:

| Tool                | Description                                    |
| ------------------- | ---------------------------------------------- |
| `rag`               | Knowledge base retrieval (RAG)                 |
| `web_search`        | Web search with citations                      |
| `code_execution`    | Sandboxed Python execution                     |
| `reason`            | Dedicated deep-reasoning LLM call              |
| `brainstorm`        | Breadth-first idea exploration with rationale  |
| `paper_search`      | arXiv academic paper search                    |
| `geogebra_analysis` | Image → GeoGebra commands (4-stage vision pipeline) |

### Level 2 — Capabilities

Multi-step agent pipelines that take over the conversation:

| Capability       | Stages                                         |
| ---------------- | ---------------------------------------------- |
| `chat`           | responding (default, tool-augmented)           |
| `deep_solve`     | planning → reasoning → writing                 |
| `deep_question`  | ideation → evaluation → generation → validation |

### Playground Plugins

Extended features in `deeptutor/plugins/`:

| Plugin            | Type       | Description                          |
| ----------------- | ---------- | ------------------------------------ |
| `deep_research`   | playground | Multi-agent research + reporting     |

## CLI Usage

```bash
# Install CLI
pip install -r requirements/cli.txt && pip install -e .

# Run any capability (agent-first entry point)
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2=4" -t rag --kb my-kb
deeptutor run deep_question "Linear algebra" --config num_questions=5

# Interactive REPL
deeptutor chat

# Knowledge bases
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf

# Plugins & memory
deeptutor plugin list
deeptutor memory show

# API server (requires server.txt)
deeptutor serve --port 8001
```

## Key Files

| Path                          | Purpose                              |
| ----------------------------- | ------------------------------------ |
| `deeptutor/runtime/orchestrator.py` | ChatOrchestrator — unified entry     |
| `deeptutor/core/stream.py`          | StreamEvent protocol                 |
| `deeptutor/core/stream_bus.py`      | Async event fan-out                  |
| `deeptutor/core/tool_protocol.py`   | BaseTool abstract class              |
| `deeptutor/core/capability_protocol.py` | BaseCapability abstract class    |
| `deeptutor/core/context.py`         | UnifiedContext dataclass             |
| `deeptutor/runtime/registry/tool_registry.py` | Tool discovery & registration |
| `deeptutor/runtime/registry/capability_registry.py` | Capability discovery & registration |
| `deeptutor/runtime/mode.py`         | RunMode (CLI vs SERVER)              |
| `deeptutor/capabilities/`           | Built-in capability wrappers         |
| `deeptutor/tools/builtin/`          | Built-in tool wrappers               |
| `deeptutor/plugins/`                | Playground plugins                   |
| `deeptutor/plugins/loader.py`       | Plugin discovery from manifest.yaml  |
| `deeptutor_cli/main.py`             | Typer CLI entry point                |
| `deeptutor/api/routers/unified_ws.py` | Unified WebSocket endpoint         |

## Plugin Development

Create a directory under `deeptutor/plugins/<name>/` with:

```
manifest.yaml     # name, version, type, description, stages
capability.py     # class extending BaseCapability
```

Minimal `manifest.yaml`:
```yaml
name: my_plugin
version: 0.1.0
type: playground
description: "My custom plugin"
stages: [step1, step2]
```

Minimal `capability.py`:
```python
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

class MyPlugin(BaseCapability):
    manifest = CapabilityManifest(
        name="my_plugin",
        description="My custom plugin",
        stages=["step1", "step2"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        async with stream.stage("step1", source=self.name):
            await stream.content("Working on step 1...", source=self.name)
        await stream.result({"response": "Done!"}, source=self.name)
```

## Dependency Layers

```
requirements/cli.txt            — CLI full (LLM + RAG + providers + tools)
requirements/server.txt         — CLI + FastAPI/uvicorn (for Web/API)
requirements/math-animator.txt  — Manim addon (for `deeptutor animate`)
requirements/dev.txt            — Server + test/lint tools
```
