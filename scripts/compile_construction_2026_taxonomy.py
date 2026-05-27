from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from deeptutor.services.taxonomy.learning_topic_resolver import compile_taxonomy_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile FINAL_CLEANED_TAXONOMY2026.json into DeepTutor topic authority.")
    parser.add_argument("--source", required=True, help="Path to FINAL_CLEANED_TAXONOMY2026.json")
    parser.add_argument(
        "--output",
        default="deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json",
        help="Compiled taxonomy output path",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser()
    raw = source.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    compiled = compile_taxonomy_payload(
        payload,
        source_path=str(source),
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(compiled, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"compiled {len(compiled['nodes'])} taxonomy nodes -> {output}")


if __name__ == "__main__":
    main()
