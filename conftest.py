from __future__ import annotations


def pytest_addoption(parser) -> None:
    """Provide shared custom options expected by legacy integration tests."""
    parser.addoption(
        "--pipeline",
        action="store",
        default="llamaindex",
        help="RAG pipeline to test",
    )
