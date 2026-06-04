from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def test_qwen_heldout_slice_defaults_to_all_available_heldout_samples(tmp_path: Path) -> None:
    out = tmp_path / "heldout"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_luban_qwen_heldout_slice.py",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    packet = json.loads((out / "agentic_grading_packet.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "internal_slice_manifest.json").read_text(encoding="utf-8"))
    label_rows = list(csv.DictReader((out / "po_labels_template.csv").open(encoding="utf-8")))

    assert len(packet["tasks"]) == 40
    assert len(manifest["selected_samples"]) == 40
    assert len(label_rows) == 175
    assert "qwen3.7-plus no-think production-config" in packet["purpose"]
    serialized_packet = json.dumps(packet, ensure_ascii=False)
    assert "human_hit" not in serialized_packet
    assert "human_score" not in serialized_packet
    assert (out / "FINDING_qwen_heldout_slice.md").exists()
