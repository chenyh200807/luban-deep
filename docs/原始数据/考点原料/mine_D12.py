#!/usr/bin/env python3
"""D12 饰面砖/板施工质量与空鼓防治 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 D12 真采分点, 产 _D12_compiled_source.json (照 C06/S06/S07 结构).

考点身份 (注册表 slot 22, **composite**):
  primary  1A413064 墙体饰面工程施工
  support  1A413130 饰面砖工程 / 1A434000-B054 裱糊与软包工程中壁纸或墙布空鼓 / 1A434034 建筑装饰装修工程质量通病防治
  四 code 全 resolve(4/4, 零漂移, taxonomy sha 26dbb542...).

  编译库现实(直读核真):
    - 真正的"墙柱面饰面板/石材施工方法"判分眼集中在 chunk 1A413030_144_0279
      (leaf 1A413064-R02/R14/R15 墙、柱面石材施工/饰面板工程): 干挂法(短槽/背槽/背栓)/干粘法/湿贴法;
      干挂需工厂加工挂件+石材六面防护; 湿贴铲除背网; 薄型小规格块材(≤10mm厚,<40cm边长)可粘贴,粘贴厚度8~10mm;
      后置埋件拉拔力合格; 湿作业法石板防碱封闭; 金属板防雷接通; 复验=花岗石放射性/人造木板甲醛/水泥基粘结料粘结强度/外墙陶瓷板吸水率/严寒陶瓷板抗冻性.
    - "饰面砖粘贴"判分眼集中在 chunk 1A413030_145_0280
      (leaf 1A413064-R16 饰面砖粘贴·名实最相符 primary 子项): 复验=瓷质砖放射性/水泥基粘结材料与外墙砖拉伸粘结强度/外墙陶瓷砖吸水率/严寒寒冷地区外墙砖抗冻性;
      工艺=排砖分格弹线/粘结剂厚度3~8mm/调整期内可微调/超时严禁振动/填缝先水平后垂直.
    - **空鼓防治判分眼**: 编译库**无"饰面砖/板专门空鼓防治"教学锚**, 真空鼓防治5要点在
      chunk 1A434000_078_0123(leaf 1A434000-B011 地面板块类地面空鼓·施工质量管理章·**地面块料**): 基层清理干净/水泥基粘结材料/油性防护石材用界面剂+背砂/大面积铺贴设伸缩缝/养护到位.
      地面瓷砖/石材面层(chunk 1A413030_140_0272/0273)有浸砖/浸湿防空鼓机理 + EP grading_keywords(浸砖/脱模剂/阴干/空鼓/结合层砂浆 等). 这些是空鼓防治本体最接近的真锚, 作主轴(地面板块)+邻接(墙面砖借力).

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前 8 个新产都踩过):
  - registry supporting `1A434000-B054`(taxonomy名"裱糊与软包工程中壁纸或墙布空鼓") 在 chunk 1A434000_079_0125
    **实际内容=涂饰色泽不均流坠 + 裱糊(壁纸/软包)空鼓** —— 是**软包/裱糊空鼓**, 非饰面砖/板空鼓.
    名实部分不符(taxonomy 节点名对得上"裱糊软包空鼓", 但与 D12 核心"饰面砖/板空鼓"是相邻不同概念): 取作🔵邻接外延(裱糊软包空鼓口径), 不当饰面砖/板空鼓主采分点.
  - registry supporting `1A413130`(饰面砖工程) 是 taxonomy 节点, **编译库内无独立 1A413130-* leaf**; 真饰面砖判分锚是 primary 子项 leaf `1A413064-R16饰面砖粘贴`(chunk 0280). 标 source_ref 缺口留痕.
  - registry supporting `1A434034`(建筑装饰装修工程质量通病防治) 是**章节级节点**, 编译库内无独立 1A434034-* leaf;
    最近的可锚空鼓通病叶子是同章 `1A434000-B011`(地面板块空鼓·已收作主轴)/`1A434000-B054`(软包空鼓·邻接). 标 coarse 缺口留痕.
  - 涂料/涂饰(chunk 1A413030_142_0277 乳胶漆/氟碳漆/美术漆)是**墙体饰面工程同章但非砖/板/石材镶贴**: 仅取"分格缝"相关作🔵邻接(分格缝是 D12 关键词), 涂饰流程/VOC检测非饰面砖/板空鼓判分眼, 绕开留痕.
  - 与 D11抹灰/D13幕墙 区分: 抹灰(基层找平砂浆)是饰面前道工序非本考点; 幕墙(玻璃/金属板幕墙·结构胶·龙骨体系)是独立大考点, 干挂石材≠幕墙. 仅在边界声明点名, 不展开.
  - 与建筑材料章(1A412010 石材/陶瓷材料性能)区分: 材料特性(吸水率/放射性数值)是材料考点眼, 本 pack 只取"复验项目"(施工质量验收侧), 不展开材料性能数值.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_D12_compiled_source.json")

KEYWORDS = ("饰面砖|饰面板|外墙砖|内墙砖|面砖|石材|镶贴|粘贴|满粘|空鼓|脱落|开裂|勾缝|背栓|干挂|湿贴|"
            "粘结强度|拉拔|拉拔强度|样板|界面剂|防水|分格缝|嵌缝")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP ; "ext"=邻接外延(标🔵外延, 非 D12 主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (墙柱面饰面板/石材施工方法判分眼) ──
    ("1A413030_144_0279", "1A413064-R02"): ("full", "本体·primary子项 墙、柱面石材施工/饰面板工程(判分眼): 干挂法(短槽/背槽/背栓)/干粘法/湿贴法; 干挂工厂加工挂件+石材六面防护; 湿贴铲除背网; 薄型小规格块材≤10mm厚<40cm边长可粘贴厚8~10mm; 后置埋件拉拔力合格; 湿作业法石板防碱封闭; 金属板防雷接通; 复验=花岗石放射性/人造木板甲醛/水泥基粘结料粘结强度/外墙陶瓷板吸水率/严寒陶瓷板抗冻性"),
    # ── 主轴本体 (饰面砖粘贴判分眼) ──
    ("1A413030_145_0280", "1A413064-R16"): ("full", "本体·primary子项 饰面砖粘贴(名实最相符·判分眼): 复验=瓷质砖放射性/水泥基粘结材料与外墙砖拉伸粘结强度/外墙陶瓷砖吸水率/严寒寒冷地区外墙砖抗冻性; 工艺=排砖分格弹线/粘结剂厚度3~8mm/调整期内微调/超时严禁振动/填缝先水平后垂直"),
    # ── 主轴本体 (空鼓防治真锚——地面板块空鼓5要点) ──
    ("1A434000_078_0123", "1A434000-B011"): ("full", "本体·空鼓防治真锚(地面板块·施工质量管理章): 地面空鼓防治5要点=基层清理干净/水泥基粘结材料/油性防护石材用界面剂+背砂/大面积铺贴设伸缩缝/养护到位. ⚠️编译库内无'饰面砖板专门空鼓防治'锚, 此为最接近的空鼓防治判分眼(地面板块, 墙面砖空鼓防治原理同源借力)"),
    # ── 邻接外延 (地面石材/瓷砖面层——块料镶贴防空鼓机理) ──
    ("1A413030_140_0272", "1A413063-R05"): ("ext", "邻接外延·地面石材饰面施工(块料镶贴防空鼓机理): 基层处理→放线→试拼→铺砂浆→铺石材→养护→勾缝; 大理石/花岗石铺设前浸湿晾干防吸水空鼓; 浅色石材用白水泥; 勾缝清晰顺直深浅一致. 地面块料非墙面饰面砖, 标🔵邻接(防空鼓原理可借力)"),
    ("1A413030_140_0273", "1A413063-R04"): ("ext", "邻接外延·地面瓷砖面层施工(块料镶贴防空鼓机理): 基层处理→放线→浸砖→铺砂浆→铺砖→养护→勾缝; 铺贴前清理脱模剂必要时充分浸泡阴干; 未浸砖致空鼓(EP grading_keywords=浸砖/脱模剂/阴干/空鼓/结合层砂浆). 地面块料非墙面饰面砖, 标🔵邻接"),
    # ── 邻接外延 (软包/裱糊空鼓——名实不符 supporting B054) ──
    ("1A434000_079_0125", "1A434000-B054"): ("ext", "邻接外延·registry supporting 裱糊与软包空鼓(名实部分不符): 涂饰色泽不均流坠(施工不当/温湿度异常/稀释剂挥发过快); 裱糊空鼓(底胶不匀/刷胶时间失控/赶压不当/基面不平). ⚠️=软包/裱糊空鼓, 与 D12 核心'饰面砖/板空鼓'相邻不同概念, 标🔵邻接不当主采分"),
}

# ext 模式剔除噪声卡(壁纸软包分类等非空鼓判分眼)
EXT_NOISE = re.compile(r"壁纸.*分类|软包.*分类|乳胶漆|氟碳漆|美术漆|VOC|游离甲醛")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A413130(饰面砖工程·registry supporting)": "taxonomy 节点 resolve 通过但**编译库内无独立 1A413130-* leaf**, 真饰面砖判分锚=primary子项 leaf 1A413064-R16饰面砖粘贴(chunk 0280已收). source_ref 缺口留痕, 与 1A413064 同腹地",
    "1A434034(建筑装饰装修工程质量通病防治·registry supporting)": "taxonomy **章节级节点** resolve 通过但编译库内无独立 1A434034-* leaf, 最近可锚空鼓通病叶子=同章 1A434000-B011(地面板块空鼓·已收主轴)/B054(软包空鼓·已收邻接). coarse 缺口留痕",
    "1A413030_142_0277(乳胶漆/氟碳漆/美术漆/涂饰)": "墙体饰面工程同章但=涂料涂饰(非砖/板/石材镶贴); 涂饰流程/VOC检测/苯甲苯检测非饰面砖板空鼓判分眼; '分格缝'概念已在饰面砖粘贴工艺侧覆盖, 涂料专项绕开归涂饰考点",
    "1A413030_144_0279(R14/R15 饰面板工程/分类)": "与 R02(墙柱面石材施工)同 chunk 共用同 4 张卡, R02 已收(primary子项名实相符). R14/R15 同卡不重复收(留痕)",
    "1A412010_*(石材/陶瓷/建筑陶瓷材料性能)": "天然花岗石/大理石/人造石材/建筑陶瓷的材料特性(吸水率/放射性/抗冻数值)是**材料性能考点**(1A412010章), 本 pack 只取施工验收侧'复验项目', 材料性能数值绕开归材料考点",
    "1A413030_140_0272/0273(地面工程其余卡·变形缝/楼地面构造)": "地面石材/瓷砖面层只取'铺贴防空鼓机理'卡作🔵邻接, 楼地面构造/变形缝等非块料镶贴防空鼓的卡绕开归地面工程考点",
    "D11抹灰/D13幕墙": "抹灰(基层找平砂浆)是饰面前道工序非本考点; 幕墙(玻璃/金属板幕墙·结构胶·龙骨体系)是独立大考点(干挂石材≠幕墙); 仅边界声明点名不展开",
    "饰面砖/板专门空鼓防治源锚缺口": "⚠️编译库内**无'外墙饰面砖/板专门空鼓防治'教学锚**(全库扫描: 空鼓防治5要点锚只在 1A434000-B011 地面板块空鼓). 墙面饰面砖空鼓防治判分眼靠地面板块原理借力 + 真题侧 _D12_exam_evidence.json. 这是 composite/source_ref 缺口根因",
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
        "考点": "D12 饰面砖/板施工质量与空鼓防治",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "composite (slot 22, primary 1A413064/support 1A413130·1A434000-B054·1A434034 全 resolve 4/4; 但'饰面砖板专门空鼓防治'编译库无锚, 空鼓判分眼靠地面板块原理+真题侧, 标 source_ref 缺口)",
        "编译库覆盖说明": "registry primary 1A413064(墙体饰面工程施工) 名实相符为腹地; 真判分眼: 墙柱面饰面板/石材施工方法集中 chunk 1A413030_144_0279(leaf 1A413064-R02·干挂短槽/背槽/背栓+干粘+湿贴/后置埋件拉拔力/六面防护/薄型小规格≤10mm<40cm粘贴8~10mm/复验粘结强度); 饰面砖粘贴集中 chunk 1A413030_145_0280(leaf 1A413064-R16·复验拉伸粘结强度/排砖分格弹线/粘结剂3~8mm/调整期/严禁振动/填缝先水平后垂直). ⚠️**空鼓防治**: 编译库无'饰面砖/板专门空鼓防治'锚, 真空鼓防治5要点在 chunk 1A434000_078_0123(leaf 1A434000-B011 地面板块空鼓·基层清理/水泥基粘结/界面剂+背砂/伸缩缝/养护)——地面块料口径, 墙面砖空鼓防治原理同源借力 + 真题侧补. supporting 1A413130(饰面砖工程)/1A434034(装饰装修通病防治)taxonomy resolve 通过但编译库无独立 leaf, 真锚走 primary 子项 + 同章 B011/B054. supporting 1A434000-B054(裱糊软包空鼓)名实部分不符(=软包空鼓非饰面砖板空鼓)标🔵邻接. composite 考点弹药本体集中(干挂/湿贴/饰面砖粘贴), 空鼓防治判分眼靠地面板块原理+真题侧.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"D12 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
