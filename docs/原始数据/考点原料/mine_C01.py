#!/usr/bin/env python3
"""C01 施工缝留置与处理 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 C01 真采分点, 产 _C01_compiled_source.json (照 S05/N01 结构).

考点身份 (注册表 slot 13, direct):
  primary  1A413040-R20 施工缝和后浇带  (= chunk 1A413030_103_0196, R20/R29 同 chunk 双挂)
  support  1A413040-R29 混凝土施工缝和后浇带 (同 chunk) / 1A434000-B037 混凝土施工缝及接槎部位质量通病防治

⚠️ 源库标签污染 + 跨考点防御 (C07/S05/N01 都踩过):
  - leaf/chunk 名义 vs compiled_context 实际常错挂; 必须核 compiled_context 真实内容确属
    "施工缝留置位置 / 接槎二次浇筑界面处理 / 后浇带留置与处理"(主体结构施工本体), 名实不符绕开并留痕.
  - 与 Q01(养护裂缝)/Q03(质量通病蜂窝麻面)/C04(模板拆除) 区分: 后浇带养护14d 与 Q01 养护重叠,
    只取"后浇带"专项养护句作 C01 后浇带锚, 不收通用养护表; 通病蜂窝麻面归 Q03.
  - 与【地下防水/屋面防水】区分: "地下防水施工缝设防措施/止水带/遇水膨胀止水条/防水构造接槎100mm"
    属防水考点 (1A413050-R23/R38 等防水 leaf) 腹地, 命题语境是防水设防而非主体结构施工缝留置/接槎处理,
    绕开归防水考点 (本 pack 只保留其中真讲"主体结构施工缝留设位置/接槎二次浇筑界面"的卡).

  施工缝数值判读锚(凿毛/1.2N·mm²/30mm砂浆/受剪力较小/14d/28d)在编译库 EP grading_keywords + 真题侧均有,
  教材锚以 compiled_source 为准, 数值判读锚以 _C01_exam_evidence.json 真题为准.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_C01_compiled_source.json")

KEYWORDS = ("施工缝|后浇带|接槎|接茬|留置位置|留设|水平施工缝|竖向施工缝|垂直施工缝|凿毛|界面处理|"
            "二次浇筑|继续浇筑|抗剪|柱施工缝|梁板施工缝|沉降后浇带|温度后浇带")

# 经人工核真的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# 同一 chunk 可能被多个 leaf_id 挂(R20/R29 都挂 1A413030_103_0196), 用 (chunk, leaf) 唯一定位.
# mode: "full"=取该 chunk 全部 TC/rule/EP ; "tc_filter"=只取 title/content 含 C01 判读关键词的 TC/rule
CHUNK_POLICY = {
    ("1A413030_103_0196", "1A413040-R20"): ("full",      "本体·primary 施工缝留设位置(水平柱墙0~100/0~300mm、竖向次梁跨度1/3、楼梯端部1/3、墙洞口连梁跨中1/3或墙交界)+后浇带要点(微膨胀混凝土/强度提高一级/养护≥14d/接缝按施工缝处理)+浇筑连续性(初凝前留缝)"),
    ("1A434000_075_0117", "1A434000-B037"): ("b037_xianyan", "support·B037(注册表 supporting leaf): leaf 名义=混凝土施工缝及接槎部位质量通病防治, 但 compiled_context 实际两卡=防水混凝土裂缝渗漏防治+管道穿墙渗漏(名实不符·内容已漂移到防水渗漏). 诚实处置: 不把防水渗漏卡当 C01 施工缝采分点(标🔵外延), 仅保留 B037 leaf 作注册表 supporting 锚 + 其 EP(渗漏成因)作邻接外延参照. 真施工缝接槎采分点不在此 chunk"),
    ("1A413030_094_0176", "1A413033-R14"): ("tc_filter", "本体外延·后浇带界面处理:后浇带用快易收口网, 浇筑前拆除并凿毛(C01后浇带处理本体), 卡里基础模板/杯形/锥形等绕开(基础模板腹地)"),
    ("1A413030_098_0184", "1A413040-R23"): ("tc_filter", "本体外延·后浇带模板:后浇带模板应独立设置 — 只取后浇带模板卡(真题2018案例三反向考'不应独立支设'), 其余模板安装卡绕开"),
    ("1A434000_074_0116", "1A415043-E01"): ("tc_filter", "support外延·地下防水施工缝渗漏成因(施工缝未清理干净→粘结不良→渗漏; 未按规范处理施工缝→接槎明显; 钢筋密集→浇捣困难→不密实) — 只取该接槎渗漏成因卡, 焊缝/填充墙/沉降裂缝卡绕开(他考点)"),
}

# tc_filter 模式下, TC/rule 标题或内容须含这些词才算真"施工缝/接槎处理"
TC_C01 = re.compile(r"施工缝|后浇带|接槎|接茬|凿毛|界面|留设|留置|二次浇筑|继续浇筑|收口网")
# 纯防水设防/止水带/屋面/雨期 = 他考点, tc_filter 下额外排除
NOISE_BLOCK = re.compile(r"止水带|止水条|止水钢板|防水卷材|防水涂料|屋面|找坡|找平|隔离层|雨期|焊缝|填充墙|沉降缝.*窗台|室内环境")

# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A413030_131_0250(1A413050-R23)": "屋面与防水>施工缝设置及防水构造: 水平施工缝高出底板≥300mm/遇水膨胀止水条7d净膨胀率/大体积防水龄期 — 命题语境是【地下/防水工程】施工缝防水构造, 属防水考点腹地, 非C01主体结构施工缝留置/接槎处理, 绕开",
    "1A413030_130_0248(1A413050-R38)": "表3.5-4 明挖法地下工程结构接缝防水设防措施(施工缝≥2种/后浇带≥1种设防: 界面剂/止水条/注浆管/止水带) — 防水设防考点, 非C01施工缝留置/界面处理本体, 绕开",
    "1A422000_029_0049": "相关法规>中埋式止水带施工规定/防水涂料接槎100mm — 防水法规, 非C01本体, 绕开",
    "1A413030_133_0254": "涂膜防水施工>接槎宽度≥100mm — 防水涂料接槎(屋面防水), 非主体结构混凝土施工缝接槎, 绕开",
    "1A413030_124_0236": "屋面保护层>水泥砂浆保护层不得留施工缝 — 屋面防水保护层, 非C01本体, 绕开",
    "1A413030_104_0197(养护表)": "混凝土养护表(硅酸盐≥7d/抗渗C60≥14d/后浇带≥14d) — 养护通识归Q01, 其'后浇带≥14d'已被primary R20 chunk的后浇带卡覆盖, 不重复收",
    "1A413030_092_0171": "桩基成桩>边振边拔→继续浇筑→成桩 — '继续浇筑'是灌注桩工序泛词命中, 非施工缝继续浇筑, 绕开",
    "1A413030_096_0181/095_0178/106_0204/105_0201/123_0232": "大体积混凝土/条基/砌体/后张法/找坡 等仅泛词(后浇带/施工缝)边角命中, 主题非C01施工缝留置处理, 绕开",
    "1A411011_034_0061/1A412010_055_0109/1A413000_075_0144/1A422000_025_0040/1A434000_067_0100/1A438000_156_0304": "钢结构构造/木材强度/内摩擦角/环境污染限量/填充墙主控/雨期(清理后浇带积水) 仅泛词命中, 主题非C01, 全部绕开",
    "2023/2024真题质量通病/检测管理/孔洞修补": "真题侧2023第1题(检测管理+通病图识别+孔洞修补流程)/2024(三检+叠合板+填充墙裂缝)含施工缝/界面剂泛词, 但命题考点是质量检测/通病/防水构造, 非C01施工缝留置, 不作C01真题🟢锚(仅孔洞修补'界面剂'与C01接槎界面处理理念相通, 作🔵讲解参照不作判分锚)",
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
    # (chunk, leaf) -> record
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
        captured_quotes = set()
        # b037_xianyan: 名实不符 supporting leaf, 只保留 EP 作邻接外延参照(标记在 quote), 不收防水渗漏卡当采分点
        if mode == "b037_xianyan":
            for ep in cc.get("exam_patterns", []):
                e = pj(ep)
                if not e:
                    continue
                sps.append({
                    "statement": "[外延·名实不符] " + (e.get("description", "") or ""),
                    "required_terms": e.get("grading_keywords", []),
                    "point_id": f"ca:{ch}",
                    "quote": "B037 leaf 名义=施工缝及接槎质量通病防治, 实际内容已漂移到防水渗漏; 此 EP 作邻接外延参照, 非 C01 施工缝采分点. EP=" + (e.get("description", "") or ""),
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
        for tc in cc.get("teaching_cards", []):
            t = pj(tc)
            if not t:
                continue
            blob = (t.get("title", "") or "") + (t.get("content", "") or "")
            if mode == "tc_filter" and (not TC_C01.search(blob) or NOISE_BLOCK.search(blob)):
                continue
            content = t.get("content", "") or ""
            sps.append({
                "statement": (t.get("title", "") + "：" + content).strip("："),
                "required_terms": t.get("source_refs", []),
                "point_id": f"kc:{ch}:{idx}",
                "quote": content,
                "chunk": ch,
            })
            captured_quotes.add(content.strip())
            idx += 1
        for rule in cc.get("rules", []):
            ro = pj(rule)
            if isinstance(ro, dict):
                rt = ro.get("description", "") or ro.get("statement", "")
            elif isinstance(rule, str):
                rt = rule
            else:
                rt = ""
            if not rt or rt.strip() in captured_quotes:
                continue
            if mode == "tc_filter" and (not TC_C01.search(rt) or NOISE_BLOCK.search(rt)):
                continue
            sps.append({
                "statement": rt,
                "required_terms": [],
                "point_id": f"kc:{ch}:{idx}",
                "quote": rt,
                "chunk": ch,
            })
            idx += 1
        # exam_patterns -> ca:<chunk> (full 取; tc_filter 仅取真 C01 EP)
        for ep in cc.get("exam_patterns", []):
            e = pj(ep)
            if not e:
                continue
            desc = e.get("description", "") or ""
            if mode == "tc_filter" and (not TC_C01.search(desc) or NOISE_BLOCK.search(desc)):
                continue
            sps.append({
                "statement": desc,
                "required_terms": e.get("grading_keywords", []),
                "point_id": f"ca:{ch}",
                "quote": desc + " | grading_keywords=" + ",".join(e.get("grading_keywords", [])),
                "chunk": ch,
            })
        # concepts (full 模式取真 C01 概念句)
        if mode == "full":
            for co in cc.get("concepts", []):
                c = pj(co)
                term = (c.get("term", "") if isinstance(c, dict) else str(co)) or ""
                if not TC_C01.search(term):
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
        "考点": "C01 施工缝留置与处理",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "编译库覆盖说明": "施工缝留设位置/后浇带要点教材锚集中在 primary chunk 1A413030_103_0196(R20/R29);数值判读锚(凿毛/1.2N·mm²/30mm砂浆/受剪力较小/14d养护/28d封闭)在 EP grading_keywords + 真题侧;教材锚以本源料为准, 数值判读锚以 _C01_exam_evidence.json 真题为准(诚实标注)",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"C01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
