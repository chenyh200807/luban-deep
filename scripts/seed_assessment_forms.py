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
    parser.add_argument(
        "--blueprint",
        default="diagnostic_v1",
        help="Blueprint version to seed (e.g. pass_readiness_architecture_v2).",
    )
    parser.add_argument(
        "--manifest",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "内容线表单 manifest(luban_s2_diagnostic_form.v2)路径,可重复传入多份;"
            "给定时逐题按 manifest 钉选导入(sha 校验,失配即 fail),"
            "不给时保持现行自动组卷。"
        ),
    )
    parser.add_argument(
        "--replicate-to-min",
        action="store_true",
        help="manifest 份数不足轮换下限(3)时,显式复制补足(过渡措施)。",
    )
    args = parser.parse_args()

    result = get_member_console_service().generate_and_persist_assessment_forms(
        args.blueprint,
        manifest_paths=args.manifest,
        replicate_to_min=args.replicate_to_min,
    )
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
