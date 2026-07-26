#!/usr/bin/env python3
"""asyncio 阻塞面扫描器 — 跨层追踪 `async def` 无 await 却触到同步 IO 的调用点。

**这不是 gate,是尺子。** enforcement=operational,永远 exit 0(除非 --check 且超基线)。
判据含启发式(跨模块按名字匹配),设成 pr_gate 会制造假红,而假红比没门更糟。

背景:2026-07-26 第一轮 asyncio 盲区侦察发现,单层 AST 判据
(「async def 函数体内直接出现 IO」)只能覆盖 2.4% —— IO 藏在第二、三跳。
本扫描器做 2 跳追踪,把覆盖率从 4 处提到 42 处。

用法:
    python scripts/scan_asyncio_blocking.py                # 人读报告
    python scripts/scan_asyncio_blocking.py --json         # 机器消费
    python scripts/scan_asyncio_blocking.py --check 42     # 超过基线才非 0(可选门)

诚实边界(结果是**下界**,不是全集):
  · 只做 2 跳;第 3 跳以上的 IO 只能靠跨模块名字启发式命中。
  · 跨模块调用按名字匹配(service/store/repo/client/dao/db/supabase),不做全仓符号解析。
  · 命中 ≠ 有 bug。纯内存缓存的 service 调用会误报;需人工抽验。

配套:agent-skills/deeptutor-evidence-discipline/references/blindspot-asyncio.md
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
TARGET = REPO / "deeptutor"

# 同步 IO 的直接形状(第 1 跳能看见的)
IO_RE = re.compile(
    r"\.(table|select|insert|upsert|update|delete|execute|executemany|fetchall|fetchone|commit|rpc)\("
    r"|requests\.|httpx\.(get|post|put|delete)\(|urlopen\(|sqlite3\.connect|psycopg|\.cursor\(\)"
)
# 跨模块数据访问的启发式:名字看起来在做持久化的对象
XMOD_RE = re.compile(
    r"\b(\w*(?:service|store|repo|repository|client|dao|db|supabase)\w*)\.\w+\(", re.I
)


def dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def scan_file(path: pathlib.Path) -> list[dict]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError):
        return []

    lines = src.splitlines()
    rel = str(path.relative_to(REPO))

    # 本文件内的同步函数索引:名字 -> (行号, 有无直接 IO, 有无跨模块数据访问)
    sync_fns: dict[str, tuple[int, bool, bool]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            seg = "\n".join(lines[n.lineno - 1 : (n.end_lineno or n.lineno)])
            sync_fns[n.name] = (n.lineno, bool(IO_RE.search(seg)), bool(XMOD_RE.search(seg)))

    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        body = list(ast.walk(node))
        if any(isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in body):
            continue  # 有 await = 不是本病

        stmts = [
            s for s in node.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        if len(stmts) < 3:
            continue  # 太短,噪音大

        seg = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
        direct_io = bool(IO_RE.search(seg))
        xmod = sorted(set(XMOD_RE.findall(seg)))

        hop2 = []
        for n in body:
            if isinstance(n, ast.Call):
                base = dotted(n.func).split(".")[-1]
                if base in sync_fns:
                    ln, has_io, has_x = sync_fns[base]
                    if has_io or has_x:
                        hop2.append(f"{base}@{ln}")

        if not (direct_io or xmod or hop2):
            continue

        depth = 1 if direct_io else (2 if (hop2 or xmod) else 3)
        out.append(
            {
                "file": rel,
                "line": node.lineno,
                "func": node.name,
                "depth": depth,
                "stmts": len(stmts),
                "hop2": hop2[:5],
                "xmod": xmod[:3],
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="机器可消费输出")
    ap.add_argument("--check", type=int, metavar="BASELINE",
                    help="命中数超过 BASELINE 时 exit 1(可选门;默认不设门)")
    args = ap.parse_args()

    hits: list[dict] = []
    files = 0
    for p in sorted(TARGET.rglob("*.py")):
        files += 1
        hits.extend(scan_file(p))

    if args.json:
        print(json.dumps({"scanned_files": files, "total": len(hits), "hits": hits},
                         ensure_ascii=False, indent=2))
    else:
        bydepth = collections.Counter(h["depth"] for h in hits)
        byfile = collections.Counter(h["file"] for h in hits)
        print(f"asyncio 阻塞面扫描 | 扫描 {files} 文件 | 命中 {len(hits)} 处(下界)\n")
        print("按 IO 深度:")
        print(f"  第 1 层(体内直接 IO)      : {bydepth[1]:3d}   ← 单层判据能抓到的")
        print(f"  第 2 层(调用的同步函数里) : {bydepth[2]:3d}   ← 单层判据漏掉的")
        print(f"  第 3 层(跨模块启发式)     : {bydepth[3]:3d}\n")
        print("命中最密集的文件:")
        for f, n in byfile.most_common(10):
            print(f"  {n:3d}  {f}")
        print("\n深度 2 样例(单层判据漏掉的):")
        for h in [x for x in hits if x["depth"] == 2][:10]:
            xs = ",".join(h["xmod"]) or "-"
            print(f"  {h['file']}:{h['line']}  {h['func']}()  2跳={len(h['hop2'])} 跨模块={xs}")
        print("\n注:命中 ≠ 有 bug。判据含启发式,纯内存 service 调用会误报,需人工抽验。")
        print("    修法参考 references/blindspot-asyncio.md 的 A0(先给默认 executor 定容再改 to_thread)。")

    if args.check is not None and len(hits) > args.check:
        print(f"\n[check] {len(hits)} > 基线 {args.check}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
