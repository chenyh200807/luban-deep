#!/usr/bin/env python3
"""确定性 chunk-heading harness：复核 RichLeaf 污染 registry 的 suspect 170 leaf。

只读。不改 bundle / registry / 任何生产文件。

方法（与异源专家用过的 chunk-heading 法同构）：
对每个 suspect leaf：
  1. 取 source_ref.chunk_id → 教材原 chunk 的 content_markdown。
  2. 抽出 markdown 子标题集合（### / #### / ##### / 数字编号小节标题）。
  3. claimed_topic（leaf 名义末段）与 actual_content_topic（compiled_context 实际主题）比对：
     A. claimed 的判别词能在 chunk 里切出**独立子标题段落**，且与 actual 是不同子段
        → 真污染（B 类，可 per-leaf 切）。
     B. claimed 与 actual 主题一致（互为父子/别名/同一段不同措辞），或 claimed 词
        其实就落在 actual 子段内 → 假阳（中文无词边界误判）。
     C. claimed 词在整个 chunk 都找不到、chunk 主题与 claimed 完全不相干
        → 需重链/无源（A/C 类）。
分桶输出，不写生产文件，结果打到 stdout + 写 _suspect_review_result.json（只读复核产物）。
"""
import json, re, os
from collections import defaultdict

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = ROOT + "/deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json"
REG = ROOT + "/docs/原始数据/考点原料/_richleaf_pollution_registry.json"
BOOK_BASE = "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强/"
BOOKS = [
    "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]

STOP = ("工程", "施工", "质量", "通病", "防治", "管理", "问题", "要点", "技术",
        "建筑", "设计", "构造", "要求", "基本", "及其", "以及")


def load_chunks():
    chunks = {}
    for bf in BOOKS:
        d = json.load(open(BOOK_BASE + bf, encoding="utf-8"))
        for blk in d["content_blocks"]:
            chunks[blk["chunk_id"]] = blk
    return chunks


def ctx_text(rec):
    c = rec.get("compiled_context", "")
    if isinstance(c, str) and c.startswith("{"):
        try:
            c = json.loads(c)
        except Exception:
            return c
    return json.dumps(c, ensure_ascii=False) if not isinstance(c, str) else c


def headings(md):
    """抽 markdown 子标题文本（去 # 与编号前缀）。"""
    hs = []
    for line in md.splitlines():
        line = line.strip()
        m = re.match(r"^(#{2,6})\s+(.*)", line)
        if m:
            hs.append(m.group(2).strip())
    return hs


LANE_PREFIX = re.compile(r"^[^—]{2,12}——")  # 去 taxonomy lane 前缀, 如 "建筑设计——" "防水工程——"


def strip_lane(topic):
    return LANE_PREFIX.sub("", topic)


def discriminative_words(topic):
    """名义主题去通用词后的判别词。"""
    topic = strip_lane(topic)
    parts = re.split(r"[、/()（）\s—·,，:：;；和与及的]+", topic)
    words = [w for w in parts if len(w) >= 2 and w not in STOP]
    # 若整体不可切，退而取≥3连续汉字子串里去掉停用词后的剩余
    if not words:
        # 把停用词逐个剔掉后看还剩什么
        s = topic
        for sw in STOP:
            s = s.replace(sw, "")
        s = re.sub(r"[、/()（）\s—·,，:：;；和与及的]+", "", s)
        if len(s) >= 2:
            words = [s]
    return words


def review_one(p, rec, chunk):
    claimed = p["claimed_topic"]
    actual = p["actual_content_topic"]
    ctx = ctx_text(rec)
    md = chunk.get("content_markdown", "") if chunk else ""
    hs = headings(md)
    hs_join = " || ".join(hs)
    cwords = discriminative_words(claimed)
    awords = discriminative_words(actual)

    actual_stripped = strip_lane(actual)
    claimed_stripped = strip_lane(claimed)

    # claimed 判别词是否就在 actual 主题里（同主题别名/父子）= 假阳
    claimed_in_actual = bool(cwords) and all((w in actual_stripped) for w in cwords)
    actual_in_claimed = bool(awords) and all((w in claimed_stripped) for w in awords)

    # 共享核心名词(≥2字 n-gram 交集, 去停用词后) → 主题相关 = 父子/同域假阳
    def ngrams(s):
        s = strip_lane(s)
        for sw in STOP:
            s = s.replace(sw, "")
        s = re.sub(r"[、/()（）\s—·,，:：;；和与及的0-9.\-]+", "", s)
        return {s[i:i + 2] for i in range(len(s) - 1)}
    shared = ngrams(claimed) & ngrams(actual)
    topic_overlap = len(shared) >= 1  # 至少一个共享核心二元词

    # claimed 判别词是否落在某个独立子标题上（≠ actual 所在子标题）= 真污染可切
    head_hit = None
    for h in hs:
        if any(w in h for w in cwords) and not all(w in actual for w in cwords):
            head_hit = h
            break

    # claimed 词在整个 chunk 文本(md+ctx) 是否出现
    blob = md + " " + ctx
    appears = bool(cwords) and any(w in blob for w in cwords)

    # actual 词是否在 chunk 出现（确认 context 确实取自本 chunk）
    actual_appears = bool(awords) and any(w in blob for w in awords)

    if not cwords:
        verdict = "false_positive"  # 名义太泛, detector 本应不判
        reason = "claimed 全通用词, 无判别词"
    elif claimed_in_actual or actual_in_claimed:
        verdict = "false_positive"
        reason = "claimed 与 actual 同主题(父子/别名/同段措辞)"
    elif head_hit:
        verdict = "real_pollution"
        reason = f"claimed 词落在独立子标题[{head_hit[:24]}], 与 actual 不同子段, 可 per-leaf 切"
    elif appears:
        # claimed 词在 chunk 里出现但不在独立标题 → 同 chunk 多子主题, context 只取了一个
        # 需看 chunk 是否本就是单主题(则假阳)还是多子主题(则真污染但无清晰标题边界)
        if len(hs) >= 2 and actual_appears:
            verdict = "real_pollution"
            reason = f"chunk 多子主题({len(hs)} 标题), context 只填了 actual, claimed 词另在他处"
        else:
            verdict = "false_positive"
            reason = "claimed 词散见于同一单主题段, 与 actual 主题实质一致"
    else:
        # claimed 判别词整个 chunk 找不到。区分:
        #  - 与 actual 共享核心名词(父子/同域措辞不同) → 假阳
        #  - 完全不相干 → 需重链/无源
        if topic_overlap:
            verdict = "false_positive"
            reason = f"claimed 词面不在 chunk 但与 actual 共享核心词{sorted(shared)}, 同域父子(措辞差异)"
        elif not actual_appears:
            verdict = "needs_relink"
            reason = "claimed 与 actual 词都不在 chunk, 疑似源不匹配(A/C)"
        else:
            verdict = "needs_relink"
            reason = "claimed 与 actual 主题不相干, claimed 名义无源(C)"

    return {
        "leaf_id": p["leaf_id"],
        "chunk_id": p["chunk_id"],
        "claimed": claimed,
        "actual": actual,
        "verdict": verdict,
        "reason": reason,
        "cwords": cwords,
        "n_headings": len(hs),
        "headings": hs[:8],
        "head_hit": head_hit,
        "claimed_appears": appears,
        "topic_overlap": sorted(shared),
    }


def main():
    chunks = load_chunks()
    b = json.load(open(BUNDLE, encoding="utf-8"))
    recs = {r["leaf_id"]: r for r in b["records"]}
    reg = json.load(open(REG, encoding="utf-8"))
    suspect = [p for p in reg["detail"] if p["confidence"] == "suspect"]

    results = []
    for p in suspect:
        rec = recs.get(p["leaf_id"])
        chunk = chunks.get(p["chunk_id"])
        if rec is None:
            results.append({"leaf_id": p["leaf_id"], "verdict": "missing_rec", "reason": "leaf 不在 prod bundle"})
            continue
        results.append(review_one(p, rec, chunk))

    buckets = defaultdict(list)
    for r in results:
        buckets[r["verdict"]].append(r)

    print(f"=== suspect {len(suspect)} 复核分桶 ===")
    for v in ("real_pollution", "false_positive", "needs_relink", "missing_rec"):
        rs = buckets.get(v, [])
        print(f"{v}: {len(rs)} ({len(rs)/len(suspect)*100:.1f}%)")

    out = {
        "_status": "只读复核产物·不改生产",
        "_method": "chunk-heading 确定性 harness, 复核 detector suspect 170",
        "suspect_total": len(suspect),
        "bucket_counts": {v: len(buckets.get(v, [])) for v in
                          ("real_pollution", "false_positive", "needs_relink", "missing_rec")},
        "results": results,
    }
    op = ROOT + "/docs/原始数据/考点原料/_suspect_review_result.json"
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ 复核结果: {op}")


if __name__ == "__main__":
    main()
