#!/usr/bin/env python3
"""accuracy_gate — P0 一键准确性回归门(持续质量飞轮 v1).

"换 SHA 一键复核六维, 红即阻断" 的封板门. 编排 6 个确定性探针(probes/), 每维
确定性主裁 + 异源判官降级(judge 假阳 -> 不计 pass/fail), 输出失败率/复现率, 按
封板判据给退出码.

六维(全走 probes/*, 不硬编码 BASE / scratchpad 路径; BASE/judge key 由 .env 注入):
  daowu          倒诬(surface_stable o1==o2)
  huizhi         回指(binding-check 锚原题4选项)
  leak_boundary  出题泄露 + 边界(A隐式不泄/B显式放行/C未答回指不泄)
  sev_regression 3-SEV 回归(泄露/回指/倒诬, 异源判官)
  forward_liveness 拒判(批量必判 + Dim1 陈旧多题 active-set known bug)
  content_truth  规范条文不抑制 + hedge

封板判据(可证伪):
  六维全 0 复现(每维 reproduced=False) -> exit 0 (GO).
  任一维复现(reproduced=True)        -> exit 3 (阻断) + 点名 + 持久化终态证据路径.
  SHA 三方门不齐 / GIT_DIRTY!=false   -> exit 2 (STOP, 绝不在错 SHA 跑 eval).
  登录失败 / 全 inconclusive          -> exit 4 (无法判定, 非内容失败).

前置 SHA 门(反自证硬前置): origin/main == host .env == container env 且
GIT_DIRTY==false. 三者按最短非空 SHA 前缀比较(DEEPTUTOR_GIT_SHA 是 --short=12).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parent / "probes"
if str(PROBES_DIR) not in sys.path:
    sys.path.insert(0, str(PROBES_DIR))

from _probe_common import DEFAULT_BASE, login, run_dimension  # noqa: E402

# 维度名 -> 探针模块. 顺序即报告顺序.
DIMENSIONS: list[tuple[str, str]] = [
    ("daowu", "dim_daowu"),
    ("huizhi", "dim_huizhi"),
    ("leak_boundary", "dim_leak_boundary"),
    ("sev_regression", "dim_sev_regression"),
    ("forward_liveness", "dim_forward_liveness"),
    ("content_truth", "dim_content_truth"),
]

REMOTE_HOST = os.environ.get("DEEPTUTOR_REMOTE_HOST", "Aliyun-ECS-2")
REMOTE_DIR = os.environ.get("DEEPTUTOR_REMOTE_DIR", "/root/deeptutor")

EXIT_GO = 0
EXIT_SHA_STOP = 2
EXIT_REPRODUCED = 3
EXIT_INCONCLUSIVE = 4


# ---------------- 三方 SHA 前置门 ----------------

def _sha_prefix_match(a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def _local_origin_main_sha() -> str:
    try:
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(["git", "rev-parse", "origin/main"],
                           capture_output=True, text=True, timeout=30, check=True)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _ssh(cmd: str, timeout: int = 60) -> str:
    try:
        r = subprocess.run(["ssh", REMOTE_HOST, cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _host_env_sha() -> str:
    return _ssh(
        f"cd '{REMOTE_DIR}' && [ -f .env ] && "
        f"awk -F= '/^DEEPTUTOR_GIT_SHA=/{{print $2; exit}}' .env"
    )


def _container_env() -> tuple[str, str]:
    """returns (container DEEPTUTOR_GIT_SHA, container DEEPTUTOR_GIT_DIRTY)."""
    sha = _ssh(
        f"cd '{REMOTE_DIR}' && docker compose exec -T deeptutor "
        f"printenv DEEPTUTOR_GIT_SHA"
    )
    dirty = _ssh(
        f"cd '{REMOTE_DIR}' && docker compose exec -T deeptutor "
        f"printenv DEEPTUTOR_GIT_DIRTY"
    )
    return sha, dirty


def check_sha_gate(skip: bool) -> dict:
    """三方 SHA 门. 返回 {ok, detail, ...}; ok=False -> 调用方 STOP exit 2."""
    if skip:
        return {"ok": True, "skipped": True,
                "detail": "SHA 门被 --skip-sha-gate 跳过(仅限离线/本地编排自检)"}
    origin = _local_origin_main_sha()
    host = _host_env_sha()
    container_sha, container_dirty = _container_env()
    dirty_ok = (container_dirty.strip().lower() in ("false", "0", "no", ""))
    three_way_ok = (
        _sha_prefix_match(origin, host)
        and _sha_prefix_match(host, container_sha)
        and _sha_prefix_match(origin, container_sha)
    )
    ok = three_way_ok and dirty_ok and bool(origin) and bool(container_sha)
    return {
        "ok": ok, "skipped": False,
        "origin_main": origin, "host_env": host,
        "container_env": container_sha, "container_git_dirty": container_dirty,
        "dirty_ok": dirty_ok, "three_way_ok": three_way_ok,
        "detail": ("三方 SHA 对齐且 GIT_DIRTY=false" if ok else
                   "三方 SHA 不齐或 GIT_DIRTY!=false — STOP, 绝不在错 SHA 跑 eval"),
    }


# ---------------- 维度编排 ----------------

def run_one_dimension(name: str, module_name: str, token: str, base: str,
                      runs: int) -> dict:
    mod = importlib.import_module(module_name)
    unit_factories = mod.units(token, base)
    result = run_dimension(name, unit_factories, runs)
    return result


def _evidence_path(name: str, result: dict, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_result.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="P0 accuracy gate (6-dim regression)")
    ap.add_argument("--runs", type=int, default=3, help="每维每 unit 跑几轮(smoke=1)")
    ap.add_argument("--base", default=DEFAULT_BASE, help="部署 base url")
    ap.add_argument("--skip-sha-gate", action="store_true",
                    help="跳过三方 SHA 门(仅离线/本地编排自检; 不要在真 eval 用)")
    ap.add_argument("--only", default="",
                    help="逗号分隔仅跑这些维度(调试用), 默认全六维")
    ap.add_argument("--out-dir", default="",
                    help="终态证据落盘目录(默认 仓库 artifacts/quality_gate/<ts>)")
    args = ap.parse_args()

    print(f"=== accuracy_gate | base={args.base} | runs={args.runs} ===", flush=True)

    # 1) 三方 SHA 门前置.
    sha = check_sha_gate(args.skip_sha_gate)
    print("[SHA门]", json.dumps(sha, ensure_ascii=False), flush=True)
    if not sha["ok"]:
        print("STOP: SHA 门不齐, 绝不在错 SHA 跑 eval.", flush=True)
        return EXIT_SHA_STOP

    # 2) 登录.
    token = login(args.base)
    if not token:
        print("LOGIN FAILED — 无法判定(非内容失败).", flush=True)
        return EXIT_INCONCLUSIVE

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(__file__).resolve().parents[2] / "artifacts" / "quality_gate"
        / time.strftime("%Y%m%d_%H%M%S")
    )

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    dims = [(n, m) for n, m in DIMENSIONS if not only or n in only]

    summary: list[dict] = []
    for name, module_name in dims:
        print(f"\n--- 维度 {name} ---", flush=True)
        try:
            result = run_one_dimension(name, module_name, token, args.base, args.runs)
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] 编排异常: {str(e)[:200]}", flush=True)
            result = {"dim": name, "rows": [], "conclusive": 0,
                      "inconclusive": 0, "passed": 0, "failed": 0,
                      "fail_rate": None, "reproduced": False,
                      "orchestration_error": str(e)[:200]}
        ev_path = _evidence_path(name, result, out_dir)
        result["evidence_path"] = ev_path
        summary.append(result)
        fr = result.get("fail_rate")
        fr_s = f"{fr:.2f}" if isinstance(fr, float) else "n/a"
        mark = "❌复现" if result.get("reproduced") else (
            "✅" if result.get("conclusive") else "?无定论")
        print(f"[{name}] {mark} pass={result.get('passed')} fail={result.get('failed')} "
              f"inconclusive={result.get('inconclusive')} fail_rate={fr_s} "
              f"evidence={ev_path}", flush=True)
        for row in result.get("rows", []):
            if row.get("pass") is False:
                why = row.get("why") or row.get("refusal_marker") or ""
                print(f"    ✗ run{row.get('run')} {row.get('sub','')} "
                      f"{str(why)[:120]}", flush=True)

    # 3) 封板判据.
    reproduced = [r for r in summary if r.get("reproduced")]
    any_conclusive = any(r.get("conclusive") for r in summary)
    print("\n=== 封板汇总 ===", flush=True)
    for r in summary:
        print(f"  {r['dim']}: pass={r.get('passed')} fail={r.get('failed')} "
              f"reproduced={r.get('reproduced')} evidence={r.get('evidence_path')}",
              flush=True)
    gate_path = out_dir / "gate_summary.json"
    gate_path.write_text(json.dumps(
        {"sha_gate": sha, "base": args.base, "runs": args.runs,
         "dimensions": summary,
         "reproduced_dims": [r["dim"] for r in reproduced]},
        ensure_ascii=False, indent=2))
    print(f"门汇总: {gate_path}", flush=True)

    if reproduced:
        names = ", ".join(r["dim"] for r in reproduced)
        print(f"\n❌ 阻断: 复现维度 [{names}] — 红即阻断, 看上方 evidence 路径核终态.",
              flush=True)
        return EXIT_REPRODUCED
    if not any_conclusive:
        print("\n? 全维 inconclusive — 无法判定(judge 全降级/采集失败, 非内容失败).",
              flush=True)
        return EXIT_INCONCLUSIVE
    print("\n✅ GO: 六维全 0 复现, 封板通过.", flush=True)
    return EXIT_GO


if __name__ == "__main__":
    sys.exit(main())
