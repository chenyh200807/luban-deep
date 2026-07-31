#!/usr/bin/env python3
"""C1 映射构建 v3（只读）。

相对 v2 的关键修正：
- 识别"整题行"(一行含 问题1..N 全部) vs "小问行"(一行一问) vs "背景载体行"(无问无答)。
- 题面无【问题】标记时，用行首序号在尾部区域兜底解析。
- 候选口径放宽为 REAL_EXAM 且正文≥150 字，不再要求必须有【背景资料】标记。
"""
import json, re, os, hashlib, csv
from collections import defaultdict, Counter

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw_case_rows.jsonl")

WS = re.compile(r"\s+")
HARD = re.compile(r"[^一-鿿0-9]")
FW = str.maketrans("０１２３４５６７８９", "0123456789")

Q_REGION = re.compile(r"【\s*问\s*题\s*】|#{2,4}\s*问题|^[ \t]*问题[ \t]*[:：]", re.M)
BG_MARK = re.compile(r"【\s*背景资料\s*】|【\s*案例背景\s*】|#{2,4}\s*案例背景")
XW_OID = re.compile(r"^XW_(\d{4})_CASE_(\d+)_Q(\d+)$")
CASE_HASH = re.compile(r"^EXAM_.+_CASE_([0-9a-f]{8})$")

ORD_LINE = re.compile(r"^[ \t]*(?:问题[ \t]*)?(\d{1,2})[ \t]*[.．、：:][ \t]*(?=\S)", re.M)
ORD_INLINE_Q = re.compile(r"问题[ \t]*(\d{1,2})[ \t]*[：:.]")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
ANCHOR_SUBQ = [re.compile(r"问题\s*(\d{1,2})"), re.compile(r"^第\s*(\d{1,2})\s*[题问]")]

FABRICATED = "（根据上下文推断）"
PLACEHOLDER = ["（无独立背景，为通用问题）", "无独立背景"]
MIN_BODY = 150      # 候选行最小正文长度（硬归一化后）
MIN_BG = 60         # 建组所需最小背景长度


def hardnorm(s):
    return HARD.sub("", (s or "").translate(FW))


def question_region(stem):
    m = Q_REGION.search(stem)
    if m:
        return stem[m.end():], m.start(), True
    return stem[-900:], max(0, len(stem) - 900), False


def collect_ordinals(region, explicit):
    hits = [(m.start(), int(m.group(1))) for m in ORD_LINE.finditer(region)]
    hits += [(m.start(), int(m.group(1))) for m in ORD_INLINE_Q.finditer(region)]
    hits.sort()
    seen, ords = set(), []
    for _pos, n in hits:
        if n not in seen and 1 <= n <= 12:
            seen.add(n); ords.append(n)
    if not explicit:
        # 无显式【问题】标记时只接受尾部升序连续 run，避免把背景里的编号列表当小问
        run = []
        for n in ords:
            if not run or n == run[-1] + 1:
                run.append(n)
            else:
                run = [n]
        ords = run
    return ords


def gen_of(oid):
    oid = oid or ""
    if XW_OID.match(oid): return "g0_xw"
    if re.match(r"^EXAM_\d{4}_", oid): return "g3_exam_year"
    if CASE_HASH.match(oid): return "g2_exam_chunk"
    if oid.startswith("AUTO_"): return "g1_auto"
    return "gx_other"


def shingles(s, n=6):
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


class UF:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[rb] = ra


