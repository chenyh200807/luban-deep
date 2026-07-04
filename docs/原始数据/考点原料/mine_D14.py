#!/usr/bin/env python3
"""D14 吊顶/门窗/地面装饰质量综合 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 D14 真采分点, 产 _D14_compiled_source.json (照 D12/C06 结构).

考点身份 (注册表 slot 24, **composite** 综合包):
  primary  1A413062 吊顶工程施工
  support  1A413063 地面工程施工 / 1A413061-R10 轻质隔墙门窗洞口安装 / 1A434034 建筑装饰装修工程质量通病防治
  四 code 全 resolve(taxonomy sha 26dbb542...).
  注册表 note: 「综合包; 细拆 D15/D16 前不得混成一个评分点」——本 pack 三子域(吊顶/地面/门窗)
  各自声明主/辅节点, 不混成单一采分点; D15(门窗细分)/D16(地面细分)为 conditional_split 候选, 本 pack 不预拆。

  编译库现实(直读核真, 2026-07-04 逐 chunk 核):
    ── 吊顶子域(primary 1A413062, 名实相符腹地) ──
      * chunk 1A413030_139_0268 (leaf 1A413062-R01 吊顶安装要求·判分眼):
        主龙骨间距≤1200mm/悬臂段≤300mm/接头错开; 次龙骨≤600mm不搭接/洞口周边设附加龙骨;
        纸面石膏板从中间向四周自由固定/长边纵向/螺钉150~170mm/钉眼防锈/双层板接缝错开.
      * chunk 1A413030_138_0267 (leaf 1A413022-E01 暗龙骨吊顶施工工艺):
        吊杆>1500mm设反支撑/>2500mm设钢结构转换层/遇梁风管设横担/不得直接吊挂设备/预埋杆件焊接/灯具风口设附加龙骨.
        ⚠️源库标签污染: 内容 100% 是吊顶工艺, 但 leaf_id 前缀=1A413022(地基与基础工程)——taxonomy 误挂,
        取作吊顶本体判分眼, 留痕(与 ENGINE §5 教训"leaf名实不符错挂旁系"同类).
      * chunk 1A434000_078_0124 (leaf 1A434000-B057 轻钢龙骨石膏板吊顶表面开裂·质量通病本体):
        石膏板顶棚防裂5要点=吊筋间距≤1200mm/拼缝错缝不密拼/螺钉固定牢固/转角加强/嵌缝饱满.
    ── 地面子域(support 1A413063, 名实相符) ──
      * 1A413030_140_0272 (leaf 1A413063-R05 石材饰面施工): 基层处理→放线→试拼→铺砂浆→铺石材→养护→勾缝; 石材铺前浸湿晾干防吸水空鼓; 浅色用白水泥.
      * 1A413030_140_0273 (leaf 1A413063-R04 瓷砖面层施工): 铺贴前清脱模剂/充分浸泡阴干; 未浸砖致空鼓(EP kw=浸砖/脱模剂/阴干/空鼓/结合层砂浆).
      * 1A413030_141_0274 (leaf 1A413063-R06 竹木地板): 基层处理→安装木搁栅→铺毛地板→铺竹木地板→成品保护; 毛地板开槽深板厚1/3/间距200mm/与搁栅垂直; 靠墙第一块离墙10mm/由内向外/顺光顺行走方向.
      * 1A413030_141_0275 (leaf 1A413063-R01 地毯面层): 基层→放线→剪裁→钉倒刺板→铺衬垫→铺地毯→收口; 裁剪比施工面长20mm/倒刺板距踢脚8~10mm/衬垫离倒刺板10mm; 先固定一长边撑子拉伸.
      * 1A434000_078_0123 (leaf 1A434000-B011 地面板块类空鼓、起拱·质量通病本体): 地面空鼓防治5要点=基层清理干净/水泥基粘结材料/油性防护石材用界面剂+背砂/大面积设伸缩缝/养护到位.
    ── 门窗子域(编译库覆盖弱, source_ref 缺口, 靠真题补) ──
      * 1A422000_043_0069 (leaf 1A422000-B156 门窗安装要求): 真门窗判分眼=在砌体上安装门窗严禁用射钉固定.
        ⚠️同 chunk 混入涂饰料(基层含水率溶剂型≤8%/乳液型≤10%/木材≤12%; 厨卫用耐水腻子)——是涂饰/找平采分眼,
        非门窗安装本体, 标🔵邻接混入, 门窗本体只取"严禁射钉".
      * 1A434000_080_0129 (leaf 1A434000-B066 门窗节能工程常见问题治理·质量通病本体):
        门窗节能常见问题=类型不符/传热系数超标/气密性差/中空玻璃露点高/可见光透射比不符.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_D14_compiled_source.json")

KEYWORDS = ("吊顶|主龙骨|次龙骨|吊杆|反支撑|龙骨|石膏板|罩面板|嵌缝|附加龙骨|"
            "地面|面层|地毯|瓷砖|石材饰面|竹木|木地板|毛地板|倒刺板|空鼓|起拱|勾缝|"
            "门窗|射钉|传热系数|气密性|中空玻璃|节能")

# 经人工核真的 (chunk, leaf) 白名单 + mode(full=本体判分眼 / ext=邻接外延·混入,标🔵) + 子域 note.
CHUNK_POLICY = {
    # ── 吊顶子域(primary 1A413062) ──
    ("1A413030_139_0268", "1A413062-R01"): ("full", "吊顶·本体 primary 吊顶安装要求(判分眼): 主龙骨≤1200mm悬臂≤300mm接头错开; 次龙骨≤600mm不搭接洞口设附加龙骨; 纸面石膏板中间向四周自由固定/长边纵向/螺钉150~170mm/钉眼防锈/双层接缝错开"),
    ("1A413030_138_0267", "1A413022-E01"): ("full", "吊顶·本体 暗龙骨吊顶施工工艺(判分眼): 吊杆>1500mm反支撑/>2500mm钢结构转换层/遇梁风管横担/不直接吊挂设备/预埋杆件焊接/灯具风口附加龙骨. ⚠️源库标签污染=吊顶内容误挂地基leaf 1A413022, 取作吊顶本体+留痕"),
    ("1A434000_078_0124", "1A434000-B057"): ("full", "吊顶·质量通病本体 轻钢龙骨石膏板吊顶开裂: 防裂5要点=吊筋≤1200mm/拼缝错缝不密拼/螺钉固定牢固/转角加强/嵌缝饱满"),
    # ── 地面子域(support 1A413063) ──
    ("1A413030_140_0272", "1A413063-R05"): ("full", "地面·本体 石材饰面施工: 基层→放线→试拼→铺砂浆→铺石材→养护→勾缝; 石材铺前浸湿晾干防吸水空鼓; 浅色石材白水泥"),
    ("1A413030_140_0273", "1A413063-R04"): ("full", "地面·本体 瓷砖面层施工: 铺贴前清脱模剂/充分浸泡阴干; 未浸砖致空鼓(grading_kw=浸砖/脱模剂/阴干/空鼓/结合层砂浆)"),
    ("1A413030_141_0274", "1A413063-R06"): ("full", "地面·本体 竹木地板: 基层→木搁栅→毛地板→竹木地板→成品保护; 毛地板开槽深板厚1/3/间距200mm/与搁栅垂直; 靠墙第一块离墙10mm/由内向外/顺光顺行走"),
    ("1A413030_141_0275", "1A413063-R01"): ("full", "地面·本体 地毯面层: 基层→放线→剪裁→钉倒刺板→铺衬垫→铺地毯→收口; 裁剪比施工面长20mm/倒刺板距踢脚8~10mm/衬垫离倒刺板10mm; 先固定长边撑子拉伸"),
    ("1A434000_078_0123", "1A434000-B011"): ("full", "地面·质量通病本体 板块类地面空鼓、起拱: 防治5要点=基层清理干净/水泥基粘结材料/油性防护石材用界面剂+背砂/大面积设伸缩缝/养护到位"),
    # ── 门窗子域(编译库弱, source_ref 缺口) ──
    ("1A422000_043_0069", "1A422000-B156"): ("full", "门窗·本体 门窗安装要求(判分眼极窄): 在砌体上安装门窗严禁用射钉固定. ⚠️同chunk混入涂饰料(含水率8%/10%/12%·耐水腻子)标🔵邻接非门窗本体"),
    ("1A434000_080_0129", "1A434000-B066"): ("full", "门窗·质量通病本体 门窗节能常见问题治理: 类型不符/传热系数超标/气密性差/中空玻璃露点高/可见光透射比不符"),
}

# ext 模式剔除的噪声(门窗chunk里的涂饰含水率/耐水腻子, 非门窗采分眼)——本 pack CHUNK_POLICY 全 full,
# 该正则供 note 声明的"邻接混入"提示, main 中对 full chunk 不过滤(保留全 chunk, 交 4谱系+jury 核).
EXT_NOISE = re.compile(r"耐水腻子|含水率.*(溶剂|乳液|木材)")

# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕).
SKIPPED = {
    "1A422000-B012(上步宽扫误当门窗)": "leaf 名'不同材料基体交接处抹灰防裂措施'(加强网搭接≥100mm)=**抹灰防裂**(D11抹灰腹地), 非门窗; chunk 1A413030误配, 绕开归 D11",
    "1A413061-R10(registry supporting·门窗洞口安装)": "注册表 supporting 给的 1A413061-R10 leaf_name_path=**轻质隔墙工程>门窗洞口安装**——是轻质隔墙里的洞口留置, 非独立门窗安装工程; 真门窗施工本体走 1A422000-B156(严禁射钉)+节能通病 B066. 标 supporting 名实偏差留痕, 门窗本体不锚 R10",
    "1A413062-R02/R03(1A413030_138_0264 吊顶施工/分类)": "chunk 1A413030_138_0264 的 compiled_context 空(TC=0/rule=0/EP=0), 无采分点可锚; 吊顶本体判分眼已在 R01(0268)+暗龙骨(0267)+开裂通病(B057)覆盖. 空 chunk 跳过留痕",
    "1A434034(registry supporting·装饰装修质量通病防治)": "taxonomy **章节级节点** resolve 通过但编译库内无独立 1A434034-* leaf; 三子域质量通病真锚=同章 1A434000-B057(吊顶开裂)/B011(地面空鼓)/B066(门窗节能)已全收. coarse 缺口留痕",
    "门窗施工本体源锚缺口": "⚠️编译库对'门窗安装施工工艺'覆盖极弱(仅 B156'严禁射钉'一条判分眼); 门窗子域深度靠 _D14_exam_evidence.json 真题侧补 + 4谱系原理层. 这是 composite 门窗子域 source_ref 缺口根因(与 D15 conditional_split 待拆同源)",
    "地面/石材 chunk 与 D12 共享": "1A413030_140_0272(石材)/0273(瓷砖)/1A434000-B011(地面空鼓) 同时被 D12(饰面砖空鼓·墙面借地面原理)引用; 本 D14 从**地面装饰质量本体**视角引用(非借力). pack 只引用不拥有, 同 chunk 多 pack 不同视角合法, 声明留痕",
}


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


def main() -> None:
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
            blob = title + content
            if mode == "ext" and EXT_NOISE.search(blob):
                continue
            prefix = "[🔵邻接/原理外延] " if mode == "ext" else ""
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
            if mode == "ext" and EXT_NOISE.search(desc):
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
        "考点": "D14 吊顶/门窗/地面装饰质量综合",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "composite (slot 24, primary 1A413062吊顶/support 1A413063地面·1A413061-R10隔墙门窗洞口·1A434034装饰通病; 三子域各声明主辅, 不混成单一采分点, D15/D16 conditional_split 不预拆; 门窗子域编译库弱=source_ref缺口靠真题补)",
        "编译库覆盖说明": "composite 三子域: ①吊顶(primary 1A413062名实相符腹地)=龙骨安装(主≤1200/次≤600/石膏板螺钉150~170) chunk 0268 + 暗龙骨吊杆(>1500反支撑/>2500转换层) chunk 0267[⚠️误挂地基leaf 1A413022] + 石膏板开裂防裂5要点 B057; ②地面(support 1A413063)=石材/瓷砖/竹木/地毯各面层施工 chunk 0272/0273/0274/0275 + 地面空鼓防治5要点 B011; ③门窗(编译库极弱)=仅门窗安装'严禁射钉' B156 + 节能通病B066, 门窗施工工艺深度靠真题侧补(source_ref缺口, 同D15待拆). supporting 1A413061-R10(注册表给)实为轻质隔墙门窗洞口非独立门窗, 名实偏差绕开; 1A434034(通病防治)章节级无独立leaf, 三子域通病真锚走同章B057/B011/B066. 地面 0272/0273/B011 与 D12 共享(D14从地面质量本体视角), pack只引用不拥有.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"D14 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 leaf: {len(SKIPPED)} 类")
    for u in units:
        dom = u["note"].split("·")[0]
        print(f"  [{dom:>4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
