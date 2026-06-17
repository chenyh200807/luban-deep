#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_luban_human_validation_slice import score_human_labels, write_labels_csv_from_review_book
from scripts.score_luban_shadow_expansion_gate import _load_slices, run_expansion_gate


DEFAULT_HELDOUT_DIR = Path("artifacts/luban_human_validation_v1/po_slice_20260603_heldout")
DEFAULT_GATE_DIR = Path("artifacts/luban_agentic_grading_harness/shadow_expansion_gate_20260603")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _finding(result: dict[str, Any]) -> str:
    validation = result["human_validation"]["validation"]
    lines = [
        "# FINDING: Luban Held-out Post-label Gate",
        "",
        "> Directional/shadow. This is a post-human-label handoff runner, not production approval.",
        "",
        f"- status: `{result['status']}`",
        f"- human labels: filled `{validation['filled_label_count']}` / expected `{validation['expected_label_count']}`, "
        f"missing `{validation['missing_count']}`, invalid `{validation['invalid_count']}`, extra `{validation['extra_count']}`",
        f"- expansion gate: `{result['expansion_gate']['status']}`",
        "",
    ]
    if result.get("review_book_conversion"):
        conversion = result["review_book_conversion"]
        lines.extend(
            [
                "## Review Book Conversion",
                "",
                f"- parsed rows: `{conversion['parsed_row_count']}`",
                f"- template rows: `{conversion['template_row_count']}`",
                f"- matched rows: `{conversion['matched_row_count']}`",
                f"- extra rows: `{len(conversion.get('extra_rows') or [])}`",
                "",
            ]
        )
    if result["status"] == "blocked_human_labels_incomplete":
        lines.extend(
            [
                "## Next Action",
                "",
                "Complete all held-out human labels before interpreting model metrics.",
                "",
            ]
        )
    elif result["status"] == "pass":
        lines.extend(
            [
                "## Gate Result",
                "",
                "At least one shadow arm passed the directional expansion gate. Production runtime remains `not_approved`.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Gate Result",
                "",
                "No shadow arm passed the directional expansion gate. Inspect per-arm metrics and disagreements before changing runtime.",
                "",
            ]
        )
    return "\n".join(lines)


def run_post_label_gate(
    *,
    manifest_path: Path,
    labels_path: Path,
    review_book_path: Path | None,
    template_path: Path,
    write_labels_csv_path: Path,
    human_metrics_output_path: Path,
    slices_config_path: Path,
    expansion_output_dir: Path,
) -> dict[str, Any]:
    conversion = None
    resolved_labels_path = labels_path
    if review_book_path is not None:
        resolved_labels_path = write_labels_csv_path
        conversion = write_labels_csv_from_review_book(
            review_book_path=review_book_path,
            template_path=template_path,
            output_path=resolved_labels_path,
        )

    human_validation = score_human_labels(manifest_path=manifest_path, labels_path=resolved_labels_path)
    _write_json(human_metrics_output_path, human_validation)
    expansion_gate = run_expansion_gate(slices=_load_slices(slices_config_path), output_dir=expansion_output_dir)

    if not bool((human_validation.get("validation") or {}).get("is_complete")):
        status = "blocked_human_labels_incomplete"
    else:
        status = str(expansion_gate.get("status") or "fail")

    result = {
        "schema_version": "luban-heldout-post-label-gate.v0.1",
        "status": status,
        "human_validation": human_validation,
        "expansion_gate": expansion_gate,
        "production_runtime_decision": "not_approved",
    }
    if conversion:
        result["review_book_conversion"] = conversion

    _write_json(expansion_output_dir / "heldout_post_label_gate.json", result)
    (expansion_output_dir / "FINDING_heldout_post_label_gate.md").write_text(_finding(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run held-out human validation scoring and 64-answer shadow expansion gate.")
    parser.add_argument("--manifest", default=str(DEFAULT_HELDOUT_DIR / "internal_slice_manifest.json"))
    parser.add_argument("--labels", default=str(DEFAULT_HELDOUT_DIR / "po_labels_filled.csv"))
    parser.add_argument("--review-book", default=str(DEFAULT_HELDOUT_DIR / "阅卷审阅册_老师用.md"))
    parser.add_argument("--template", default=str(DEFAULT_HELDOUT_DIR / "po_labels_template.csv"))
    parser.add_argument("--write-labels-csv", default=str(DEFAULT_HELDOUT_DIR / "po_labels_filled.csv"))
    parser.add_argument("--human-metrics-output", default=str(DEFAULT_HELDOUT_DIR / "human_validation_metrics.json"))
    parser.add_argument("--slices-config", default=str(DEFAULT_GATE_DIR / "slices_config.json"))
    parser.add_argument("--expansion-output-dir", default=str(DEFAULT_GATE_DIR))
    parser.add_argument("--no-review-book", action="store_true", help="Read --labels directly instead of converting from the review book.")
    parser.add_argument("--filled-csv", action="store_true", help="Alias for --no-review-book; use when PO filled po_labels_filled.csv directly.")
    args = parser.parse_args()

    review_book_path = None if args.no_review_book or args.filled_csv else Path(args.review_book)
    result = run_post_label_gate(
        manifest_path=Path(args.manifest),
        labels_path=Path(args.labels),
        review_book_path=review_book_path,
        template_path=Path(args.template),
        write_labels_csv_path=Path(args.write_labels_csv),
        human_metrics_output_path=Path(args.human_metrics_output),
        slices_config_path=Path(args.slices_config),
        expansion_output_dir=Path(args.expansion_output_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "blocked_human_labels_incomplete":
        return 2
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
