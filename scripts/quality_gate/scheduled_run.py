#!/usr/bin/env python3
"""scheduled_run — accuracy_gate 的可调度薄封装(持续质量飞轮 V2 第二步).

只做四件事, 判定逻辑单一权威仍在 accuracy_gate.py, 本脚本不重新实现任何判据:
  ① SHA 门前置检查(不齐 -> skipped:misaligned, 不往下跑, 不花钱).
  ② 对齐则 subprocess 跑 accuracy_gate.py --runs N --out-dir <本次目录>.
  ③ 读 gate_summary.json(v1 起就有, 不依赖任何后续 PR)产出 WEAK-GO 报告 +
    读 domains/quality-flywheel/metrics/accuracy.jsonl 拼六维趋势(样本不足如实说不足).
  ④ 给 domains/quality-flywheel/LOG.md 追加一行(shared brain 活动流).

退出码与 accuracy_gate.py 完全一致(单一口径, 不新发明):
  0 GO(结构判定, 非最终封板) | 2 SHA 门不齐(STOP) | 3 复现阻断(BLOCK) | 4 无法判定.

反自证: 本脚本任何输出都不自称"调度成功"/"门已通过", 只写退出码 + 证据路径这类
可核验事实; 报告顶部固定 WEAK-GO 横幅, 封板永远人在环.

高频/高 --runs 是真花钱: 默认 --runs 3, cadence(多久跑一次)由外部调度器(如
GitHub Actions cron)控制, 本脚本每次调用只跑一轮 accuracy_gate, 不做内部重试放大.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
GATE_SCRIPT = SCRIPT_DIR / "accuracy_gate.py"
DOMAIN_DIR = REPO_ROOT / "domains" / "quality-flywheel"
LOG_PATH = DOMAIN_DIR / "LOG.md"
METRICS_PATH = DOMAIN_DIR / "metrics" / "accuracy.jsonl"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from accuracy_gate import DEFAULT_BASE, check_sha_gate  # noqa: E402

EXIT_GO = 0
EXIT_SHA_STOP = 2
EXIT_REPRODUCED = 3
EXIT_INCONCLUSIVE = 4

VERDICT_WORD = {
    EXIT_GO: "WEAK-GO(结构判定, 待人盖封板)",
    EXIT_SHA_STOP: "SKIP(misaligned)",
    EXIT_REPRODUCED: "BLOCK",
    EXIT_INCONCLUSIVE: "INCONCLUSIVE",
}


def _read_metrics_rows(dim: str, limit: int = 5) -> list[dict]:
    """读 accuracy.jsonl 里某维度最近几行(纯观测, 不写)."""
    if not METRICS_PATH.exists():
        return []
    rows: list[dict] = []
    with METRICS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("dim") == dim:
                rows.append(row)
    return rows[-limit:]


def _trend_lines(dims: list[str]) -> list[str]:
    lines = ["## 趋势(metrics/accuracy.jsonl 历史)", ""]
    for dim in dims:
        rows = _read_metrics_rows(dim)
        if len(rows) < 2:
            lines.append(f"- `{dim}`: 样本不足(仅 {len(rows)} 行), 无法判趋势。")
            continue
        seq = " → ".join(r.get("gate_verdict", "?") for r in rows)
        lines.append(f"- `{dim}`: 最近 {len(rows)} 次 {seq}")
    return lines


def _append_log_line(ts: str, title_suffix: str, what: str, refs: str) -> None:
    date = ts[:10]
    entry = (
        f"## {date} · 调度 accuracy_gate{title_suffix} · #scheduled\n\n"
        f"What: {what}\n"
        f"Refs: {refs}\n\n"
    )
    DOMAIN_DIR.mkdir(parents=True, exist_ok=True)
    header = "# LOG · quality-flywheel（append-only 活动流）\n\n"
    existing = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else header
    idx = existing.find("\n## ")
    if idx == -1:
        new_content = existing.rstrip("\n") + "\n\n" + entry
    else:
        new_content = existing[: idx + 1] + entry + existing[idx + 1 :]
    LOG_PATH.write_text(new_content, encoding="utf-8")


def _write_report(report_path: Path, body: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(body, encoding="utf-8")


def _skip_report(sha: dict) -> str:
    return (
        "# accuracy_gate 调度报告 — SHA 门未对齐, 已跳过\n\n"
        "⚠️ **skipped:misaligned** — 三方 SHA 不齐, 绝不在错 SHA 上跑 eval, "
        "没有产生任何探针调用(不花钱)。\n\n"
        f"```json\n{json.dumps(sha, ensure_ascii=False, indent=2)}\n```\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="accuracy_gate 可调度薄封装(SHA 门前置 + WEAK-GO 报告 + LOG 记账)")
    ap.add_argument("--runs", type=int, default=3,
                     help="透传给 accuracy_gate.py 的 --runs(默认 3; 高频/高 runs 是真花钱, 别调高)")
    ap.add_argument("--base", default=DEFAULT_BASE, help="部署 base url")
    ap.add_argument("--report-dir", default="",
                     help="报告落盘目录(默认 artifacts/quality_gate/scheduled/<ts>/)")
    args = ap.parse_args()

    ts = datetime.now().isoformat()
    run_dir = Path(args.report_dir) if args.report_dir else (
        REPO_ROOT / "artifacts" / "quality_gate" / "scheduled" / time.strftime("%Y%m%d_%H%M%S")
    )
    report_path = run_dir / "report.md"

    # ① SHA 门前置检查 — 不齐立刻停, 不跑任何探针.
    sha = check_sha_gate(skip=False)
    print("[SHA门]", json.dumps(sha, ensure_ascii=False), flush=True)
    if not sha["ok"]:
        print("skipped:misaligned — SHA 门不齐, 不往下跑.", flush=True)
        _write_report(report_path, _skip_report(sha))
        _append_log_line(
            ts, "(skipped)",
            f"三方 SHA 不齐(origin={sha.get('origin_main', '')[:12]}, "
            f"host={sha.get('host_env', '')[:12]}, container={sha.get('container_env', '')[:12]}), "
            "跳过本次调度跑, 未产生任何探针调用。",
            f"`{report_path}`",
        )
        return EXIT_SHA_STOP

    # ② 对齐 -> subprocess 跑 accuracy_gate.py(权威判定逻辑在那边, 这里不重复).
    gate_out_dir = run_dir / "gate"
    cmd = [sys.executable, str(GATE_SCRIPT), "--runs", str(args.runs),
           "--base", args.base, "--out-dir", str(gate_out_dir)]
    print(f"[调度] 跑门: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    gate_log_path = run_dir / "accuracy_gate.stdout.log"
    _write_report(gate_log_path, proc.stdout + "\n" + proc.stderr)
    print(proc.stdout, flush=True)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, flush=True)
    exit_code = proc.returncode

    # ③ 读 gate_summary.json(v1 起就有)拼 WEAK-GO 报告 + 六维趋势.
    summary_path = gate_out_dir / "gate_summary.json"
    dims_summary: list[dict] = []
    if summary_path.exists():
        try:
            gate_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            dims_summary = gate_summary.get("dimensions", [])
        except json.JSONDecodeError:
            pass

    matrix_lines = [
        "| dim | pass | fail | inconclusive | fail_rate | reproduced | conclusive | evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in dims_summary:
        fr = r.get("fail_rate")
        fr_s = f"{fr:.2f}" if isinstance(fr, float) else "n/a"
        matrix_lines.append(
            f"| {r.get('dim')} | {r.get('passed')} | {r.get('failed')} | "
            f"{r.get('inconclusive')} | {fr_s} | {r.get('reproduced')} | "
            f"{r.get('conclusive')} | `{r.get('evidence_path', '')}` |"
        )

    dim_names = [r.get("dim") for r in dims_summary if r.get("dim")]
    trend = _trend_lines(dim_names) if dim_names else ["(六维编排未产出结果, 无趋势可读)"]

    verdict_word = VERDICT_WORD.get(exit_code, f"exit={exit_code}")
    report_body = (
        "# accuracy_gate 调度报告\n\n"
        "⚠️ **WEAK-GO — 结构判定, 非最终封板, 需人工确认后手动盖 GO。**\n\n"
        f"- 时间: {ts}\n"
        f"- base: {args.base}\n"
        f"- runs: {args.runs}\n"
        f"- SHA 门: {json.dumps(sha, ensure_ascii=False)}\n"
        f"- accuracy_gate 退出码: {exit_code}({verdict_word})\n"
        f"- 门原始日志: `{gate_log_path}`\n"
        f"- 门汇总: `{summary_path}`\n\n"
        "## 六维矩阵\n\n" + "\n".join(matrix_lines) + "\n\n"
        + "\n".join(trend) + "\n"
    )
    _write_report(report_path, report_body)

    # ④ LOG.md 记账(shared brain, 本脚本自己的职责, 不重复 accuracy_gate 已做的 metrics collector).
    deployed_sha = sha.get("container_env") or sha.get("origin_main") or ""
    block_dims = [r.get("dim") for r in dims_summary if r.get("reproduced")]
    what = (
        f"SHA={deployed_sha[:12]}, exit={exit_code}({verdict_word}), "
        f"六维: {', '.join(dim_names) if dim_names else 'n/a'}"
        + (f"; 复现阻断维度: {', '.join(block_dims)}" if block_dims else "")
        + "。metrics/accuracy.jsonl 的 append 由 accuracy_gate.py 自身完成(单一 collector 权威), "
          "本行只记调度活动。"
    )
    _append_log_line(ts, "", what, f"`{report_path}`")

    print(f"\n[调度报告] {report_path}", flush=True)
    print(f"[调度] 退出码 {exit_code}({verdict_word}) — 不代表已封板, 需人工核 evidence 后手动盖 GO。",
          flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
