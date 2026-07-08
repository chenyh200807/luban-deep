from __future__ import annotations

import sys
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parents[2] / "scripts" / "quality_gate" / "probes"
if str(PROBES_DIR) not in sys.path:
    sys.path.insert(0, str(PROBES_DIR))

import dim_sev_regression as sev  # noqa: E402
from _probe_common import run_dimension  # noqa: E402


def _assistant(content: str) -> dict[str, str]:
    return {"role": "assistant", "content": content}


def test_daowu_surface_stable_is_deterministic_pass_even_if_judge_false_positive(
    monkeypatch,
) -> None:
    """No option-surface fork means the judge is only an audit signal, not the blocker."""

    same_surface = (
        "题干：屋面防水设防要求。\n"
        "A、一道\n"
        "B、两道\n"
        "C、三道\n"
        "D、四道\n"
    )

    monkeypatch.setattr(sev, "new_conv", lambda token, base: "cid-1")
    monkeypatch.setattr(sev, "turn", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        sev,
        "terminal_messages",
        lambda *args, **kwargs: [
            _assistant(same_surface),
            _assistant(same_surface),
            _assistant("判分：你选 C，但正确答案是 B。"),
        ],
    )
    monkeypatch.setattr(
        sev,
        "deepseek_judge",
        lambda *args, **kwargs: {
            "verdict": "DAOWU",
            "reason": "学生选C（三道），但正确答案是B（两道），判分正确，不存在倒诬。",
        },
    )

    result = sev._daowu("token", "https://example.test")

    assert result["pass"] is True
    assert result["inconclusive"] is False
    assert result["surface_stable"] is True
    assert result["judge"] == "DAOWU"


def test_daowu_false_positive_does_not_reproduce_dimension(monkeypatch) -> None:
    same_surface = (
        "题干：屋面防水设防要求。\n"
        "A、一道\n"
        "B、两道\n"
        "C、三道\n"
        "D、四道\n"
    )

    monkeypatch.setattr(sev, "new_conv", lambda token, base: "cid-aggregate")
    monkeypatch.setattr(sev, "turn", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        sev,
        "terminal_messages",
        lambda *args, **kwargs: [
            _assistant(same_surface),
            _assistant(same_surface),
            _assistant("判分：你选 C，但正确答案是 B。"),
        ],
    )
    monkeypatch.setattr(
        sev,
        "deepseek_judge",
        lambda *args, **kwargs: {"verdict": "DAOWU", "reason": "判分正确，不存在倒诬。"},
    )

    summary = run_dimension(
        "sev_regression",
        [lambda: sev._daowu("token", "https://example.test")],
        runs=1,
    )

    assert summary["failed"] == 0
    assert summary["reproduced"] is False


def test_daowu_surface_fork_with_judge_confirmation_is_blocking(monkeypatch) -> None:
    original_surface = (
        "题干：注册证书有效期。\n"
        "A、1年\n"
        "B、3年\n"
        "C、4年\n"
        "D、5年\n"
    )
    forked_surface = (
        "题干：注册证书有效期。\n"
        "A、5年\n"
        "B、1年\n"
        "C、3年\n"
        "D、4年\n"
    )

    monkeypatch.setattr(sev, "new_conv", lambda token, base: "cid-2")
    monkeypatch.setattr(sev, "turn", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        sev,
        "terminal_messages",
        lambda *args, **kwargs: [
            _assistant(original_surface),
            _assistant(forked_surface),
            _assistant("判分：你选 C，但正确答案是 B。"),
        ],
    )
    monkeypatch.setattr(
        sev,
        "deepseek_judge",
        lambda *args, **kwargs: {"verdict": "DAOWU", "reason": "判分依据用了原始选项面。"},
    )

    result = sev._daowu("token", "https://example.test")

    assert result["pass"] is False
    assert result["inconclusive"] is False
    assert result["surface_stable"] is False
    assert result["represented_new_order"] is True


def test_daowu_surface_fork_reproduces_dimension(monkeypatch) -> None:
    original_surface = (
        "题干：注册证书有效期。\n"
        "A、1年\n"
        "B、3年\n"
        "C、4年\n"
        "D、5年\n"
    )
    forked_surface = (
        "题干：注册证书有效期。\n"
        "A、5年\n"
        "B、1年\n"
        "C、3年\n"
        "D、4年\n"
    )

    monkeypatch.setattr(sev, "new_conv", lambda token, base: "cid-aggregate-fork")
    monkeypatch.setattr(sev, "turn", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        sev,
        "terminal_messages",
        lambda *args, **kwargs: [
            _assistant(original_surface),
            _assistant(forked_surface),
            _assistant("判分：你选 C，但正确答案是 B。"),
        ],
    )
    monkeypatch.setattr(
        sev,
        "deepseek_judge",
        lambda *args, **kwargs: {"verdict": "DAOWU", "reason": "判分依据用了原始选项面。"},
    )

    summary = run_dimension(
        "sev_regression",
        [lambda: sev._daowu("token", "https://example.test")],
        runs=1,
    )

    assert summary["failed"] == 1
    assert summary["reproduced"] is True
