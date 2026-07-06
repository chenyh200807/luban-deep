#!/usr/bin/env python3
"""Tier-0 确定性预裁器 (深 pack 裁决签发流水线 D1 基建).

设计权威: docs/plan/鲁班移动端提分闭环/2026-07-04-luban-ai-adjudication-pipeline-plan.md §1 Tier-0

对 pack jury sidecar 里每条「高可信且无 resolution」的 issue, 先用零 LLM 检查回答
"jury 说的现象是否为真" (J01 #3 先例: jury ≠ ground truth, 机器闸凌驾 LLM 共识):

  a) point_id / quote 子串核: issue 声称"无 quote 支持 / quote 未含 X / 源料中未找到"
     → 直读 _<ID>_compiled_source.json 对应 point_id 的 quote 做子串匹配。
     命中 → jury 断言被证伪 → 候选 resolution(status=not_applicable)。
  b) 错因码整表对账: pack 正文全部 E/M 码引用 × ERROR_CODE_REGISTRY 直读,
     输出对账表 (只报告, 不改写; 供 Tier-2 语义裁决用)。
  c) 真题锚复核: 调 verify_exam_anchors.py, 记录 exit code。

铁律 (内建, 不可绕):
  * 绝不写 status=fixed —— 那是 Tier-1 手术编辑的事, 本脚本只可能写 not_applicable。
  * 绝不升色 / 绝不动 pack 正文 —— 本脚本对 pack .md 只读。
  * resolution.verified 必须含可独立重跑的确定性证据语句 (point_id + 命中 token)。
  * 默认 dry-run 只报告; 只有 --write-resolutions 才落盘 sidecar。
  * flagged_by 命名归一只在读取时内存中做, 不重写 sidecar。

用法::

    python3 adjudicate.py G02                       # 单包 Tier-0 报告 (dry-run)
    python3 adjudicate.py --all                     # 全量 Tier-0 报告
    python3 adjudicate.py G02 --write-resolutions   # 确定性证伪命中的落盘 not_applicable
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent          # docs/原始数据/考点原料
PACK_DIR = HERE / "成品"
REPO = HERE.parents[2]
ERROR_CODES_PY = REPO / "deeptutor" / "contracts" / "error_codes.py"
VERIFY_EXAM_ANCHORS = HERE / "verify_exam_anchors.py"

# ── flagged_by 命名归一 (读取时内存归一, 不重写 sidecar) ────────────────────
FLAGGED_BY_CANON = {
    "gpt-5.5(codex)": "GPT-5.5(Codex)",
    "gpt-5.5-codex": "GPT-5.5(Codex)",
    "gpt-5.5": "GPT-5.5(Codex)",
    "qwen-3.7-max": "Qwen-3.7-Max",
    "qwen-max": "Qwen-3.7-Max",
    "qwen": "Qwen-3.7-Max",
    "deepseek-v4-pro": "DeepSeek-V4-Pro",
    "deepseek": "DeepSeek-V4-Pro",
}


def canon_flagger(name: str) -> str:
    return FLAGGED_BY_CANON.get(str(name).strip().lower(), str(name).strip())


# ── 源料读取 ────────────────────────────────────────────────────────────────
POINT_ID_RE = re.compile(r"(?:ca|kc|cc|m35):[0-9A-Za-z_\-一-鿿]+(?::[0-9A-Za-z_\-]+)?")

# issue 文本里的"缺失断言"两族: ①点位不存在 ②quote 不含 X
ABSENCE_NOT_FOUND_RE = re.compile(r"未找到|不存在|源料中未提供|缺少锚|无法定位")
ABSENCE_NO_QUOTE_RE = re.compile(
    r"无\s*quote|quote\s*未含|未提供\s*quote|缺\s*quote|无对应教材\s*quote"
    r"|无\s*.{0,4}quote\s*支撑|quote\s*不支持|quote\s*支撑不足|未包含"
)
# issue 文本里的引号包裹 token (声称缺失的数值/关键词)
QUOTED_TOKEN_RE = re.compile(r"[‘“「']([^’”」']{1,40})[’”」']")


def find_compiled_source(pack_id: str) -> Path | None:
    for d in (PACK_DIR, HERE):
        hits = sorted(d.glob(f"_{pack_id}*_compiled_source.json"))
        if hits:
            return hits[0]
    return None


def load_quote_index(pack_id: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """point_id → quote 全索引; 同时给出去尾 :idx 的基 id → quotes 列表。"""
    src = find_compiled_source(pack_id)
    exact: dict[str, str] = {}
    base: dict[str, list[str]] = {}
    if not src:
        return exact, base
    data = json.loads(src.read_text(encoding="utf-8"))
    for unit in data.get("units", []):
        for sp in unit.get("scoring_points", []):
            pid = sp.get("point_id")
            if not pid:
                continue
            quote = str(sp.get("quote") or "")
            exact[pid] = quote
            base.setdefault(pid.rsplit(":", 1)[0], []).append(quote)
    return exact, base


def resolve_pid_quotes(pid: str, exact: dict[str, str], base: dict[str, list[str]]) -> list[str] | None:
    """pid 存在 → 该点 quote 列表; 不存在 → None。"""
    if pid in exact:
        return [exact[pid]]
    if pid in base:
        return base[pid]
    stripped = pid.rsplit(":", 1)[0]
    if stripped in base:
        return base[stripped]
    return None


def token_fragments(token: str) -> list[str]:
    """省略号/句读切分, 每片段独立子串核 (J01 #3 先例的'…'证据格式)。"""
    frags = [f.strip() for f in re.split(r"[…;；。]+", token) if len(f.strip()) >= 2]
    return frags or [token.strip()]


def token_hits(token: str, quotes: list[str]) -> bool:
    joined = "\n".join(quotes)
    return all(frag in joined for frag in token_fragments(token))


# ── Tier-0a: 单条 issue 确定性预裁 ─────────────────────────────────────────
def adjudicate_issue(row: dict[str, Any], exact: dict[str, str], base: dict[str, list[str]]) -> dict[str, Any]:
    issue_text = str(row.get("issue", ""))
    scan_text = " ".join(str(row.get(k, "")) for k in ("issue", "location", "fix"))
    pids = sorted(set(POINT_ID_RE.findall(scan_text)))
    tokens = [t for t in QUOTED_TOKEN_RE.findall(issue_text) if not POINT_ID_RE.fullmatch(t)]
    claims_not_found = bool(ABSENCE_NOT_FOUND_RE.search(issue_text))
    claims_no_quote = bool(ABSENCE_NO_QUOTE_RE.search(issue_text))

    detail: dict[str, Any] = {
        "point_ids": {},
        "tokens": {},
        "claims_not_found": claims_not_found,
        "claims_no_quote": claims_no_quote,
    }
    all_quotes: list[str] = []
    all_pids_exist = bool(pids)
    for pid in pids:
        quotes = resolve_pid_quotes(pid, exact, base)
        detail["point_ids"][pid] = {
            "exists": quotes is not None,
            "has_quote": bool(quotes and any(q.strip() for q in quotes)),
        }
        if quotes is None:
            all_pids_exist = False
        else:
            all_quotes.extend(quotes)

    corpus = all_quotes if all_quotes else list(exact.values())
    all_tokens_hit = bool(tokens)
    for tok in tokens:
        hit = token_hits(tok, corpus)
        detail["tokens"][tok] = hit
        if not hit:
            all_tokens_hit = False

    # 证伪判定 (保守: 只有 jury 的缺失断言被直读推翻才 REFUTED)
    verdict = "UNDECIDED→Tier-1/2"
    evidence: list[str] = []
    if claims_not_found and pids and all_pids_exist and all(
        detail["point_ids"][p]["has_quote"] for p in pids
    ):
        verdict = "REFUTED(jury断言被证伪)"
        evidence = [f"{p} 存在且带 quote" for p in pids]
    elif claims_no_quote and pids and all_pids_exist and tokens and all_tokens_hit:
        verdict = "REFUTED(jury断言被证伪)"
        evidence = [f"{p} quote 直读含「{t}」" for p in pids for t in tokens]
    elif (claims_no_quote or claims_not_found) and pids and all_pids_exist and tokens and not all_tokens_hit:
        verdict = "CONFIRMED(现象为真)→Tier-1默认降色"

    detail["verdict"] = verdict
    detail["evidence"] = evidence
    return detail


def build_resolution(pack_id: str, evidence: list[str]) -> dict[str, str]:
    """J01 先例格式。铁律: status 只可能是 not_applicable, 永不 fixed。"""
    today = datetime.date.today().isoformat()
    return {
        "status": "not_applicable",
        "fixed_in": "无需改正文——jury 断言被 Tier-0 确定性核验证伪 (adjudicate.py)",
        "verified": (
            f"{today} 确定性核验：{'；'.join(evidence)}，jury 断言系幻觉，"
            f"机器闸凌驾 LLM 共识（可重跑：python3 docs/原始数据/考点原料/adjudicate.py {pack_id}）"
        ),
    }


# ── Tier-0b: 错因码整表对账 ────────────────────────────────────────────────
NON_CODE = {"M35", "M15", "M20", "M25", "M30"}  # 同 verify_pack.py: 撞形非码 token
CODE_RE = re.compile(r"(?<![\w\-])([EM]\d{2})(?![\w])")


def load_registry_labels() -> dict[str, str]:
    text = ERROR_CODES_PY.read_text(encoding="utf-8")
    return dict(re.findall(r'"([EM]\d{2})":\s*\{"label":\s*"([^"]+)"', text))


def error_code_reconciliation(pack_path: Path) -> list[tuple[str, str, bool]]:
    text = pack_path.read_text(encoding="utf-8")
    labels = load_registry_labels()
    cited = sorted(set(CODE_RE.findall(text)) - NON_CODE)
    return [(c, labels.get(c, "—"), c in labels) for c in cited]


# ── Tier-0c: 真题锚复核 ────────────────────────────────────────────────────
def run_exam_anchor_gate(pack_path: Path) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(VERIFY_EXAM_ANCHORS), str(pack_path)],
        capture_output=True, text=True,
    )
    tail = (r.stdout.strip().splitlines() or ["(无输出)"])[-1]
    return r.returncode, tail


