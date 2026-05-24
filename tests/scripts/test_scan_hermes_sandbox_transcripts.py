from __future__ import annotations

from pathlib import Path

from scripts.scan_hermes_sandbox_transcripts import scan_paths, main


def test_scan_paths_ignores_redacted_summary(tmp_path: Path) -> None:
    summary = tmp_path / "docs" / "sandbox" / "summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        "Hermes sandbox summary\n\nphone=[REDACTED_PHONE]\nemail=[REDACTED_EMAIL]\n",
        encoding="utf-8",
    )

    findings = scan_paths([summary])

    assert findings == []


def test_scan_paths_detects_common_pii(tmp_path: Path) -> None:
    transcript = tmp_path / "docs" / "sandbox" / "raw.md"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "学员姓名：张三\n手机号 13800138000\nemail: student@example.com\nopenid: oXabc1234567890\n",
        encoding="utf-8",
    )

    findings = scan_paths([transcript])

    assert {finding.kind for finding in findings} >= {"chinese_name_label", "phone", "email", "openid"}
    assert all(str(transcript) in finding.path for finding in findings)


def test_main_fails_when_sandbox_contains_raw_pii(tmp_path: Path, capsys) -> None:
    sandbox = tmp_path / "docs" / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / "raw.jsonl").write_text('{"mobile":"13900139000"}\n', encoding="utf-8")

    exit_code = main(["--path", str(sandbox)])

    assert exit_code == 1
    assert "PII finding" in capsys.readouterr().out
