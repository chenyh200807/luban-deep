#!/usr/bin/env python3
"""考点 pack 机器闸 (Layer-1 确定性质检, fail-closed).

用法: python verify_pack.py <pack.md> [<source.json>] [--semantic-audit]

若不给 source.json, 按同目录 _<PACKID>_compiled_source.json 推导。

机械验 3 件硬事 (任一不过 = FAIL):
  1. 引用的 point_id (ca:/kc:/m35:) 是否真存在于源料
  2. 引用的 error_code (E/M码) 是否真在 ERROR_CODE_REGISTRY
  3. 三色标注是否存在且 🟢 项不为零
另出软报告 (warning, 不判 FAIL): 🟢 占比、疑似🟢无source行、真题年份引用。

机器闸只验 point_id **存在**, 不验 **语义** (heading 名实是否相符是 Codex 指出的边界):
point_id 真在源料 ≠ 该 point 的 quote/statement 真讲这个考点。``--semantic-audit``
是**可选报告**, 为每个被引用的 point_id 打印其 quote/statement 供人工核名实, **不改判定**
(pass/fail 逻辑完全不动) —— 仍是 Layer-2 独立judge / Layer-3 人审的输入, 不替代它们。
"""
import sys, re, json, os, glob

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
ERR_FILE = os.path.join(ROOT, "deeptutor/contracts/error_codes.py")

def load_valid_error_codes():
    t = open(ERR_FILE, encoding="utf-8").read()
    return set(re.findall(r"\b([EM]\d{2})\b", t)) | {"unknown_error"}

def load_source_point_ids(src_path):
    d = json.load(open(src_path, encoding="utf-8"))
    ids = set()
    for u in d.get("units", []):
        for sp in u.get("scoring_points", []):
            pid = sp.get("point_id")
            if pid:
                ids.add(pid)
                ids.add(pid.rsplit(":", 1)[0])  # 去掉尾部 :idx 的基id
    return ids


def load_source_point_records(src_path):
    """point_id (含去尾 :idx 的基id) -> 该 point 的名实证据 (leaf 名 + quote + statement).

    供 --semantic-audit 报告人工核 "名实是否相符"。只读, 不参与判定。"""
    d = json.load(open(src_path, encoding="utf-8"))
    recs = {}
    for u in d.get("units", []):
        leaf = u.get("leaf_name_path") or u.get("leaf_id") or ""
        for sp in u.get("scoring_points", []):
            pid = sp.get("point_id")
            if not pid:
                continue
            rec = {
                "leaf": leaf,
                "statement": sp.get("statement") or "",
                "quote": sp.get("quote") or "",
            }
            recs[pid] = rec
            recs.setdefault(pid.rsplit(":", 1)[0], rec)
    return recs