def main():
    rows = [json.loads(l) for l in open(RAW, encoding="utf-8")]
    recs = []
    for r in rows:
        stem = r.get("stem_text") or ""
        oid = r.get("original_id") or ""
        meta = r.get("source_meta") if isinstance(r.get("source_meta"), dict) else {}
        region, qstart, explicit = question_region(stem)
        ords = collect_ordinals(region, explicit)
        bg_raw = stem[:qstart] if explicit else stem
        bgn = hardnorm(BG_MARK.sub("", bg_raw))
        xw = XW_OID.match(oid)
        ch = CASE_HASH.match(oid)
        anchor = meta.get("original_anchor")

        # ---- 行粒度分类 ----
        if xw:
            kind, idx, idx_src, span = "single_subquestion", int(xw.group(3)), "oid_xw_Q", None
        elif len(ords) >= 2 and ords[0] == 1:
            kind, idx, idx_src, span = "whole_case", None, None, [min(ords), max(ords)]
        elif len(ords) == 1:
            kind, idx, idx_src, span = "single_subquestion", ords[0], ("stem_ordinal" if explicit else "stem_tail_ordinal"), None
        elif len(ords) >= 2:
            kind, idx, idx_src, span = "ambiguous_multi", None, None, [min(ords), max(ords)]
        else:
            kind, idx, idx_src, span = "no_question_text", None, None, None
        if idx is None and kind in ("no_question_text",):
            for p in ANCHOR_SUBQ:
                m = p.search(anchor or "")
                if m:
                    idx, idx_src, kind = int(m.group(1)), "anchor", "single_subquestion"
                    break

        recs.append({
            "row_id": r["id"], "original_id": oid, "source_type": r.get("source_type"),
            "node_code": r.get("node_code"), "exam_year": r.get("exam_year"),
            "source_chunk_id": r.get("source_chunk_id"), "case_hash8": ch.group(1) if ch else None,
            "anchor": anchor, "page_num": meta.get("page_num"), "gen": gen_of(oid),
            "row_granularity": kind, "subq_span": span,
            "bgn": bgn, "bg_len": len(bgn), "body_len": len(hardnorm(stem)),
            "q_head": WS.sub(" ", region.strip())[:140],
            "stem_head": WS.sub(" ", stem.strip())[:140],
            "idx": idx, "idx_src": idx_src,
            "has_answer": r.get("has_answer"), "ans_len": r.get("ans_len"),
            "ans_type": r.get("ans_type"), "has_rubric": r.get("has_rubric"),
            "ans_norm": hardnorm(r.get("ans_text") or "")[:300],
            "fabricated_bg": FABRICATED in stem,
            "placeholder_bg": any(p in bg_raw for p in PLACEHOLDER),
            "xw_case_no": int(xw.group(2)) if xw else None,
        })

    cand = [r for r in recs if r["source_type"] == "REAL_EXAM" and r["body_len"] >= MIN_BODY]
    non_case = [r for r in recs if r not in cand]  # 保持顺序稳定
    cand_ids = {r["row_id"] for r in cand}
    non_case = [r for r in recs if r["row_id"] not in cand_ids]

    # ---------- 年内合并建组 ----------
    uf = UF()
    by_year = defaultdict(list)
    for r in cand:
        if r["bg_len"] >= MIN_BG and not r["fabricated_bg"] and not r["placeholder_bg"]:
            by_year[r["exam_year"]].append(r); uf.find(("row", r["row_id"]))

    merge_log = []
    for year, members in by_year.items():
        exact = defaultdict(list)
        for r in members:
            exact[r["bgn"]].append(r)
        for k, lst in exact.items():
            for r in lst:
                uf.union(("row", lst[0]["row_id"]), ("row", r["row_id"]))
        keys = list(exact)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                reason = None
                if a in b or b in a:
                    reason = "containment"
                else:
                    sa, sb = shingles(a), shingles(b)
                    if sa and sb:
                        jac = len(sa & sb) / len(sa | sb)
                        if jac >= 0.55:
                            reason = f"jaccard={jac:.2f}"
                if reason:
                    uf.union(("row", exact[a][0]["row_id"]), ("row", exact[b][0]["row_id"]))
                    merge_log.append({"year": year, "reason": reason,
                                      "a_ids": [r["row_id"] for r in exact[a]],
                                      "b_ids": [r["row_id"] for r in exact[b]],
                                      "a_head": a[:50], "b_head": b[:50]})
    # _CASE_hash 作为佐证再合一次（同 hash 必同题）
    hashmap = defaultdict(list)
    for year, members in by_year.items():
        for r in members:
            if r["case_hash8"]:
                hashmap[r["case_hash8"]].append(r)
    for h, lst in hashmap.items():
        for r in lst[1:]:
            if uf.find(("row", lst[0]["row_id"])) != uf.find(("row", r["row_id"])):
                merge_log.append({"year": lst[0]["exam_year"], "reason": f"case_hash8={h}",
                                  "a_ids": [lst[0]["row_id"]], "b_ids": [r["row_id"]],
                                  "a_head": "", "b_head": ""})
            uf.union(("row", lst[0]["row_id"]), ("row", r["row_id"]))

    clusters = defaultdict(list)
    for year, members in by_year.items():
        for r in members:
            clusters[uf.find(("row", r["row_id"]))].append(r)

    # ---------- case_no ----------
    year_clusters = defaultdict(list)
    for root, ms in clusters.items():
        year_clusters[ms[0]["exam_year"]].append((root, ms))
    group_meta = {}
    for year, lst in year_clusters.items():
        def sortkey(item):
            _r, ms = item
            xw = [m["xw_case_no"] for m in ms if m["xw_case_no"]]
            pages = [m["page_num"] for m in ms if m["page_num"]]
            return (min(xw) if xw else 99, min(pages) if pages else 999,
                    min(m["row_id"] for m in ms))
        for n, (root, ms) in enumerate(sorted(lst, key=sortkey), start=1):
            xw = sorted({m["xw_case_no"] for m in ms if m["xw_case_no"]})
            case_no = xw[0] if len(xw) == 1 else n
            src = "oid_xw_CASE" if len(xw) == 1 else (
                "page_order" if any(m["page_num"] for m in ms) else "rowid_order")
            fp = hashlib.md5(max((m["bgn"] for m in ms), key=len).encode()).hexdigest()[:16]
            group_meta[root] = {"case_group_id": f"{year}-case{case_no}", "case_no": case_no,
                                "case_no_src": src, "case_group_fingerprint": fp, "exam_year": year}

    inv = {m["row_id"]: root for root, ms in clusters.items() for m in ms}

    assigned, whole_case, group_only, unassignable = [], [], [], []
    for r in cand:
        root = inv.get(r["row_id"])
        if root is None:
            if r["fabricated_bg"]:
                r["reason"] = "污染:LLM编造背景（根据上下文推断），非真题原文"
            elif r["placeholder_bg"]:
                r["reason"] = "背景占位符(无独立背景/通用问题)，题级归属证据不足"
            else:
                r["reason"] = f"背景正文过短({r['bg_len']}字)，不能建题级键"
            unassignable.append(r); continue
        r.update(group_meta[root])
        if r["row_granularity"] == "whole_case":
            r["reason"] = f"整题行(一行含问题{r['subq_span'][0]}~{r['subq_span'][1]})，不是单个小问，subquestion_index 应留空"
            whole_case.append(r)
        elif r["idx"] is None:
            r["reason"] = f"题级组已定，小问序号无原文证据(granularity={r['row_granularity']}, has_answer={r['has_answer']})"
            group_only.append(r)
        else:
            assigned.append(r)

    for r in non_case:
        st = r["source_type"]
        r["reason"] = {
            "TEXTBOOK_ASSESSMENT": "非案例题:教材自动生成考核题被误标 question_type=case_study",
            "LECTURE_NOTE_ASSESSMENT": "非案例题:讲义自动生成考核题被误标 question_type=case_study",
            "textbook_exercise": "非案例题:教材习题被误标 question_type=case_study",
            "TEXTBOOK": "非案例题:教材条目被误标 question_type=case_study",
        }.get(st, f"REAL_EXAM 但正文过短({r['body_len']}字)，疑似碎片/空行" if st == "REAL_EXAM" else f"未知来源({st})")
        unassignable.append(r)

    # ---------- 组内校验 ----------
    gm_rows = defaultdict(list)
    for r in assigned:
        gm_rows[r["case_group_id"]].append(r)
    gm_all = defaultdict(list)
    for r in assigned + whole_case + group_only:
        gm_all[r["case_group_id"]].append(r)

    group_report = {}
    for gid, ms in gm_all.items():
        sub = [m for m in ms if m["row_granularity"] == "single_subquestion" and m["idx"]]
        wc = [m for m in ms if m["row_granularity"] == "whole_case"]
        cnt = Counter(m["idx"] for m in sub)
        distinct = sorted(cnt)
        contiguous = bool(distinct) and distinct == list(range(1, max(distinct) + 1))
        by_idx = defaultdict(list)
        for m in sub: by_idx[m["idx"]].append(m)
        conflicts = [{"index": i, "ids": [x["row_id"] for x in l]}
                     for i, l in by_idx.items()
                     if len(l) > 1 and len({x["ans_norm"][:150] for x in l}) > 1]
        wc_span = sorted({tuple(m["subq_span"]) for m in wc})
        group_report[gid] = {
            "total_rows": len(ms), "subquestion_rows": len(sub), "whole_case_rows": len(wc),
            "background_only_rows": len(ms) - len(sub) - len(wc),
            "distinct_indexes": distinct, "contiguous": contiguous,
            "whole_case_spans": [list(s) for s in wc_span],
            "max_observed_subq": max([max(distinct)] if distinct else [0] +
                                     [s[1] for s in wc_span] or [0]) if (distinct or wc_span) else 0,
            "gens": sorted({m["gen"] for m in ms}),
            "answer_conflicts": conflicts,
            "fingerprint": ms[0]["case_group_fingerprint"], "case_no_src": ms[0]["case_no_src"],
            "row_ids": sorted(m["row_id"] for m in ms),
        }
        for m in sub:
            m["group_size"] = len(ms); m["group_distinct_indexes"] = len(distinct)
            m["group_contiguous"] = contiguous
            m["index_duplicated"] = cnt[m["idx"]] > 1
            m["index_answer_conflict"] = any(c["index"] == m["idx"] for c in conflicts)
            ev = [f"bg_fp={m['case_group_fingerprint']}(bg{m['bg_len']}字)",
                  f"idx_src={m['idx_src']}", f"gen={m['gen']}", f"case_no_src={m['case_no_src']}"]
            if m["anchor"]: ev.append(f"anchor={m['anchor']}")
            if m["case_hash8"]: ev.append(f"case_hash8={m['case_hash8']}")
            m["evidence"] = "|".join(ev)
            if not m["has_answer"]:
                m["confidence"] = "low"
            elif m["idx_src"] == "oid_xw_Q":
                m["confidence"] = "high"
            elif m["idx_src"] == "stem_ordinal" and contiguous and not m["index_answer_conflict"]:
                m["confidence"] = "high"
            elif m["idx_src"] in ("stem_ordinal", "stem_tail_ordinal"):
                m["confidence"] = "medium"
            else:
                m["confidence"] = "low"

    # ---------- 落盘 ----------
    def clean(d):
        return {k: v for k, v in d.items() if k not in ("bgn", "ans_norm")}

    def dump(name, data):
        with open(os.path.join(BASE, name), "w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(clean(d), ensure_ascii=False) + "\n")

    assigned.sort(key=lambda x: (x["exam_year"], x["case_no"], x["idx"], x["row_id"]))
    whole_case.sort(key=lambda x: (x["exam_year"], x["case_no"], x["row_id"]))
    group_only.sort(key=lambda x: (x["exam_year"], x["case_no"], x["row_id"]))
    unassignable.sort(key=lambda x: x["row_id"])
    dump("mapping.jsonl", assigned)
    dump("mapping_whole_case_rows.jsonl", whole_case)
    dump("mapping_group_only.jsonl", group_only)
    dump("unassignable.jsonl", unassignable)
    json.dump(merge_log, open(os.path.join(BASE, "merge_log.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(group_report, open(os.path.join(BASE, "group_report.json"), "w"), ensure_ascii=False, indent=1)

    with open(os.path.join(BASE, "mapping.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "stem摘要", "提议case_group_id", "提议subquestion_index", "归属证据",
                    "置信度", "case_group_fingerprint", "row_granularity", "gen", "group_size",
                    "group_distinct_indexes", "index_duplicated", "index_answer_conflict",
                    "group_contiguous", "exam_year", "original_id", "source_chunk_id", "has_answer"])
        for m in assigned:
            w.writerow([m["row_id"], m["q_head"], m["case_group_id"], m["idx"], m["evidence"],
                        m["confidence"], m["case_group_fingerprint"], m["row_granularity"], m["gen"],
                        m["group_size"], m["group_distinct_indexes"], m["index_duplicated"],
                        m["index_answer_conflict"], m["group_contiguous"], m["exam_year"],
                        m["original_id"], m["source_chunk_id"], m["has_answer"]])

    with open(os.path.join(BASE, "unassignable.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "stem摘要", "原因分类", "row_granularity", "source_type", "exam_year",
                    "original_id", "bg_len", "所属组(若已定)", "整题行span", "has_answer"])
        for m in whole_case + group_only:
            w.writerow([m["row_id"], m["stem_head"], m["reason"], m["row_granularity"], m["source_type"],
                        m["exam_year"], m["original_id"], m["bg_len"], m["case_group_id"],
                        m["subq_span"] or "", m["has_answer"]])
        for m in unassignable:
            w.writerow([m["row_id"], m["stem_head"], m["reason"], m["row_granularity"], m["source_type"],
                        m["exam_year"], m["original_id"], m["bg_len"], "", m["subq_span"] or "",
                        m["has_answer"]])

    stats = {
        "total_case_study_rows": len(recs),
        "real_exam_candidates": len(cand),
        "A_assigned_group_and_index": len(assigned),
        "B_whole_case_rows_group_only": len(whole_case),
        "C_group_only_index_blank": len(group_only),
        "D_unassignable": len(unassignable),
        "groups": len(gm_all),
        "groups_per_year": dict(sorted(Counter(g.split("-")[0] for g in gm_all).items())),
        "confidence_dist": dict(Counter(m["confidence"] for m in assigned)),
        "idx_src_dist": dict(Counter(m["idx_src"] for m in assigned)),
        "gen_dist_assigned": dict(Counter(m["gen"] for m in assigned)),
        "row_granularity_dist_candidates": dict(Counter(m["row_granularity"] for m in cand)),
        "groups_non_contiguous": [g for g, v in group_report.items()
                                  if v["subquestion_rows"] and not v["contiguous"]],
        "groups_with_answer_conflict": {g: v["answer_conflicts"] for g, v in group_report.items()
                                        if v["answer_conflicts"]},
        "rows_with_dup_index": sum(1 for m in assigned if m.get("index_duplicated")),
        "merge_operations": len(merge_log),
        "unassignable_reasons": dict(Counter(m["reason"] for m in unassignable)),
        "group_only_reasons": dict(Counter(m["reason"][:40] for m in group_only)),
    }
    json.dump(stats, open(os.path.join(BASE, "stats.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
