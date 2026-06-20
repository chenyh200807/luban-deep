#!/usr/bin/env python3
"""C06 砌体留槎与构造柱 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 C06 真采分点, 产 _C06_compiled_source.json (照 C01/S05/N01 结构).

考点身份 (注册表 slot 15, **coarse_review**):
  primary  1A413081 砖砌体工程
  support  1A413083 填充墙砌体工程 / 1A413042-R03 填充墙砌体工程 / 1A413030-G01 砌体墙临时施工洞口留置规定
  ⚠️ 注册表注: 缺精确 leaf, 只能先锚砖砌体/填充墙/洞口留置; 本 pack 标 coarse_review + needs_leaf_review, 不进学员默认入口.

  编译库现实: 注册表 canonical code(1A413081/1A413083) 是【块体材料】节点(砖砌体/填充墙材料), 真正的
  "砌体留槎/构造柱/拉结筋施工" 教学锚集中在 RichLeaf 编译库的 **1A413042-*(砌体结构工程施工)**
  系列 leaf(chunk 1A413030_105~109_*), 名实相符直读核真确属砌体施工本体. 故 pack 教材锚以 1A413042-* / 1A413030-G01
  为弹药内部引用, 与注册表 canonical 1A413081/1A413083(块体材料锚)并存(收口对账记此差异).

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前面 5 个新产都踩过):
  - 必须核 compiled_context 真实内容确属 "砌体留槎(斜槎/直槎)/构造柱马牙槎(先退后进)/拉结筋(500mm)/
    临时施工洞口(≤1m/≥500mm)/咬槎搭砌" 砌体施工本体, 名实不符绕开并留痕.
  - 与 A01(验收/主控项目)/C04(拆模)/C01(施工缝)/Q03(质量通病) 区分:
    * 砖砌体/填充墙【主控项目·砂浆饱满度80%/90%】是 A01 验收 territory, 但"转角交接同时砌筑/严禁分砌"
      与 C06 留槎咬槎本体强相关 → 只取"同时砌筑/咬槎"采分眼作 🔵→🟢 外延, 饱满度数值标 🔵 外延(验收锚).
    * 填充墙裂缝防治(2φ6@500mm/14d后施工/半砖斜砌) 在 chunk 1A434000_074_0116, 是 Q03 质量通病 territory,
      且该 chunk 名实不符(混入焊缝夹渣/地基沉降/防水渗漏多卡) → 标 🔵 外延邻接参照, 不当 C06 留槎采分点.
  - 砌筑砂浆配合比(R13)/防潮层(R02)/脚手眼禁止(R06)/皮数杆(R10)/质量检查(R14) 属砌体施工通识,
    与"留槎/构造柱"主轴邻接, 取作 🟢 本体外延(同 chunk 砌体施工), 但主轴判分眼集中在 R08/R11/R16(留槎构造柱) + R01/G01(洞口) + R04/R09/R17/R18(填充墙/砌块咬槎).
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_C06_compiled_source.json")

KEYWORDS = ("砌体|砌筑|留槎|马牙槎|构造柱|斜槎|直槎|拉结筋|拉结钢筋|填充墙|砖砌体|多孔砖|组砌|留置|接槎|"
            "咬槎|先退后进|先砌墙后浇柱|2皮砖|500mm|洞口留置|皮数杆|临时施工洞口|搭接|同时砌筑|空心砖|砌块")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP ; "ext"=本体外延(同砌体施工, 标本体外延); "wai"=验收/通病外延(标🔵外延, 不作 C06 留槎主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (留槎 / 构造柱 / 拉结筋 / 洞口 / 咬槎) ──
    ("1A413030_107_0210", "1A413042-R08"): ("full", "本体·primary 主轴: 烧结砖砌体(灰缝10mm/8~12mm) + 斜槎/直槎规则(8度及以上须斜槎/普通砖斜槎水平投影≥高2/3、多孔砖斜槎长高比≥1/2/非抗震可直槎但加拉结筋) + 构造柱马牙槎(先退后进/沿高≤300mm/凹凸60mm/沿墙高每500mm拉结钢筋) — C06 判分眼最集中卡"),
    ("1A413030_106_0208", "1A413042-R01"): ("full", "本体·primary 临时施工洞口: 净宽≤1m、距交接面≥500mm、宜设过梁或挑砖封口、预埋拉结筋、9度抗震须设计确认、墙梁部分不宜留洞"),
    ("1A413030_106_0208", "1A413030-G01"): ("full", "本体·注册表 supporting G01 同 chunk(砌体墙临时施工洞口留置规定): 内容与 R01 同卡, 作注册表 supporting 锚 + 洞口留置采分眼"),
    ("1A413030_106_0204", "1A413042-R12"): ("ext",  "本体外延·砌体砌筑顺序: 低处先砌/高处搭接(搭接长度≥高差)/转角交接同步/出檐后砌/高差大者先砌(高差1.2m搭接EP)"),
    ("1A413030_106_0206", "1A413042-R10"): ("ext",  "本体外延·皮数杆: 转角和交接处设置, 间距不宜大于15m"),
    ("1A413030_106_0207", "1A413042-R14"): ("ext",  "本体外延·砌体质量检查: 垂直度/平整度/灰缝厚度/砂浆饱满度终凝前校正, 每层校核轴线标高"),
    ("1A413030_106_0209", "1A413042-R06"): ("ext",  "本体外延·脚手眼禁止部位: 120mm墙/清水墙/料石墙/独立柱/过梁三角区/窗间墙<1m/门窗洞口旁/梁下500mm/轻质墙/夹心墙外叶"),
    ("1A413030_105_0202", "1A413042-R13"): ("ext",  "本体外延·砌筑砂浆配合比设计(配合比/试配/稠度/保水率/抗压强度)"),
    ("1A413030_106_0205", "1A413042-R02"): ("ext",  "本体外延·基础墙防潮层(1:2.5水泥砂浆+防水剂/20mm/抗震区严禁卷材)"),
    # ── 填充墙 / 砌块 留槎咬槎本体 ──
    ("1A413030_109_0212", "1A413042-R04"): ("full", "本体·填充墙施工: 拉结筋化学植筋须实体检测 + 连接构造不得随意改变须设计同意 + 钻孔镂槽切锯须专用工具严禁剔凿/预留洞预埋件砌前设置"),
    ("1A413030_109_0213", "1A413042-R09"): ("full", "本体·烧结空心砖砌体: 侧立砌筑孔洞水平 + 底部3皮普通砖 + 上下错缝交接处咬槎搭砌/转角交接同时砌筑不得留直槎/斜槎高度≤1.2m — 咬槎/留槎本体"),
    ("1A413030_109_0214", "1A413042-R18"): ("full", "本体·轻骨料砌块: 纵横墙交接转角同时砌筑/不能同时砌筑应留斜槎(斜槎水平投影≥高2/3)/孔洞填充逐皮填满不捣实 — 留斜槎本体"),
    ("1A413030_109_0215", "1A413042-R17"): ("ext",  "本体外延·蒸压加气砌块: 上下错缝搭接≥块长1/3且≥150mm不足设钢筋加强/薄层砂浆专用粘结/灰缝2~4mm/错位>2mm磨平"),
    ("1A413030_108_0211", "1A413042-R03"): ("ext",  "本体外延·小砌块/填充墙: 龄期≥28d/底面朝上反砌/灰缝10mm/日砌高≤1.4m + 砌块禁用条件(防潮层下/长期浸水/化学侵蚀/温度>80℃/振动) + 厨卫底部现浇坎台150mm"),
    # ── 验收/通病外延(标🔵外延, 不作 C06 留槎主采分点) ──
    ("1A434000_067_0100", "1A434000-B048"): ("wai", "外延·砖砌体主控项目(A01验收territory): 砂浆饱满度墙≥80%/柱≥90%(标🔵验收锚) + 转角交接处同时砌筑严禁内外墙分砌(此句与C06留槎咬槎本体相通, 取作🟢外延) + 填充墙可靠连接须设计同意"),
    ("1A434000_074_0116", "1A434000-B013"): ("wai", "外延·填充墙裂缝防治(Q03质量通病territory, 且chunk名实不符混焊缝/地基/防水多卡): 柱墙边2φ6@≤500mm/填充墙与主体间空隙砌后14d再施工/空心砖内侧半砖斜砌/加强网片 — 标🔵外延邻接参照, 非C06留槎主采分点"),
}

# wai 模式: 只保留 title/content 含这些"留槎/咬槎/同时砌筑/拉结"本体词的卡, 余防水/焊缝/地基卡绕开
WAI_KEEP = re.compile(r"同时砌筑|咬槎|留槎|斜砌|拉结|分砌|2φ6|500mm|饱满度|交接处|半砖斜砌|加强网片|14d|14天")
NOISE_BLOCK = re.compile(r"焊缝|夹渣|地基不均|沉降缝|防水|渗漏|止水|涂料|卷材|管道穿墙")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A411011_033_0060(1A411040-R01~R10)": "建筑设计与构造>建筑结构设计构造要求(圈梁/砌体中留槽洞/填充墙构造设计/独立砖柱240mm/砌块房屋) — 属【设计构造要求】章节(1A411040设计层), 命题语境是结构构造设计而非砌体施工留槎/构造柱马牙槎做法, 绕开归建筑构造设计考点",
    "1A411011_011/012_0021/0022(抗震措施/砌体结构房屋)": "建筑设计>抗震设计/抗震措施/砌体结构房屋/混凝土结构房屋 — 抗震设计层泛词(构造柱/圈梁作抗震措施提及), 非C06砌体施工留槎本体, 绕开归抗震设计",
    "1A412010_050~052_*(1A412010-B095~B130 块体/砂浆材料)": "建筑材料>结构工程材料(烧结砖/砌块/蒸压加气砌块/砂浆强度等级/块体强度) — 属【材料性能】考点(注册表1A413081/1A413083 名义对应块体材料), 命题考材料强度等级/种类, 非砌体施工留槎/构造柱做法, 绕开归材料考点(注: 注册表primary 1A413081砖砌体/1A413083填充墙是材料层节点, 真留槎构造柱施工锚在1A413042施工层, 收口对账记此名实差异)",
    "1A422000_029/036_*(相关法规 止水带/防水/砌体结构构造)": "相关法规>中埋式止水带/防水卷材/防水涂料/防水混凝土/砌体结构构造与施工(B122泛词) — 防水法规为主, 砌体仅泛词命中, 非C06留槎本体, 绕开",
    "1A413030_133_0254(1A413050-R25 涂膜防水)": "屋面与防水>涂膜防水施工 — 防水考点, '组砌/搭接'泛词命中, 绕开",
    "1A434000_074_0116(B005/B042/B046/B016/B067 焊缝/地基/防水)": "施工质量管理 chunk 0116 名实不符: 同一 chunk 混入焊缝夹渣防治/地基不均沉降裂缝/地下防水施工缝渗漏/屋面防水通病 多卡 — 仅其中'填充墙裂缝防治'卡(B013)与C06填充墙相关(已作🔵外延收), 焊缝/地基/防水卡全部绕开归各自考点(钢结构/Q03通病/防水)",
    "1A413030_105_0202(1A413042-R15 砌筑砂浆)": "砌筑砂浆 leaf R15 与 R13 同 chunk, R13已收(配合比), R15重复, 不重复收",
    "1A434000_067_0100(B047/B055/B056 质检通用)": "砌体结构工程质量检验与标准/质量检查主控项目/内容 — 与B048砖砌体主控同chunk, B048已收(取同时砌筑/饱满度), 通用质检泛词不重复收",
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
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "wai" and (not WAI_KEEP.search(blob) or NOISE_BLOCK.search(blob)):
                continue
            content = t.get("content", "") or ""
            prefix = "[🔵验收/通病外延] " if mode == "wai" else ""
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
        "考点": "C06 砌体留槎与构造柱",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "coarse_review (slot 15, needs_leaf_review, 不进学员默认入口)",
        "编译库覆盖说明": "注册表 canonical primary 1A413081(砖砌体)/1A413083(填充墙)为【块体材料】层节点; 真'砌体留槎/构造柱马牙槎/拉结筋'施工教学锚集中在 RichLeaf 编译库 1A413042-*(砌体结构工程施工)系列 leaf(chunk 1A413030_105~109_*) + 1A413030-G01(临时洞口), 名实相符直读核真. C06 主轴判分眼集中: 留槎(斜槎/直槎规则·8度斜槎/水平投影≥2/3/长高比≥1/2)、构造柱马牙槎(先退后进/≤300mm/凹凸60mm/沿墙高500mm拉结钢筋)、临时洞口(净宽≤1m/距交接面≥500mm/预埋拉结筋)、咬槎搭砌(转角交接同时砌筑不留直槎). 数值判读锚靠真题侧 _C06_exam_evidence.json. coarse 考点弹药教材锚集中(主轴卡少), 判分眼靠真题侧补.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"C06 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
