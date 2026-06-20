#!/usr/bin/env python3
"""D13 幕墙防火/防雷/层间封堵构造 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 D13 真采分点, 产 _D13_compiled_source.json (照 S06/S07/C06 结构).

考点身份 (注册表 slot 23, **direct**):
  primary  1A413134 建筑幕墙防火、防雷和成品保护技术要求  (canonical 专属叶子, resolve ✅)
  support  1A413065-R10 建筑幕墙的防雷构造要求 / 1A413065-R11 建筑幕墙防火、防雷和成品保护技术要求 /
           1A413065-R12 建筑幕墙防火构造要求  (resolve ✅ ✅ ✅)
  ⚠️ 注册表/编译库现实(直读核真):
     - canonical 主锚 1A413134 是 taxonomy 树上的【建筑幕墙防火/防雷/成品保护】专属判断节点(name 与 D13 完全相符),
       属 `direct`(非 coarse_review). 但 1A413134 在编译库 bundle 内**无独立 record**——真正承载教学卡的编译库 chunk
       挂在 1A413065-R10/R11/R12 系列(同一"建筑幕墙工程施工"叶子族的细分 leaf), 作弹药内部引用与 canonical 主锚并存.
     - 真正的"防火构造三尺寸判分眼"集中在 chunk 1A413030_148_0286 (leaf 1A413065-R11/R12·防火构造要求):
       上下层开口间实体墙≥1.2m 或 防火挑檐宽≥1.0m 且长度≥开口宽; 窗槛墙空腔上下沿矿物棉填塞高度≥200mm;
       钢质承托板厚≥1.5mm; 同一玻璃单元不跨两个防火分区. **逐尺寸核真.**
     - 真正的"防雷构造判分眼"集中在 chunk 1A413030_148_0287 (leaf 1A413065-R10·防雷构造要求):
       金属框架与主体防雷体系可靠连接; 铝合金立柱≤10m 范围宜一根柔性导线连通上下柱; 均压环楼层预埋件用圆钢/扁钢
       与均压环焊接连通. **逐条核真.**
     - 成品保护(chunk 0288·leaf R09)名义被 registry support R11"防火、防雷和成品保护"涵盖, 但成品保护判分眼弱,
       标🔵邻接(警示标识/保护膜不提前撕/清洗不上下同时作业).
     - 幕墙分类(chunk 0281·leaf R07/R08)含隐框/明框/半隐框分类体系, 是 D13 题干的背景定性层, 标🔵通识.
     - 层间封堵"封堵材料"(防火堵料三类/防火板材)在材料层 chunk 1A412010_066_0130 系列(leaf 1A412010-B152/G01),
       属【结构工程材料·建筑防火材料】材料锚, 标🔵材料外延(真题2015第23题"有机防火堵料"印证).

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前 8 个新产都踩过):
  - chunk 1A413030_148_0286: 两个 leaf(R11"防火、防雷和成品保护技术要求" / R12"防火构造要求")**共用同一张防火构造卡**
    (内容完全相同: 1.2m/1.0m/200mm/1.5mm/不跨防火分区). 只取 R11(registry support, 名义最全)作本体锚,
    R12 同卡不重复收(留痕).
  - chunk 1A413030_147_0284 (leaf R02/R14/R16/R18 全玻/点支承/石材/金属幕墙): 共用一张"全玻10mm/石材25mm/金属流程/
    点支承预拉力"安装构造卡 —— 属【幕墙面板安装构造】, **非 D13 防火/防雷/封堵判分眼**, 全部绕开(归幕墙安装本体, 与 D13 不同采分轴).
  - chunk 1A413030_146_0283/145_0281 (leaf R03~R08·分类/安装要点/横梁立柱): 分类体系作🔵通识背景定性(隐框/明框/半隐框),
    其余安装要点(横梁/立柱/结构胶)属幕墙安装非 D13, 仅取分类卡作🔵, 余绕开.
  - 材料层 1A412010-* 海量水泥/砂/石/混凝土/木材/玻璃/涂料 chunk: 与 D13 无关, 仅取防火堵料/防火板材(B152/G01)作🔵材料外延.
  - 与 D12(饰面砖/外墙保温)区分: D12 是饰面层粘贴/保温层, D13 是幕墙体系防火防雷封堵, 不混.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_D13_compiled_source.json")

KEYWORDS = ("幕墙|玻璃幕墙|石材幕墙|金属幕墙|防火|层间防火封堵|防火封堵|层间封堵|防雷|均压环|防雷连接|烟囱效应|"
            "窗间墙|窗槛墙|隐框|明框|半隐框|预埋件|挂件|防火岩棉|镀锌钢板|耐火极限|防火裙板|挑檐|承托板|柔性导线|防火堵料")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (本体判分眼) ; "ext"=邻接外延/通识(标🔵, 非 D13 防火防雷封堵主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (防火构造三尺寸判分眼) ──
    ("1A413030_148_0286", "1A413065-R11"): ("full", "本体·registry support 幕墙防火构造要求(判分眼): 上下层开口间实体墙≥1.2m 或防火挑檐宽≥1.0m且长≥开口宽; 窗槛墙空腔上下沿矿物棉填塞高度≥200mm; 钢质承托板厚≥1.5mm; 同一玻璃单元不跨两个防火分区. **逐尺寸核真**"),
    # ── 主轴本体 (防雷构造判分眼) ──
    ("1A413030_148_0287", "1A413065-R10"): ("full", "本体·registry support 幕墙防雷构造要求(判分眼): 金属框架与主体防雷体系可靠连接; 铝合金立柱≤10m范围宜一根柔性导线连通上下柱; 均压环楼层预埋件用圆钢/扁钢与均压环焊接连通形成防雷通路. **逐条核真**"),
    # ── 邻接外延 (成品保护——registry R11 名义涵盖但判分眼弱) ──
    ("1A413030_148_0288", "1A413065-R09"): ("ext", "邻接外延·幕墙成品保护与清洗(registry R11名义含'成品保护'但判分眼弱): 易撞易碎部位设警示标识; 保护膜不提前撕除; 清洗前制定方案; 严禁同一垂直方向上下面同时作业. 标🔵邻接"),
    # ── 通识背景 (幕墙分类——题干定性层) ──
    ("1A413030_145_0281", "1A413065-R07"): ("ext", "通识背景·建筑幕墙分类(D13题干定性层): 按面板材料分玻璃/金属板/金属复合板/石材/人造板材; 玻璃幕墙按构造分明框/隐框/半隐框/全玻/点支承; 按支承分框支承/肋支承/点支承; 按施工分构件式/单元式. 标🔵通识(非防火防雷封堵判分眼)"),
    # ── 材料外延 (层间封堵材料——防火堵料/防火板材) ──
    ("1A412010_066_0130", "1A412010-B152"): ("ext", "材料外延·建筑防火封堵材料(结构工程材料层): 防火堵料分三类有机(可塑性)/无机(速固型)/防火包(耐火包); 膨胀型钢结构防火涂料涂层厚≥1.5mm非膨胀型≥15mm; 防火板材含硅酸钙板/耐火纸面石膏板/矿物棉板等. 真题2015第23题'有机防火堵料'印证. 标🔵材料外延(非幕墙构造判分眼但层间封堵选材锚)"),
}

# ext 模式剔除噪声卡(全玻/石材/金属厚度等幕墙安装非D13判分眼, 防火玻璃自爆等跑题)
EXT_NOISE = re.compile(r"自爆|硫化镍|均质|夹层玻璃由|花纹板|蜂窝芯|龙骨|全玻璃墙面板|点支承.*预拉力|石材.*25mm|金属幕墙施工流程")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A413030_148_0286(R12 防火构造要求)": "与 R11(防火、防雷和成品保护技术要求)同 chunk 同卡(完全相同的防火构造尺寸卡: 1.2m/1.0m/200mm/1.5mm/不跨防火分区), R11已收(registry support名义最全), R12不重复收",
    "1A413030_147_0284(R02/R14/R16/R18 全玻/点支承/石材/金属幕墙)": "共用'全玻10mm/石材25mm/金属流程/点支承预拉力'安装构造卡 —— 属【幕墙面板安装构造】采分轴, 非D13防火/防雷/封堵判分眼, 全部绕开归幕墙安装本体(D13题干背景可借, 不当采分点)",
    "1A413030_146_0283(R03~R06/R13/R15/R17 单元式/安装要点/横梁/立柱/结构胶)": "幕墙安装施工要点(横梁立柱安装/结构胶) —— 属幕墙安装本体非D13防火防雷封堵, 仅 R07分类卡作🔵通识背景, 余绕开",
    "1A413030_145_0281(R08 建筑幕墙工程施工)": "与 R07(建筑幕墙分类)同 chunk 共用分类卡, R07已收作🔵通识, R08不重复",
    "1A413030_148_0285(R01 人造板材幕墙)": "人造板材幕墙适用条件/接缝方式(瓷板/陶板/木纤维板可封可开) —— 属幕墙面板选型, 真题2022第27题人造板面板印证但非D13防火防雷封堵判分眼, 绕开归幕墙分类外延(分类卡R07已点名'人造板材')",
    "1A412010-* 海量材料层(水泥/砂/石/混凝土/木材/玻璃/涂料/防水卷材)": "结构工程材料层与D13无关, 仅取 B152/G01(防火堵料/防火板材)作🔵材料外延; 防火玻璃B154(含自爆/均质跑题内容)、密封材料B048/B049(密封胶分类非封堵判分眼)绕开",
    "D12(饰面砖/外墙保温)territory": "饰面层粘贴/外墙保温属D12采分轴, D13是幕墙体系防火防雷封堵, 严格分界不混(2015案例2同背景含外墙保温复验/屋面卷材防水, 均非D13判分眼)",
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
        sps = []
        idx = 0
        captured = set()
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            content = t.get("content", "") or ""
            title = t.get("title", "") or ""
            if not content.strip():
                continue
            blob = title + content
            if mode == "ext" and EXT_NOISE.search(blob):
                continue
            prefix = "[🔵邻接/通识/材料外延] " if mode == "ext" else ""
            sps.append({
                "statement": prefix + (title + "：" + content).strip("："),
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
            if mode == "ext" and EXT_NOISE.search(rt):
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
            desc = e.get("content", "") or e.get("description", "") or ""
            gk = e.get("grading_keywords", [])
            if not (desc or gk):
                continue
            if mode == "ext" and EXT_NOISE.search(desc):
                continue
            sps.append({
                "statement": desc,
                "required_terms": gk,
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(gk),
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
        "考点": "D13 幕墙防火/防雷/层间封堵构造",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 23, canonical 专属叶子 1A413134 resolve✅; 编译库锚挂 1A413065-R10/R11/R12)",
        "编译库覆盖说明": "registry primary 1A413134(建筑幕墙防火、防雷和成品保护技术要求)是 canonical taxonomy 专属判断节点(name 与 D13 完全相符, resolve✅, 故 direct 非 coarse_review). 1A413134 在编译库 bundle 内无独立 record——真正承载教学卡的编译库 chunk 挂在 supporting leaf 1A413065-R10/R11/R12(同'建筑幕墙工程施工'叶子族细分 leaf), 作弹药内部引用与 canonical 主锚并存. 防火构造三尺寸判分眼(实体墙≥1.2m/挑檐≥1.0m/空腔填塞≥200mm/钢承托板≥1.5mm/不跨防火分区)集中在 chunk 1A413030_148_0286(leaf 1A413065-R11/R12); 防雷构造判分眼(金属框架连主体防雷/立柱≤10m柔性导线/均压环预埋件焊接)集中在 chunk 1A413030_148_0287(leaf 1A413065-R10). 成品保护(0288·R09)/分类(0281·R07)标🔵; 层间封堵选材(防火堵料三类)在材料层 chunk 1A413030_066_0130(leaf 1A412010-B152)标🔵材料外延, 真题2015第23题印证. ⚠️真题侧关键补料: 2015案例2'楼板/隔墙缝隙不燃材料封堵+岩棉/矿棉厚度≥100mm+水平防火烟带+1.5mm镀锌钢板承托不得用铝板'是层间防火封堵判分眼真题锚(与教材200mm空腔填塞为不同部位尺寸, 详见 pack §8 textbook-vs-exam 辨析).",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"D13 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:48]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
