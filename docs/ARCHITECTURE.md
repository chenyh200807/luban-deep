# DeepTutor Architecture Reference

> 本文件承载原 AGENTS.md 的架构/CLI/Key Files 事实章节(2026-07-12 下沉,同时修正了幽灵内容)。
> 行为约束不在这里——硬约束与启动门见 [AGENTS.md](../AGENTS.md)。
> 查具体代码结构优先用 CodeGraph(`codegraph explore "..."`),本文件只做入门地图。

## Overview

DeepTutor 是 agent-native 智能学习伴侣,两层插件模型(Tools + Capabilities),三个入口:
CLI、WebSocket API(唯一流式入口 `/api/v1/ws`)、Python SDK。

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

## Level 1 — Tools

LLM 按需调用的单功能工具(源码在 `deeptutor/tools/`):

| Tool                | Description                                    |
| ------------------- | ---------------------------------------------- |
| `rag`               | 唯一知识召回工具(RAG;知识库只是绑定)           |
| `web_search`        | Web search with citations                      |
| `code_execution`    | Sandboxed Python execution                     |
| `reason`            | Dedicated deep-reasoning LLM call              |
| `brainstorm`        | Breadth-first idea exploration                 |
| `paper_search`      | arXiv academic paper search                    |
| `geogebra_analysis` | Image → GeoGebra commands(vision pipeline)     |

## Level 2 — Capabilities

多步 agent 流水线(源码在 `deeptutor/capabilities/`,实际文件为准):

| Capability       | 说明                                            |
| ---------------- | ----------------------------------------------- |
| `chat`           | 默认,tool-augmented                             |
| `chat_mode`      | 表达风格/交互节奏(fast / deep / smart)          |
| `deep_solve`     | planning → reasoning → writing                  |
| `deep_question`  | ideation → evaluation → generation → validation |
| `deep_research`  | 多 agent 研究+报告                              |
| `tutorbot`       | TutorBot runtime(唯一业务身份,见 AGENTS.md Concept Discipline) |
| `math_animator`  | Manim 数学动画                                  |
| `visualize`      | 可视化                                          |

> 历史说明:`deeptutor/plugins/` 目录与 manifest.yaml 插件机制已不存在(deep_research
> 已并入 capabilities)。旧文档里的 "Playground Plugins / Plugin Development" 章节作废。

## Key Files(2026-07-12 逐一核验存在)

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
| `deeptutor/capabilities/`           | Built-in capabilities(含 tutorbot)  |
| `deeptutor_cli/main.py`             | Typer CLI entry point                |
| `deeptutor/api/routers/unified_ws.py` | Unified WebSocket endpoint(唯一)  |

## CLI Usage

```bash
# Install CLI
pip install -r requirements/cli.txt && pip install -e .

# Run any capability
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2=4" -t rag --kb my-kb
deeptutor run deep_question "Linear algebra" --config num_questions=5

# Interactive REPL
deeptutor chat

# Knowledge bases
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf

# API server (requires server.txt)
deeptutor serve --port 8001
```

完整子命令(plugin/memory/bot/session/notebook/provider/config 等)见 `deeptutor --help`。

## Dependency Layers

```
requirements/cli.txt            — CLI full (LLM + RAG + providers + tools)
requirements/server.txt         — CLI + FastAPI/uvicorn (for Web/API)
requirements/tutorbot.txt       — TutorBot runtime addon
requirements/math-animator.txt  — Manim addon (for `deeptutor animate`)
requirements/dev.txt            — Server + test/lint tools
requirements/runtime.lock       — locked runtime set
```