# ── Tier-2 面板调度 (D1 只留桩) ────────────────────────────────────────────
def dispatch_panel(pack_id: str, issue_index: int) -> None:
    """TODO(D2+): 异源 AI 面板调度 —— 设计 §2 模型矩阵:
    GLM-5.2 每案必到 (唯一非生产/非 jury 源) + 第二签; 事实类须教材原文 quote 命中;
    flagger 不得裁决自己 flag 的条目。复用 jury_audit.py 的 key 加载/调用件。"""
    raise NotImplementedError("Tier-2 面板调度尚未实现 (D1 只做 Tier-0 确定性预裁)")


# ── 主流程 ─────────────────────────────────────────────────────────────────
def find_pack_file(pack_id: str) -> Path | None:
    hits = [p for p in sorted(PACK_DIR.glob(f"{pack_id}_*.md")) if "作答层样板" not in p.name]
    return hits[0] if hits else None


def adjudicate_pack(pack_id: str, write: bool) -> dict[str, Any]:
    print(f"\n{'=' * 66}\n=== Tier-0 确定性预裁: {pack_id} ===")
    jury_path = PACK_DIR / f"_{pack_id}_jury.json"
    pack_path = find_pack_file(pack_id)
    summary = {"pack": pack_id, "high_unresolved": 0, "refuted": 0, "confirmed": 0, "written": 0}
    if not pack_path:
        print("⚠ pack 正文不存在, 跳过")
        return summary
    if not jury_path.exists():
        print("⚠ jury sidecar 不存在, 跳过")
        return summary
    try:
        rows = json.loads(jury_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"✗ jury sidecar 解析失败 (fail-closed, 需先修复): {exc}")
        summary["high_unresolved"] = -1
        return summary

    exact, base = load_quote_index(pack_id)
    print(f"源料 quote 索引: {len(exact)} 个 point_id")

    # a) 逐条高可信未决 issue
    dirty = False
    for idx, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("confidence") != "高可信":
            continue
        if isinstance(row.get("resolution"), dict):
            continue
        summary["high_unresolved"] += 1
        flaggers = sorted({canon_flagger(n) for n in row.get("flagged_by", [])})
        detail = adjudicate_issue(row, exact, base)
        print(f"\n[#{idx}] {row.get('issue', '')[:80]}")
        print(f"  flagged_by(归一): {flaggers}")
        for pid, st in detail["point_ids"].items():
            print(f"  point_id {pid}: exists={st['exists']} has_quote={st['has_quote']}")
        for tok, hit in detail["tokens"].items():
            print(f"  token 「{tok[:40]}」: {'命中' if hit else '未命中'}")
        print(f"  → {detail['verdict']}")
        if detail["verdict"].startswith("REFUTED"):
            summary["refuted"] += 1
            resolution = build_resolution(pack_id, detail["evidence"])
            if write:
                row["resolution"] = resolution
                dirty = True
                summary["written"] += 1
                print(f"  落盘 resolution: {resolution['verified'][:100]}…")
            else:
                print(f"  (dry-run) 候选 resolution: {resolution['verified'][:100]}…")
        elif detail["verdict"].startswith("CONFIRMED"):
            summary["confirmed"] += 1

    if dirty:
        jury_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n✍ 已写回 {jury_path.name} (仅 not_applicable, 永不写 fixed)")

    # b) 错因码整表对账 (只报告)
    recon = error_code_reconciliation(pack_path)
    bad = [c for c, _, ok in recon if not ok]
    print(f"\n[错因码对账] 引用 {len(recon)} 码:")
    for code, label, ok in recon:
        print(f"  {code} = {label} {'✓' if ok else '✗ 不在 ERROR_CODE_REGISTRY'}")
    if bad:
        print(f"  ⚠ 非法码 {bad} (供 Tier-2/verify_pack 处置)")

    # c) 真题锚复核
    rc, tail = run_exam_anchor_gate(pack_path)
    print(f"\n[真题锚] verify_exam_anchors exit={rc}: {tail}")
    summary["exam_anchor_exit"] = rc

    print(f"\n小结: 高可信未决 {summary['high_unresolved']} | Tier-0 证伪 {summary['refuted']} "
          f"| 现象为真 {summary['confirmed']} | 落盘 {summary['written']}")
    return summary


def all_pack_ids() -> list[str]:
    ids = set()
    for p in PACK_DIR.glob("[A-Z][0-9][0-9]_*.md"):
        if "作答层样板" not in p.name:
            ids.add(p.name[:3])
    return sorted(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tier-0 确定性预裁 (dry-run 默认)")
    parser.add_argument("pack_ids", nargs="*", help="pack id, 如 G02")
    parser.add_argument("--all", action="store_true", help="全量 pack")
    parser.add_argument("--write-resolutions", action="store_true",
                        help="确定性证伪命中的落盘 not_applicable (默认 dry-run)")
    args = parser.parse_args()
    ids = all_pack_ids() if args.all else [i.upper() for i in args.pack_ids]
    if not ids:
        parser.error("需要 pack id 或 --all")
    summaries = [adjudicate_pack(pid, args.write_resolutions) for pid in ids]
    print(f"\n{'=' * 66}\n=== 汇总 ===")
    print(f"{'pack':<6}{'高可信未决':<12}{'Tier-0证伪':<12}{'现象为真':<10}{'落盘':<6}")
    for s in summaries:
        print(f"{s['pack']:<6}{s['high_unresolved']:<12}{s['refuted']:<12}{s['confirmed']:<10}{s['written']:<6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
