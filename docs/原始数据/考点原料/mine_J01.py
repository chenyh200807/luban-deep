#!/usr/bin/env python3
"""J01 危大工程范围 + 专项方案 + 专家论证 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 J01 真采分点, 产 _J01_compiled_source.json (照 S05/C01/N01 结构).

考点身份 (注册表 slot 1, direct):
  primary  1A431030-E01 危大工程专家论证——主要内容 (= chunk 1A437000_010_0013)
  support  1A436000-B029 危大工程范围 (= chunk 1A436000_008_0011)
           1A436000-B158 超过一定规模的危大工程范围 (= chunk 1A436000_009_0012)

⚠️ 源库标签污染 + 跨考点防御 (C07/S05/N01/C01 都踩过):
  - leaf/chunk 名义 vs compiled_context 实际常错挂; 必须核 compiled_context 真实内容确属
    "危大工程范围判定 / 超规模判定 / 专项方案编制内容 / 专家论证程序+人数+利害关系 / 危大六项管理"(危大论证本体),
    名实不符绕开并留痕.
  - 跨考点切割: 危大范围/规模阈值数字 (3m/5m/8m/100kN/24m...) 是 J01 判分眼(范围判定题);
    但脚手架/模板/起重的【本体施工工艺】归 S01/S02/C04, 本 pack 只在"哪些工程算危大/超规模"层面点名,
    不展开各分项施工做法.
  - 重大事故隐患判定 (1A436000_007_0010 B031 chunk) 与危大未编/未审专项方案的法律后果相关:
    其 EP("未编制/未审核专项施工方案"语境)+"未编/未审专项方案=重大隐患"是 J01 法律后果外延锚,
    但该 chunk 的 8 张 TC 是各分项(基坑/模板/脚手架/起重/高处/临电/拆除)重大隐患清单=安全隐患考点腹地,
    与 J01 判分眼(范围/方案/论证)弱相关, 标🔵外延只取与"未编/未审专项方案"直接相关者, 余绕开.
  - 范围/规模阈值数字判读锚以 EP grading_keywords + 真题侧 _J01_exam_evidence.json 为准,
    教材锚以本 compiled_source 为准(诚实标注).
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_J01_compiled_source.json")

KEYWORDS = ("危大工程|危险性较大|分部分项工程|专项施工方案|专项方案|专家论证|超过一定规模|论证范围|方案编制|"
            "施工方案审核|监理审查|验收|应急预案|安全专项|论证程序|深基坑|高大模板|起重吊装|脚手架工程")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# 同一 chunk 多 leaf 挂(primary 1A431030-E01 与 1A422000-C01 同挂 1A437000_010_0013), 用 (chunk, leaf) 唯一定位.
# mode: "full"=取该 chunk 全部 TC/rule/EP/concept ; "tc_filter"=只取 title/content 含 J01 判读关键词的 TC/rule
CHUNK_POLICY = {
    # primary·专家论证主要内容 (1A431030-E01 = registry primary)
    ("1A437000_010_0013", "1A431030-E01"): ("full", "本体·primary 危大工程专家论证(总承包单位组织/专家≥5人/无利害关系/论证前须经施工单位审核+总监理工程师审查/论证报告签字确认)"),
    # support·危大工程范围 (1A436000-B029 = registry supporting)
    ("1A436000_008_0011", "1A436000-B029"): ("full", "本体·support 危大工程范围判定阈值(基坑≥3m/模板≥5m/起重单件≥10kN/脚手架≥24m)"),
    # support·超过一定规模的危大工程范围 (1A436000-B158 = registry supporting)
    ("1A436000_009_0012", "1A436000-B158"): ("full", "本体·support 超过一定规模危大工程范围(深基坑≥5m/模板≥8m或跨≥18m或荷载≥15kN/m²/起重单件≥100kN或总重≥300kN/脚手架落地≥50m/幕墙≥50m/挖孔桩≥16m/大型结构≥1000kN)"),
    # 本体·危大六项管理要求 (方案修改/交底/监测 = J01 管理判分眼)
    ("1A436000_010_0011", "1A436000-B021"): ("full", "本体·危大工程六项管理要求(公示/方案交底/严禁擅自修改方案/人员登记与监督/监测与巡视/第三方监测; 方案修改须重新审核+重新论证)"),
    # 本体·基坑专项方案八大内容(专项方案编制内容判分眼)
    ("1A431000_008_0008", "1A431000-B006"): ("tc_filter", "本体·基坑工程专项施工方案八大核心内容(工程概况/编制依据/施工计划/工艺技术/保证措施/管理及人员配备/验收要求/应急处置措施)+验收要点"),
    # 本体·模板支撑专项方案核心内容(专项方案编制内容判分眼)
    ("1A431000_009_0009", "1A431000-B003"): ("tc_filter", "本体·模板支撑体系专项施工方案核心内容(工程概况/技术参数/工艺流程/施工方法/检查要求/计算书及相关施工图纸)"),
    # 外延·未编/未审专项方案=重大事故隐患(危大法律后果锚; 只取与未编/未审专项方案相关 EP, 各分项隐患清单绕开)
    ("1A436000_007_0010", "1A436000-B031"): ("ep_only_xianyan", "外延·危险性较大分部分项工程未编制/未审核专项施工方案=重大事故隐患(法律后果锚); 该 chunk 8 张 TC 是各分项重大隐患清单(基坑/模板/脚手架/起重/高处/临电/拆除)属安全隐患考点腹地, 不当 J01 采分点, 仅取'未编/未审专项方案'语境 EP 作法律后果外延参照"),
}

# tc_filter 模式下, TC/rule 标题或内容须含这些词才算真 J01 专项方案/论证/范围
TC_J01 = re.compile(r"专项施工方案|专项方案|专家论证|危大|危险性较大|论证|超过一定规模|方案编制|"
                    r"工程概况|编制依据|施工计划|施工工艺|保证措施|应急处置|应急预案|计算书|验收要求|技术参数|工艺流程")
# 纯各分项施工工艺/隐患清单 = 他考点腹地, tc_filter 下额外排除
NOISE_BLOCK = re.compile(r"地基承载力不足|连墙件缺失|防倾覆装置|附着间距|预制构件未防失稳|湿度|积水|拆除施工作业顺序")

# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A436000_007_0010(B031 各分项隐患TC)": "该 chunk 8 张 teaching_cards = 基坑超挖/模板支架/脚手架/起重机械/钢结构高处/临电/拆除各分项【重大事故隐患清单】, 命题语境是安全隐患判定(S01/S02 等安全考点腹地), 非 J01 危大范围/方案/论证判分眼, 绕开 TC 仅取该 chunk '未编/未审专项方案=重大隐患' EP 作法律后果外延锚",
    "1A431000_008_0008(验收TC内基坑支护监测项)": "TC[1] '基坑验收内容(支护结构顶部水平位移/锚杆轴力/坡顶排水/侧壁完整性)' 属 B02 基坑支护/监测考点腹地, tc_filter 下'验收要求'词命中但其内容是基坑监测专项, 与 J01 '专项方案须含验收要求'这一编制内容条目重叠——只保留'专项方案八大内容含验收要求'作编制条目锚, 不收基坑监测数值明细(归 B02)",
    "1A413000_076_0146/1A413000_084_0157 等基坑施工": "深基坑/基坑支护/开挖【施工技术本体】(地下连续墙/灌注桩排桩/降水/验槽) 仅'深基坑'泛词命中, 主题是基坑施工工艺(B02 腹地), 非 J01 危大范围判定, 绕开",
    "1A431000_006_0006/007_0007 施工组织设计": "施工组织总设计/单位工程施工组织设计编制要求 — 施工组织设计考点(与专项施工方案不同层级: 组织设计是面/方案是点), 仅'施工方案'泛词命中, 主题非 J01 危大专项方案, 绕开",
    "1A436000_006_0009(B067/B159/B160 重大隐患判定标准)": "建筑工程生产安全重大事故隐患判定标准/重大事故隐患判定条件 — 重大隐患判定通用考点, 与 J01 '未编/未审专项方案'外延部分重叠但主题是隐患判定全集, 不重复收(法律后果锚已由 B031 chunk EP 覆盖), 绕开",
    "1A411011_021_0039/1A422000_042_0067/1A432002_033_0043": "住宅装修设计要求/装饰装修法规/劳务分包合同 — '安全专项/方案/验收'等泛词边角命中, 主题与 J01 无关, 绕开",
    "1A434020_085_0137/085_0138 验收": "主体结构分部工程验收组织/检验批分项分部验收内容 — A01 验收程序考点腹地, '验收'泛词命中, 非 J01 危大专项方案验收要求条目, 绕开",
    "1A436000-G01 装配式专项方案": "装配式混凝土结构施工专项方案内容 — 装配式施工考点, '专项方案'泛词命中, 主题非危大工程专项方案/论证, 绕开",
}


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


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

        # ep_only_xianyan: 法律后果外延锚, 只取 EP(未编/未审专项方案语境), TC(各分项隐患清单)绕开
        if mode == "ep_only_xianyan":
            for ep in cc.get("exam_patterns", []):
                e = pj(ep)
                if not e:
                    continue
                desc = e.get("description", "") or ""
                sps.append({
                    "statement": "[外延·法律后果] " + desc,
                    "required_terms": e.get("grading_keywords", []),
                    "point_id": f"ca:{ch}",
                    "quote": "B031 chunk: 危险性较大分部分项工程未编制/未审核专项施工方案=重大事故隐患(法律后果外延锚, 非 J01 范围/方案/论证采分点). EP=" + desc + " | grading_keywords=" + ",".join(e.get("grading_keywords", [])),
                    "chunk": ch,
                })
            units.append({
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "scoring_points": sps,
            })
            total_sp += len(sps)
            continue

        # teaching_cards -> kc:<chunk>:<idx>
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "tc_filter" and (not TC_J01.search(blob) or NOISE_BLOCK.search(blob)):
                continue
            content = t.get("content", "") or ""
            sps.append({
                "statement": (t.get("title", "") + "：" + content).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": content,
                "chunk": ch,
            })
            captured.add(content.strip())
            idx += 1

        # rules -> kc:<chunk>:<idx>
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
            if mode == "tc_filter" and (not TC_J01.search(rt) or NOISE_BLOCK.search(rt)):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
            })
            captured.add(rt.strip())
            idx += 1

        # exam_patterns -> ca:<chunk>
        for ep in cc.get("exam_patterns", []):
            e = pj(ep)
            if not e:
                continue
            desc = e.get("description", "") or ""
            if mode == "tc_filter" and (not TC_J01.search(desc) or NOISE_BLOCK.search(desc)):
                continue
            sps.append({
                "statement": desc,
                "required_terms": e.get("grading_keywords", []),
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(e.get("grading_keywords", [])),
                "chunk": ch,
            })

        # concepts (full 模式取真 J01 概念句)
        if mode == "full":
            for co in cc.get("concepts", []):
                c = pj(co)
                term = (c.get("term", "") if isinstance(c, dict) else str(co)) or ""
                if not TC_J01.search(term):
                    continue
                sps.append({
                    "statement": term.replace("\n", " ").strip("# ").strip(),
                    "required_terms": [],
                    "point_id": f"cc:{ch}:{idx}",
                    "quote": term.replace("\n", " ").strip(),
                    "chunk": ch,
                })
                idx += 1

        if sps:
            units.append({
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "J01 危大工程范围 + 专项方案 + 专家论证",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "编译库覆盖说明": "危大范围/超规模阈值/专家论证程序/六项管理/专项方案编制内容教材锚集中在 7 个核真 chunk(primary 1A437000_010_0013 专家论证, support 1A436000_008_0011/009_0012 范围+超规模); 范围/规模阈值数字判读锚在 EP grading_keywords + 真题侧, 教材锚以本源料为准, 数值判读锚以 _J01_exam_evidence.json 真题为准(诚实标注)",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"J01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
