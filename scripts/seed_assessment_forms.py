#!/usr/bin/env python
from __future__ import annotations

import argparse
import json

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from deeptutor.services.member_console import get_member_console_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and persist diagnostic assessment forms.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    result = get_member_console_service().generate_and_persist_assessment_forms()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(
        "Assessment forms persisted: "
        f"blueprint={result['blueprint_version']} "
        f"forms={result['form_count']} "
        f"fallback_used={result['fallback_used']} "
        f"question_bank_size={result['question_bank_size']}"
    )


if __name__ == "__main__":
    main()
