from __future__ import annotations

import logging

from deeptutor.logging.context import bind_request_id, reset_request_id
from deeptutor.logging.logger import ConsoleFormatter, FileFormatter, Logger


def test_logger_records_include_request_id_in_formatters(tmp_path) -> None:
    request_id, token = bind_request_id("req-abc")
    try:
        record = logging.LogRecord(
            name="deeptutor.API",
            level=logging.INFO,
            pathname=__file__,
            lineno=12,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.module_name = "API"
        assert request_id == "req-abc"
        assert "[req=req-abc]" in ConsoleFormatter().format(record)
        assert "[req=req-abc]" in FileFormatter().format(record)
    finally:
        reset_request_id(token)


def test_logger_attaches_request_id_to_emitted_records(tmp_path) -> None:
    logger = Logger("RequestCtx", console_output=False, file_output=True, log_dir=tmp_path)
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(getattr(record, "request_id", ""))

    logger.logger.addHandler(_CaptureHandler())

    request_id, token = bind_request_id("req-xyz")
    try:
        logger.info("hello")
    finally:
        reset_request_id(token)
        logger.shutdown()

    assert request_id == "req-xyz"
    assert captured == ["req-xyz"]
    assert "[req=req-xyz]" in logger._log_file.read_text(encoding="utf-8")
