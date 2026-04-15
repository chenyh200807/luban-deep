from __future__ import annotations

import json
from datetime import datetime

from deeptutor.logging.context import bind_request_id, reset_request_id
from deeptutor.logging.logger import Logger


def test_json_file_logging_writes_structured_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_LOG_JSON", "1")

    request_id, token = bind_request_id("req-json")
    logger = Logger("JsonLogger", console_output=False, file_output=True, log_dir=tmp_path)

    try:
        logger.info("structured hello")
    finally:
        reset_request_id(token)
        logger.shutdown()

    lines = logger._log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    datetime.fromisoformat(entry["timestamp"])
    assert entry["level"] == "INFO"
    assert entry["module"] == "JsonLogger"
    assert entry["message"] == "structured hello"
    assert entry["request_id"] == request_id
