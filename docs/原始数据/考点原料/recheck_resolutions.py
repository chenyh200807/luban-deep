#!/usr/bin/env python3
"""resolution 反自证核验器 (深 pack 裁决签发流水线 D1 基建)。

设计权威: docs/plan/鲁班移动端提分闭环/2026-07-04-luban-ai-adjudication-pipeline-plan.md §3

自证陷阱禁令的物理载体: **写 resolution 的进程 ≠ 判 resolution 有效的进程**。
本脚本独立于 adjudicate.py 的代码路径, 重放每包全部 resolution 的机器可核部分:

  * status=not_applicable: 必须能从 verified 解析出 ≥1 个 point_id 证据,
    重跑存在性 + quote 子串核, 必须仍命中 (无可解析证据 = fail-closed 不过)。
  * status=fixed: fixed_in 声称的 pack 正文文件必须实存; verified 引用的
    point_id 必须实存于源料; `quote='…'` / `直读含X` 证据 token 逐字命中源料 quote;
    `E##=语义` 声明与 ERROR_CODE_REGISTRY 直读对账。
  * 全 pack: verify_pack.py + verify_exam_anchors.py 双闸 +
    build_luban_pack_manifest.py --check 零漂移。

**exit 0 = 全部通过** —— 这是"该 pack 已裁决"的唯一凭据; 任何一项不过 exit 1
并打印精确失败项。owner 抽检的第一条命令就是本脚本。

用法::

    python3 recheck_resolutions.py G03 J01 S05
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # docs/原始数据/考点原料
PACK_DIR = HERE / "成品"
REPO = HERE.parents[2]
ERROR_CODES_PY = REPO / "deeptutor" / "contracts" / "error_codes.py"
MANIFEST_BUILDER = REPO / "scripts" / "build_luban_pack_manifest.py"

VALID_STATUSES = {"fixed", "not_applicable"}
PID_RE = re.compile(r"(?:ca|kc|cc|m35):[0-9A-Za-z_\-一-鿿]+(?::[0-9A-Za-z_\-]+)?")
# 只认贴着 quote= 的显式逐字证据 (松匹配会把散文引号误当证据, J01#2 实测校准)
QUOTE_CLAIM_RE = re.compile(r"quote[^=；;，,。'\"‘「」]{0,6}=\s*[‘“「']([^’”」']{2,})[’”」']")
# 「直读含『token』」式单 token 证据 (整体子串核, 不拆 '/')
CONTAINS_BRACKET_RE = re.compile(r"(?:直读含|完整含)\s*「([^」]+)」")
# 「直读含/完整含 X/Y/Z」式裸 token 列表证据 (按 '/' 拆分, J01#2 先例)
CONTAINS_BARE_RE = re.compile(r"(?:直读含|完整含)\s*([0-9A-Za-z一-鿿/·²．\.]+)")
# E##=语义 声明 × registry 对账 (取 registry label 为前缀判定)
REGISTRY_CLAIM_RE = re.compile(r"(?<![\w\-])([EM]\d{2})\s*=\s*([一-鿿]+)")
MD_FILE_RE = re.compile(r"([A-Z]\d{2}_[^\s(（;；]+\.md)")


def _load_quotes(pack_id: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    src = None
    for d in (PACK_DIR, HERE):
        hits = sorted(d.glob(f"_{pack_id}*_compiled_source.json"))
        if hits:
            src = hits[0]
            break
    exact: dict[str, str] = {}
    base: dict[str, list[str]] = {}
    if src is None:
        return exact, base
    for unit in json.loads(src.read_text(encoding="utf-8")).get("units", []):
        for sp in unit.get("scoring_points", []):
            pid = sp.get("point_id")
            if pid:
                q = str(sp.get("quote") or "")
                exact[pid] = q
                base.setdefault(pid.rsplit(":", 1)[0], []).append(q)
    return exact, base


def _pid_quotes(pid: str, exact: dict[str, str], base: dict[str, list[str]]) -> list[str] | None:
    if pid in exact:
        return [exact[pid]]
    if pid in base:
        return base[pid]
    root = pid.rsplit(":", 1)[0]
    return base.get(root)


def _fragments(token: str) -> list[str]:
    frags = [f.strip() for f in re.split(r"[…;；。]+", token) if len(f.strip()) >= 2]
    return frags or [token.strip()]


def _registry_labels() -> dict[str, str]:
    text = ERROR_CODES_PY.read_text(encoding="utf-8")
    return dict(re.findall(r'"([EM]\d{2})":\s*\{"label":\s*"([^"]+)"', text))


def recheck_resolution(pack_id: str, idx: int, row: dict, exact: dict, base: dict,
                       labels: dict[str, str]) -> list[str]:
    """单条 resolution 的机器可核重放; 返回失败原因列表 (空 = 通过)。"""
    fails: list[str] = []
    res = row.get("resolution")
    if not isinstance(res, dict):
        return [f"[{pack_id}#{idx}] resolution 非 dict"]
    status = res.get("status")
    fixed_in = str(res.get("fixed_in") or "")
    verified = str(res.get("verified") or "")
    if status not in VALID_STATUSES:
        fails.append(f"[{pack_id}#{idx}] status={status!r} 不合法 (只允许 fixed/not_applicable)")
    if not fixed_in.strip() or not verified.strip():
        fails.append(f"[{pack_id}#{idx}] fixed_in/verified 缺失或为空")
        return fails

    # point_id 存在性重放
    pids = sorted(set(PID_RE.findall(verified)))
    resolved_quotes: list[str] = []
    for pid in pids:
        quotes = _pid_quotes(pid, exact, base)
        if quotes is None:
            fails.append(f"[{pack_id}#{idx}] verified 引用 point_id {pid} 不存在于源料")
        else:
            resolved_quotes.extend(quotes)

    # token 子串核重放 (证据 token 逐字/逐片段命中被引 point 的 quote)
    corpus = "\n".join(resolved_quotes if resolved_quotes else exact.values())
    bare_scan_text = CONTAINS_BRACKET_RE.sub("", verified)
    tokens = (
        QUOTE_CLAIM_RE.findall(verified)
        + CONTAINS_BRACKET_RE.findall(verified)
        + [t for grp in CONTAINS_BARE_RE.findall(bare_scan_text) for t in grp.split("/") if t.strip()]
    )
    for tok in tokens:
        missing = [f for f in _fragments(tok) if f not in corpus]
        if missing:
            fails.append(f"[{pack_id}#{idx}] verified 证据「{tok[:40]}」子串核未命中: {missing}")

    # E##=语义 声明 × registry 直读对账
    for code, claimed in REGISTRY_CLAIM_RE.findall(verified):
        label = labels.get(code)
        if label is None:
            fails.append(f"[{pack_id}#{idx}] verified 引用错因码 {code} 不在 ERROR_CODE_REGISTRY")
        elif not claimed.startswith(label):
            fails.append(f"[{pack_id}#{idx}] {code} 语义声明「{claimed[:20]}」≠ registry「{label}」")

    if status == "not_applicable":
        # 反自证硬门: not_applicable 必须携带可重放的 point_id 证据
        if not pids:
            fails.append(f"[{pack_id}#{idx}] not_applicable 的 verified 无可解析 point_id 证据 (fail-closed)")
        elif not tokens:
            for pid in pids:
                quotes = _pid_quotes(pid, exact, base)
                if quotes is not None and not any(q.strip() for q in quotes):
                    fails.append(f"[{pack_id}#{idx}] {pid} 存在但 quote 为空, '存在且带quote'断言不成立")

    if status == "fixed":
        m = MD_FILE_RE.search(fixed_in)
        if m and not (PACK_DIR / m.group(1)).exists():
            fails.append(f"[{pack_id}#{idx}] fixed_in 声称的正文文件不存在: {m.group(1)}")

    return fails


def _run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return r.returncode, (out.splitlines() or ["(无输出)"])[-1]


def recheck_pack(pack_id: str, labels: dict[str, str]) -> list[str]:
    fails: list[str] = []
    jury_path = PACK_DIR / f"_{pack_id}_jury.json"
    packs = [p for p in sorted(PACK_DIR.glob(f"{pack_id}_*.md")) if "作答层样板" not in p.name]
    if not packs:
        return [f"[{pack_id}] pack 正文不存在"]
    pack_path = packs[0]
    if not jury_path.exists():
        return [f"[{pack_id}] jury sidecar 不存在 (fail-closed)"]
    try:
        rows = json.loads(jury_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"[{pack_id}] jury sidecar 解析失败: {exc}"]
    if not isinstance(rows, list):
        return [f"[{pack_id}] jury sidecar 非数组"]

    exact, base = _load_quotes(pack_id)
    n_res = 0
    for idx, row in enumerate(rows):
        if isinstance(row, dict) and row.get("resolution") is not None:
            n_res += 1
            fails.extend(recheck_resolution(pack_id, idx, row, exact, base, labels))

    # 双闸
    rc, tail = _run([sys.executable, str(HERE / "verify_pack.py"), str(pack_path)])
    print(f"  [{pack_id}] verify_pack exit={rc}: {tail}")
    if rc != 0:
        fails.append(f"[{pack_id}] verify_pack FAIL")
    rc, tail = _run([sys.executable, str(HERE / "verify_exam_anchors.py"), str(pack_path)])
    print(f"  [{pack_id}] verify_exam_anchors exit={rc}: {tail}")
    if rc != 0:
        fails.append(f"[{pack_id}] verify_exam_anchors FAIL")
    print(f"  [{pack_id}] resolution 重放 {n_res} 条, 失败 {sum(1 for f in fails if f.startswith(f'[{pack_id}#'))} 条")
    return fails


def main(argv: list[str]) -> int:
    if not argv:
        print("用法: python3 recheck_resolutions.py <pack_id> [<pack_id>…]", file=sys.stderr)
        return 2
    labels = _registry_labels()
    all_fails: list[str] = []
    for pack_id in [a.upper() for a in argv]:
        print(f"=== recheck: {pack_id} ===")
        all_fails.extend(recheck_pack(pack_id, labels))
    # manifest 漂移闸 (一次)
    rc, tail = _run([sys.executable, str(MANIFEST_BUILDER), "--check"])
    print(f"[manifest --check] exit={rc}: {tail}")
    if rc != 0:
        all_fails.append("manifest --check DRIFT")
    print("─" * 60)
    if all_fails:
        print("裁决: ❌ FAIL — 精确失败项:")
        for f in all_fails:
            print("  ✗", f)
        return 1
    print("裁决: ✅ PASS (全部 resolution 机器可核部分重放命中 + 双闸绿 + manifest 零漂移)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
