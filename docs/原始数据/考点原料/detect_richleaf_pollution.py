#!/usr/bin/env python3
"""RichLeaf 源库标签污染·确定性全库检测器.

债根因(marathon 26 pack 反复踩): rich_leaf_context_bundle.json 里同一 chunk 的
compiled_context 被错误复制到该 chunk 下所有 leaf, 导致 leaf_name 各异但内容相同
——leaf 名实不符(如 chunk 074_0116 下 B016「屋面防水」/B005「地基沉降」的 context
全是「焊缝夹渣」)。判分召回按 leaf 取 context 会取到错主题内容。

检测(确定性, 零风险只读): 按 source_ref.chunk_id 分组 leaf, 同 chunk 内按
compiled_context 指纹分簇; 簇内 >1 个 leaf 且 leaf_name 末段不同 = 污染簇。
正主 = leaf_name 末段词在 context 命中的那个; 其余 = 被污染 leaf。

输出: _richleaf_pollution_registry.json(治理战役工单 + 未来 mine 的 blocklist)。
不改 bundle 本体(改 bundle = construction_grading 判分生产依赖, 属专门 RichLeaf 治理战役)。
"""
import json, hashlib, re, os
from collections import defaultdict

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = ROOT + "/deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json"


def ctx_text(rec):
    c = rec.get("compiled_context", "")
    if isinstance(c, str) and c.startswith("{"):
        try:
            c = json.loads(c)
        except Exception:
            return c
    return json.dumps(c, ensure_ascii=False) if not isinstance(c, str) else c


def ctx_fingerprint(rec):
    # 用 context 前 600 字指纹(同 chunk 同内容→同指纹)
    return hashlib.sha1(ctx_text(rec)[:600].encode("utf-8")).hexdigest()[:12]


def leaf_topic(rec):
    # leaf_name_path 末段 = 该 leaf 名义主题
    return (rec.get("leaf_name_path", "").split(">")[-1]).strip()


def name_hits_ctx(rec):
    # 名义主题的判别词是否出现在 context(去通用词)
    topic = leaf_topic(rec)
    ctx = ctx_text(rec)
    words = [w for w in re.split(r"[、/()（）\s—·,，:：和与及]+", topic) if len(w) >= 2]
    words = [w for w in words if w not in ("工程", "施工", "质量", "通病", "防治", "管理", "问题", "要点", "技术")]
    if not words:
        return True  # 名义太泛, 不判污染
    return any(w in ctx for w in words)


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    by_chunk = defaultdict(list)
    for r in recs:
        cid = (r.get("source_ref") or {}).get("chunk_id", "")
        by_chunk[cid].append(r)

    pollution = []  # 被污染 leaf
    clusters = 0
    for cid, group in by_chunk.items():
        if len(group) < 2:
            continue
        by_fp = defaultdict(list)
        for r in group:
            by_fp[ctx_fingerprint(r)].append(r)
        for fp, shared in by_fp.items():
            topics = {leaf_topic(r) for r in shared}
            if len(shared) < 2 or len(topics) < 2:
                continue  # 单 leaf 或同名(正常多 leaf 指同卡)不算污染
            # 簇内: 正主 = name 命中 context; 被污染 = name 不命中
            owners = [r for r in shared if name_hits_ctx(r)]
            victims = [r for r in shared if not name_hits_ctx(r)]
            if not victims:
                continue  # 全命中(同卡多角度), 非污染
            clusters += 1
            owner_topic = leaf_topic(owners[0]) if owners else "(无明确正主)"
            for v in victims:
                pollution.append({
                    "leaf_id": v["leaf_id"],
                    "claimed_topic": leaf_topic(v),          # leaf 名义主题
                    "actual_content_topic": owner_topic,      # 实际被填成的内容主题
                    "chunk_id": cid,
                    "fingerprint": fp,
                })

    # 铁污染分级: 同簇(chunk+指纹) leaf 数>=3 = 一份内容挂多 leaf, 几乎确凿(去中文词边界假阳)
    csize = defaultdict(int)
    for p in pollution:
        csize[(p["chunk_id"], p["fingerprint"])] += 1
    for p in pollution:
        p["confidence"] = "iron" if csize[(p["chunk_id"], p["fingerprint"])] >= 3 else "suspect"
    iron = [p["leaf_id"] for p in pollution if p["confidence"] == "iron"]

    out = {
        "_schema": "richleaf_pollution_registry.v0",
        "_status": "确定性检测·只读·不改 bundle(改 bundle = construction_grading 判分生产依赖, 属专门 RichLeaf 治理战役)",
        "_method": "同 chunk 内 context 指纹相同但 leaf_name 末段不同, 且名义主题词不在 context = 名实不符污染",
        "_impact": "影响生产判分召回: 判分按 leaf 取 compiled_context 会取到错主题内容(如屋面防水 leaf 取到焊缝夹渣)",
        "_root_cause": "RichLeaf 编译时一个 chunk 仅取首个子主题 context, 挂给该 chunk 下所有 leaf, 其余 leaf 拿到错内容",
        "_confidence": "iron=簇内>=3 leaf 共享同一内容(几乎确凿) / suspect=2 leaf(含中文无词边界假阳, 需语义复核)",
        "_use": "1) RichLeaf 治理战役工单(重编译 bundle 时按 chunk 拆分子主题 context) 2) 未来 mine 范式 blocklist(自动跳过 iron leaf)",
        "bundle_total_leaf": len(recs),
        "pollution_clusters": clusters,
        "polluted_leaf_count": len(pollution),
        "iron_pollution_count": len(iron),
        "iron_pollution_leaf_ids": sorted(iron),
        "polluted_leaf_ids": sorted(p["leaf_id"] for p in pollution),
        "detail": sorted(pollution, key=lambda p: (p["confidence"] != "iron", p["leaf_id"])),
    }
    p = os.path.join(ROOT, "docs/原始数据/考点原料/_richleaf_pollution_registry.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"全库 {len(recs)} leaf · 污染簇 {clusters} · 被污染 {len(pollution)}({len(pollution)/len(recs)*100:.1f}%) · 铁污染 {len(iron)}")
    print(f"\n铁污染样本(claimed → 实际内容):")
    for p2 in [p for p in out["detail"] if p["confidence"] == "iron"][:10]:
        print(f"  {p2['leaf_id']}  名义[{p2['claimed_topic'][:12]}] 实为[{p2['actual_content_topic'][:12]}]")
    print(f"\n→ 登记表: _richleaf_pollution_registry.json (RichLeaf 治理战役工单 + mine blocklist)")


if __name__ == "__main__":
    main()
