from __future__ import annotations

import json
import sys
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "wechat_structured_renderer_cases.json"
)


def _load_case(case_name: str) -> dict:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in cases:
        if str(item.get("name") or "").strip() == case_name:
            return item
    raise SystemExit(f"fixture not found: {case_name}")


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/print_wechat_renderer_fixture_snippet.py <case_name>",
            file=sys.stderr,
        )
        return 1

    case = _load_case(sys.argv[1])
    sample = {
        "content": case.get("content") or "",
        "presentation": case.get("presentation") or {},
    }
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2)
    snippet = (
        "const page = getCurrentPages().slice(-1)[0];\n"
        "page.debugReplaceMessagesWithStructuredSample("
        f"{sample_json}"
        ");"
    )
    print(snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
