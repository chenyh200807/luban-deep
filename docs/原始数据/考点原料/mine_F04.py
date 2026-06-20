#!/usr/bin/env python3
"""F04 防水细部节点: 阴阳角/管根/女儿墙 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 F04 真采分点, 产 _F04_compiled_source.json (照 F03/C06/S06 结构).

考点身份 (注册表 slot 32, **coarse_review**):
  primary  1A413050-R07 卷材防水层施工            (canonical resolve✅, ⚠️name=卷材施工·非细部节点本体)
  support  1A413050-R20 屋面防水基本要求          (resolve✅)
           1A413050-R21 屋面防水等级和防水做法    (resolve✅)
           1A413050-R23 施工缝设置及防水构造      (resolve✅)
  ⚠️ 注册表注: 细部节点缺专门 leaf; 注册表 primary 1A413050-R07 是【卷材施工】叶子, supporting R20/R21
     是【屋面防水等级/基本要求】叶子, 均非"阴阳角/管根/女儿墙泛水/附加层/收头"细部节点本体. 本 pack 标
     coarse_review + needs_leaf_review, 不进学员默认入口 (照 Q03/C06/S07 先例).

  编译库现实(直读核真): 4 个 registry code 全部 resolve✅, 但真正承载"细部节点防水构造"教学卡的叶子
     **不是注册表那 4 个 code, 而是同叶子族 1A413050-R* 下另几个名实相符的叶子**:
       - 1A413051-R08 (chunk 1A413030_125_0237) = "檐口、檐沟、天沟、水落口等细部的施工" — F04 细部节点本体核心叶子
         (檐口800mm满粘/收头金属压条密封/鹰嘴滴水槽; 檐沟天沟附加层伸入≥250mm; 女儿墙泛水附加层平立面≥250mm; 水落口杯固定+涂膜附加层)
       - 1A413050-R16 (chunk 1A413030_134_0257) = "室内防水层施工" — 阴阳角圆弧/管根地漏附加层增强材料本体
       - 1A413050-R17 (chunk 1A413030_133_0256) = "室内防水构造要求" — 翻起高度/管根密封/穿楼板套管 (与 F03 室内防水有重叠, F04 取管根/穿楼板细部侧)
       - 1A422000-B131 (chunk 1A422000_042_0066) = 法规"细部构造工程" — 女儿墙压顶坡度≥5%/收头压条密封/水落口杯防水伸入≥50mm
       - 1A413050-R23 (chunk 1A413030_131_0250) = 注册表 supporting, 偏地下接缝施工缝防水构造(变形缝侧), 作 supporting 锚 + ext
     真细部节点本体叶子(R08/R16/B131)作弹药内部引用, 与注册表 canonical 4 code(R07/R20/R21/R23)并存(收口对账记此名实差异).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 字符串编码用 pj() 解析 (前 20+ 个新产都踩过):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析.
  - 注册表 primary 1A413050-R07(卷材施工)名实不符 F04 细部节点本体(那是 F02 territory 的卷材铺贴工艺); 真细部
    节点教学锚在 R08(檐口细部)/R16(室内阴阳角管根)/R17(室内构造)/B131(法规细部构造). 名实不符的 R07/R20/R21
    不作 F04 主采分眼(以 compiled_context 真实内容为准), 标 supporting 锚 + 留痕.
  - 与 F02(卷材施工)/F03(防水构造层次/设防)/F05(渗漏治理)严格区分:
    * F02=卷材怎么铺/搭接/排气/收头工艺(材料施工工艺); F04=节点怎么处理(阴阳角圆弧/管根附加层/女儿墙泛水
      附加层250mm/压顶鹰嘴滴水/收头压条密封)=细部构造做法. 收头压条密封既是卷材收头工艺(F02)又是节点构造(F04),
      节点处的收头/附加层作 F04 本体取.
    * F03=屋面/地下防水等级设防道数+构造层次顺序(几道防水/层序); F04=具体节点细部做法. 室内翻起高度(R17)在
      F03 已取, F04 取其管根密封/穿楼板套管细部侧, 翻起高度数值标🔵(F03 territory 邻接)避重复判分.
    * F05=渗漏治理诊断(已渗漏→查因→治理); 1A434000_077_0120(山墙女儿墙部位漏水治理)是 F05 territory, 标🔵
      wai 邻接(治理措施非 F04 节点构造做法本体, 但"压顶/收头/钉压条"做法点与 F04 节点构造相通, 取做法点作🔵外延).
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_F04_compiled_source.json")

KEYWORDS = ("防水细部|细部节点|细部构造|阴阳角|阴角|阳角|圆弧|管根|穿墙管|穿楼板管|女儿墙|泛水|泛水高度|压顶|"
            "附加层|增强层|收头|密封|变形缝|水落口|檐口|附加增强层|节点防水|250mm|附加层宽度")

# 经人工核真(直读 compiled_context)的 (chunk, leaf) 白名单 + 内容类型.
# mode: "full"=F04 细部节点本体判分眼(阴阳角/管根/女儿墙泛水/附加层/收头/檐口/水落口)
#       "ext" =邻接外延(本身非细部节点本体, 标🔵, 如外墙节点先做原则/地下接缝施工缝构造)
#       "wai" =渗漏治理/F03重叠 territory 外延(标🔵, 只保留与节点构造做法相通的做法点)
CHUNK_POLICY = {
    # ── 主轴本体: 檐口/檐沟/天沟/水落口/女儿墙泛水 细部施工 (F04 细部节点核心叶子) ──
    ("1A413030_125_0237", "1A413051-R08"): ("full", "本体·primary 主轴: 檐口/檐沟/天沟/水落口/女儿墙泛水细部施工(1A413051-R08, 名实相符核心细部叶子): 檐口800mm范围卷材满粘·收头金属压条钉压并密封·下端设鹰嘴和滴水槽; 檐沟天沟防水层下增设附加层伸入屋面宽度≥250mm·女儿墙泛水处附加层平面和立面宽度均≥250mm; 水落口杯牢固固定承重结构·防水层下增设涂膜附加层·虹吸式排水专项设计 — F04 判分眼最集中卡. **逐数值核真**"),
    # ── 主轴本体: 室内防水层施工 (阴阳角圆弧/管根地漏附加层增强材料) ──
    ("1A413030_134_0257", "1A413050-R16"): ("full", "本体·阴阳角/管根/附加层增强材料(1A413050-R16, 室内防水层施工): 基层坚实平整无浮浆起砂裂缝·阴角阳角宜做圆弧处理; 阴阳角/管根/地漏等部位先做附加层·夹铺胎体增强材料·最后一遍可撒砂; (聚乙烯丙纶复合卷材基层湿润不得明水/自粘卷材低温热风加热属材料施工工艺侧). **阴阳角圆弧+管根附加层是 F04 细部节点本体**"),
    # ── 主轴本体: 室内防水构造要求 (管根密封/穿楼板套管细部; 翻起高度数值F03 territory标🔵) ──
    ("1A413030_133_0256", "1A413050-R17"): ("full", "本体·管根/穿楼板套管细部密封(1A413050-R17, 室内防水构造要求): 地漏管道根部必须密封·穿楼板/墙体管道套管与管道间用防水密封材料嵌填压实·防水套管高出装饰面≥20mm — 管根/穿楼板细部是 F04 本体; (翻起高度淋浴≥2000mm/盥洗≥1200mm/其他泛水≥250mm 数值在 F03 室内防水已取, F04 标🔵 F03 territory 邻接避重复判分, 泛水≥250mm 与节点附加层250mm 相通处取🟢). **逐数值核真**"),
    # ── 主轴本体: 法规·细部构造工程 (女儿墙压顶坡度/收头/水落口杯) ──
    ("1A422000_042_0066", "1A422000-B131"): ("full", "本体·法规细部构造工程(1A422000-B131): 女儿墙和山墙压顶向内排水坡度≥5%·卷材收头用金属压条钉压固定+密封材料封严·涂膜防水层直接涂刷至压顶下; 水落口设于沟底最低点·周围500mm范围内坡度≥5%·防水层伸入杯内≥50mm·粘结牢固 — 女儿墙压顶/水落口细部构造本体. **逐数值核真**"),
    # ── 邻接外延: 注册表 supporting 施工缝防水构造 (偏地下接缝, 作 supporting 锚 + ext) ──
    ("1A413030_131_0250", "1A413050-R23"): ("ext", "外延·注册表 supporting 施工缝设置及防水构造(1A413050-R23): 水平施工缝高出底板≥300mm·距孔洞边缘≥300mm·垂直缝避开地下水丰富区宜结合变形缝; 遇水膨胀止水条7d净膨胀率≤60%最终·最终膨胀率≥220%. 偏地下接缝/变形缝防水构造(F03 地下防水 territory), 作注册表 supporting 锚 + 变形缝节点外延, 标🔵(非阴阳角/管根/女儿墙细部本体, 但变形缝是细部节点之一, 止水条做法点取🔵外延)"),
    # ── 邻接外延: 外墙防水·节点先做原则 ──
    ("1A413030_134_0259", "1A413050-R13"): ("ext", "外延·外墙防水节点处理优先原则(1A413050-R13): 门窗框/管道等部件安装完毕后再进行防水施工·施工前应先做好节点处理; 严禁雨天雪天五级风及以上施工·环境温度宜5~35℃. '先做节点处理'是 F04 细部节点施工顺序原则(取🟢做法点), 外墙施工条件标🔵外延"),
    # ── 渗漏治理 territory 外延(F05, 只保留与节点构造做法相通的做法点) ──
    ("1A434000_077_0120", "1A434000-B019"): ("wai", "外延·山墙女儿墙部位漏水治理(1A434000-B019, F05渗漏治理territory): 治理措施清除旧胶结料→烤干基层→重新钉压条→覆盖新卷材→防水油膏封口·修复压顶砂浆·分层压入新卷材并加铺一层. 治理流程是 F05 territory(标🔵), 但'压顶/收头钉压条/卷材收口'做法点与 F04 女儿墙节点构造相通, 取做法点作🔵外延邻接参照, 非 F04 节点构造主采分点"),
    # ── 屋面防水等级 territory 外延(F03, 注册表 supporting R20/R21 同 chunk; 取附加层/泛水句作🔵) ──
    ("1A413030_122_0230", "1A413050-R20"): ("wai", "外延·屋面防水基本要求(1A413050-R20, 注册表 supporting; F03 territory): 以防为主以排为辅·设计年限≥20年·泛水/天沟/檐沟/变形缝设附加层. 屋面防水等级/基本要求是 F03 防水构造层次/设防 territory(标🔵), 但'泛水/天沟/檐沟/变形缝设附加层'是 F04 细部节点设附加层原则, 取附加层句作🔵→🟢外延(细部节点附加层本体相通), 等级道数数值标🔵 F03 territory"),
}

# wai 模式: 只保留 title/content 含这些"节点/收头/压条/附加层/泛水/压顶/密封"细部构造做法本体词的卡, 余渗漏/等级数值绕开
WAI_KEEP = re.compile(r"压顶|收头|压条|钉压|附加层|泛水|密封|女儿墙|水落口|檐口|滴水|鹰嘴|阴阳角|管根|节点|增强|卷材收口")
NOISE_BLOCK = re.compile(r"等级.*道|抗渗|P6|P8|水胶比|龄期|养护|坍落度|劳务|桩基|地基不均")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A413030_122_0230(1A413050-R21/R36/R39 屋面等级道数)": "屋面防水等级一二三级≥3/≥2/≥1道+卷材≥1道+防水材料选择 — F03 防水构造层次/设防 territory(注册表 supporting R21 同 chunk, 但等级道数是 F03 判分眼非 F04 细部节点本体), 绕开归 F03 (本 chunk 仅取 R20 的'泛水/天沟/檐沟/变形缝设附加层'句作🔵→细部附加层外延)",
    "1A413030_131_0250(R23 大体积防水混凝土养护/地下防水)": "施工缝 chunk 内大体积防水混凝土龄期60d/90d/养护≥14d/后浇带≥28d — F03 结构自防水 territory, 非 F04 细部节点本体, NOISE 剔(R23 只取施工缝/止水条/变形缝节点构造做法点作🔵外延)",
    "1A413030_134_0257(R16 聚乙烯丙纶/自粘卷材施工工艺)": "室内防水层施工 chunk 内'聚乙烯丙纶复合卷材基层湿润不得明水/自粘卷材低温热风加热' — F02 卷材材料施工工艺 territory, 非 F04 细部节点本体(阴阳角圆弧/管根附加层才是 F04 本体), 材料工艺卡标🔵或绕开",
    "1A413030_146_0283/147_0284(幕墙密封胶/结构胶)": "建筑幕墙工程施工(单元式/构件式/全玻/点支承/石材/金属幕墙的密封胶/结构胶) — 幕墙工程 territory, '密封/节点'泛词命中, 非防水细部节点, 绕开归幕墙(D13)",
    "1A411011_023_0044(变形缝构造设计/分类)": "建筑设计>建筑构造设计要求>变形缝构造/分类/设置(R37~R43) — 属【建筑构造设计】章(命题语境是变形缝设计分类非防水节点细部做法), '变形缝'泛词命中, 绕开归建筑构造设计",
    "1A411011_017_0031(散水明沟/墙体构造设计)": "建筑设计>建筑构造设计要求>散水明沟/墙体构造('女儿墙/泛水'泛词命中) — 建筑构造设计层非防水节点施工细部, 绕开",
    "1A412010_065_0126(B048/B049 建筑密封材料性能)": "结构工程材料>建筑密封与堵漏灌浆材料/建筑密封材料('密封'高频命中) — 属【材料性能】考点(密封材料种类/性能), 非 F04 节点密封构造做法, 绕开归材料考点",
    "1A422000_042_0066(B131 同 chunk 其他法规卡)": "法规细部构造 chunk 内若混入非女儿墙/水落口/收头的其他法规泛词卡, NOISE_BLOCK 剔(B131 主卡女儿墙压顶/水落口已 full 收)",
    "1A422000_040_0064(分格缝/屋面工程法规)": "法规>保温隔热/基层保护/屋面工程('分格缝'命中) — 屋面工程法规泛词, 分格缝偏屋面分仓非阴阳角/管根/女儿墙节点本体, 绕开",
    "1A411011_002_0003(檐口/女儿墙=建筑高度计算)": "建筑设计>建筑高度计算规则('檐口/女儿墙'命中) — 建筑高度按檐口/女儿墙计算是【建筑高度】考点, 非防水细部节点, 绕开",
}


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    seen = {}
    for r in recs:
        ch = r["source_ref"].get("chunk_id", "")
        lf = r.get("leaf_id", "")
        if (ch, lf) in CHUNK_POLICY and (ch, lf) not in seen:
            seen[(ch, lf)] = r

    units = []
    total_sp = 0
    for (ch, lf), (mode, note) in CHUNK_POLICY.items():
        r = seen.get((ch, lf))
        if not r:
            print(f"⚠ chunk {ch} (leaf {lf}) 未在bundle找到, 跳过")
            continue
        cc = r["compiled_context"]
        cc = cc if isinstance(cc, dict) else (pj(cc) or {})
        sps = []
        idx = 0
        captured = set()
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "wai" and (not WAI_KEEP.search(blob) or NOISE_BLOCK.search(blob)):
                continue
            content = t.get("content", "") or ""
            prefix = "[🔵渗漏/F03/F02外延] " if mode == "wai" else ("[🔵外延] " if mode == "ext" else "")
            sps.append({
                "statement": prefix + (t.get("title", "") + "：" + content).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": content,
                "chunk": ch,
                "tier": mode,
            })
            captured.add(content.strip())
            idx += 1
        for rule in cc.get("rules", []):
            ro = pj(rule)
            if isinstance(ro, dict):
                rt = ro.get("description", "") or ro.get("statement", "")
            elif isinstance(rule, str):
                rt = rule
            else:
                rt = ""
            if not rt or rt.strip() in captured:
                continue
            if mode == "wai" and (not WAI_KEEP.search(rt) or NOISE_BLOCK.search(rt)):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
                "tier": mode,
            })
            captured.add(rt.strip())
            idx += 1
        for ep in cc.get("exam_patterns", []):
            e = pj(ep)
            if not e:
                continue
            desc = e.get("description", "") or ""
            if mode == "wai" and (not WAI_KEEP.search(desc) or NOISE_BLOCK.search(desc)):
                continue
            sps.append({
                "statement": desc,
                "required_terms": e.get("grading_keywords", []),
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(e.get("grading_keywords", [])),
                "chunk": ch,
                "tier": mode,
            })
        if sps:
            units.append({
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "F04 防水细部节点: 阴阳角/管根/女儿墙",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "coarse_review (slot 32, needs_leaf_review, 不进学员默认入口)",
        "编译库覆盖说明": "注册表 4 code(primary 1A413050-R07卷材施工 / supporting R20屋面基本要求/R21屋面等级做法/R23施工缝防水构造)全部 resolve✅, 但均非'阴阳角/管根/女儿墙泛水/附加层/收头'细部节点本体(R07=F02卷材工艺/R20·R21=F03屋面设防/R23=地下接缝). 真细部节点教学锚集中在同叶子族另几叶: 1A413051-R08(檐口檐沟天沟水落口女儿墙泛水细部施工·附加层≥250mm·收头压条密封·鹰嘴滴水槽) + 1A413050-R16(室内防水层施工·阴阳角圆弧·管根附加层增强材料) + 1A413050-R17(管根密封·穿楼板套管) + 1A422000-B131(法规细部构造·女儿墙压顶坡度≥5%·水落口杯伸入≥50mm), 名实相符直读核真. F04 主轴判分眼: 阴阳角圆弧/45度·管根地漏先做附加层夹铺增强材料·女儿墙泛水附加层平立面≥250mm·泛水高度≥250mm·檐口800mm满粘+收头金属压条密封+鹰嘴滴水槽·女儿墙压顶坡度≥5%·水落口杯固定+涂膜附加层+伸入杯内≥50mm·穿楼板套管密封+高出装饰面≥20mm. coarse 考点教材锚集中(本体卡少), 判分眼靠真题侧 _F04_exam_evidence.json 补(2015案例2 防水细部节点错误辨析为强真题锚).",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"F04 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