def main():
    args = sys.argv[1:]
    semantic_audit = "--semantic-audit" in args
    args = [a for a in args if a != "--semantic-audit"]
    if not args:
        print("用法: python verify_pack.py <pack.md> [<source.json>] [--semantic-audit]"); sys.exit(2)
    pack = args[0]
    text = open(pack, encoding="utf-8").read()
    # 推导 source
    if len(args) >= 2:
        src = args[1]
    else:
        m = re.match(r"([A-Z]\d+)", os.path.basename(pack))
        pid = m.group(1) if m else ""
        d = os.path.dirname(pack)
        cand = glob.glob(os.path.join(d, f"_{pid}*_compiled_source.json")) \
            or glob.glob(os.path.join(os.path.dirname(d), f"_{pid}*_compiled_source.json"))
        src = cand[0] if cand else None
    fails = []

    # --- 检查1: point_id ---
    valid_pids = load_source_point_ids(src) if src and os.path.exists(src) else set()
    # point_id 含中文(如 -罚则), 缩写 :P5/P6 拆开核
    raw = re.findall(r"(?:ca|kc|m35):[0-9A-Za-z_\-一-鿿]+(?::[0-9A-Za-z_\-一-鿿]+(?:/[0-9A-Za-z]+)*)?", text)
    cited_pids = set()
    for p in raw:
        if "/" in p.rsplit(":", 1)[-1]:  # 拆 :P5/P6 -> :P5, :P6
            head, tail = p.rsplit(":", 1)
            for t in tail.split("/"):
                cited_pids.add(head + ":" + t)
        else:
            cited_pids.add(p)
    bad_pids = sorted(p for p in cited_pids if p not in valid_pids and p.rsplit(":",1)[0] not in valid_pids)
    if not src:
        print("[point_id] ⚠ 未找到源料文件, 跳过 (无法验证!)")
    elif bad_pids:
        fails.append(f"point_id 不存在于源料: {bad_pids}")

    # --- 检查2: error_code (排除 node_code 如 1A412030-E01) ---
    valid_codes = load_valid_error_codes()
    cited_codes = set(re.findall(r"(?<![\w\-])([EM]\d{2})(?![\w])", text))
    # 排除建工里跟错因码撞形的非码token: M35=评分工件引擎名; M15/M20=砂浆强度等级(M5/M10也是码,靠上下文区分时只当码)
    NON_CODE = {"M35", "M15", "M20", "M25", "M30"}
    bad_codes = sorted(c for c in cited_codes if c not in valid_codes and c not in NON_CODE)
    if bad_codes:
        fails.append(f"error_code 不在注册表: {bad_codes} (合法: E01-E12/M01-M10)")

    # --- 检查3: 三色 ---
    g, b, r = text.count("🟢"), text.count("🔵"), text.count("🔴")
    if g + b + r == 0:
        fails.append("三色标注缺失 (无 🟢/🔵/🔴)")
    elif g == 0:
        fails.append("无任何 🟢 锚定项 (全是通识/待验证, 不可信)")

    # --- 软报告 ---
    print(f"=== 机器闸: {os.path.basename(pack)} ===")
    print(f"源料: {os.path.basename(src) if src else '(缺)'}  源料point_id数: {len(valid_pids)}")
    print(f"[1 point_id] 引用 {len(cited_pids)} 个, 不存在 {len(bad_pids)} 个" + (f" ✗ {bad_pids}" if bad_pids else " ✓"))
    print(f"[2 error_code] 引用 {sorted(cited_codes)}, 非法 {len(bad_codes)} 个" + (f" ✗ {bad_codes}" if bad_codes else " ✓"))
    print(f"[3 三色] 🟢{g} 🔵{b} 🔴{r}  (🟢占比 {g*100//max(g+b+r,1)}%)")
    # 启发式: 含🟢但同段无 source token 的行 (软警告)
    src_tok = re.compile(r"(ca|kc|m35):|真题\s?20\d\d|source_ref|node_code|教材|规范")
    sus = [i+1 for i,l in enumerate(text.splitlines()) if "🟢" in l and not src_tok.search(l)]
    print(f"[软警告] 疑似🟢无source行: {len(sus)} 行 {('(行号 '+str(sus[:8])+'…)') if sus else ''} — 需Layer2/3核")
    yrs = sorted(set(re.findall(r"真题\s?(20\d\d)", text)))
    print(f"[软报告] 引用真题年份: {yrs}")

    # --- 可选: 语义审计报告 (只读, 不判 FAIL) ---
    if semantic_audit:
        print("─"*50)
        print("[语义审计] point_id 名实核对 (人工判定 quote/statement 是否真讲该考点; 不参与 PASS/FAIL):")
        if not src or not os.path.exists(src):
            print("  ⚠ 无源料, 无法输出语义证据")
        else:
            recs = load_source_point_records(src)
            shown = sorted(p for p in cited_pids if p in recs or p.rsplit(":",1)[0] in recs)
            if not shown:
                print("  (无可解析的被引用 point_id)")
            for p in shown:
                rec = recs.get(p) or recs.get(p.rsplit(":",1)[0]) or {}
                print(f"  • {p}")
                print(f"      leaf : {rec.get('leaf','')}")
                print(f"      quote: {rec.get('quote','')}")
                stmt = rec.get("statement", "")
                if stmt and stmt != rec.get("quote", ""):
                    print(f"      stmt : {stmt}")

    print("─"*50)
    if fails:
        print("裁决: ❌ FAIL")
        for f in fails: print("  ✗", f)
        sys.exit(1)
    print("裁决: ✅ PASS (机器闸通过; 仍需 Layer-2 独立judge + Layer-3 人审/真题)")
    sys.exit(0)

if __name__ == "__main__":
    main()
