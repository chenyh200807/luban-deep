from __future__ import annotations

from pathlib import Path

import deeptutor as _deeptutor

# 2026-08-07 实录:4 月的 pip install -e 留下 editable finder,兜底解析到别的
# checkout,静默吃错副本浪费三轮探针。测试进程必须只吃本仓库树内的 deeptutor;
# 有人重新 pip install -e 把毒环境带回来时,这里第一时间响。
if Path(__file__).resolve().parent not in Path(_deeptutor.__file__).resolve().parents:
    raise RuntimeError(
        f"deeptutor resolved outside this repo tree: {_deeptutor.__file__} "
        "(残留的 pip install -e?先 pip uninstall deeptutor)"
    )


def pytest_addoption(parser) -> None:
    """Provide shared custom options expected by legacy integration tests."""
    parser.addoption(
        "--pipeline",
        action="store",
        default="llamaindex",
        help="RAG pipeline to test",
    )
