#!/usr/bin/env python3
"""E01 工程量清单计价 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 E01 真采分点, 产 _E01_compiled_source.json (照 E05/S06/B02 结构).

考点身份 (注册表 slot 41, **direct**):
  primary   1A432000-B037 工程量清单计价方式   (canonical resolve✅ 名实相符)
  support   1A432000-B053 清单计价              (canonical resolve✅ 名实相符)

  ⚠️ 注册表/编译库现实(直读核真, taxonomy sha 26dbb542...):
     - primary 1A432000-B037 + supporting 1A432000-B053 在 canonical taxonomy
       resolve✅ 且名实相符: B037=工程量清单计价方式 / B053=清单计价. 两叶同挂 chunk 1A432002_035_0046.
     - **direct (非 composite)**: E01 题面"工程量清单计价"判分眼全部落在「清单组成(五大清单)/综合单价构成/
       单价计价 vs 总价计价/清单计价造价计算(分部分项费+措施费+其他项目费+规费税金)/计价风险责任划分」,
       归 1A432000 工程招标投标与合同管理「工程量清单计价」叶族 + 1A435000 造价计算 chunk(C02/C05/C22, 挂同章 1A432000-C 叶).
       不横跨多章本体, 故 direct (照 E05/S06 direct 模式).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 编码用 pj() 解析 (X02/R01/E05 踩过, 逐项核真):
  - teaching_cards/rules/exam_patterns 是 JSON 字符串, pj() 统一解析.
  - **与 C02(进度款计量计价)/K01(索赔)/E02(预付款) 区分(逐 chunk 核真)**:
    · 进度款支付/计量(1A432000-C17/C19/C24)=【C02 进度款】territory, 是"履约阶段按月计量付款",
      非"招投标阶段清单编制+清单计价造价构成"; 标🔵邻接绕开(同属合同计价但判分眼不同).
    · 索赔(工期/费用索赔 1A432000-B004/B015/B016)=【K01 索赔】territory, NOISE剔/邻接绕开.
    · 预付款(1A432000-C 预付款叶)=【E02 预付款】territory, 邻接绕开.
    · 工程造价八部分构成/六阶段(1A432002_037_0049 B032/B038)=【造价构成学】territory,
      是上位"造价由哪几部分组成"非"清单计价怎么计价/算造价", 同章邻接但判分眼不同; 标🔵邻接绕开.
    · 招投标程序(开标/中标/投标流程 B007/B008/B039/B045)=【招投标程序】territory, 同章非清单计价; 标🔵邻接绕开.
    · 分包/总承包合同义务(B010/B011/B040/B042)=【合同管理】territory; NOISE剔.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_E01_compiled_source.json")

KEYWORDS = ("工程量清单|清单计价|工程量清单计价|分部分项工程量清单|措施项目清单|其他项目清单|规费|税金|综合单价|"
            "清单项目|项目编码|项目特征|计量单位|工程数量|清单计价规范|招标控制价|投标报价|清单组成|五大清单|工程量计算规则")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
CHUNK_POLICY = {
    # ── 主轴本体①: 清单计价方式核心要点 (primary B037 工程量清单计价方式 / support B053 清单计价 territory) ──
    "1A432002_035_0046": ("full", "本体·清单计价方式核心要点(primary 1A432000-B037 工程量清单计价方式 + support B053 清单计价): "
        "分部分项工程宜采用单价计价, 措施项目宜采用总价计价; 综合单价为不含增值税的税前全费用价格, "
        "包含人工/材料/机具/管理/利润及风险费. =E01判分核心眼(单价vs总价计价分流 + 综合单价构成). 逐项核真"),
    # ── 主轴本体②: 清单编制依据 + 应用规定 (B033/B034/B035 应用管理/规定/编制依据 territory) ──
    "1A432002_037_0048": ("full", "本体·工程量清单编制依据 + 应用规定(1A432000-B033/B034/B035): "
        "编制依据=计价标准/工程量计算规则/招标文件/合同条款/招标图纸/技术规范/现场情况/地勘资料等; "
        "清单由招标人或造价咨询人编制作为招标文件组成部分; 总价合同清单缺陷由承包人负责, 单价合同由发包人负责; "
        "暂定工程量履约中重新计量, 措施项目按总价计价. =E01本体(编制责任+缺陷责任分流). 逐项核真"),
    # ── 主轴本体③: 计价风险责任划分 + 合同类型适用 + 报价澄清 (B022/B043/B062 计价风险 territory) ──
    "1A432002_036_0047": ("full", "本体·计价风险责任划分+合同类型适用+投标报价澄清(1A432000-B022/B043/B062 计价风险): "
        "发包人承担清单缺陷/数据错误/变更/赶工; 承包人承担措施清单准确性/总价合同缺陷/自身方案变更/施工效率; "
        "单价合同适用工程量不确定, 总价合同适用工程量明确, 成本加酬金适用紧急抢险/复杂工程; "
        "投标报价澄清在开标后定标前, 算术误差可修正但总价不调整. =E01本体(风险责任分流·高频判分眼). 逐项核真"),
    # ── 主轴本体④: 建安工程费构成 + 分部分项费/措施费计算公式 (C22 建筑工程费构成与计算·综合单价公式 territory) ──
    "1A435000_038_0050": ("full", "本体·建安工程费构成+分部分项费/措施费计算公式(1A432000-C22 建筑工程费构成与计算): "
        "建安费按费用构成要素=人工费/材料费/施工机具使用费/企业管理费/利润和税金; "
        "分部分项工程费=Σ(分部分项工程量×综合单价); 措施项目费按单价计量=Σ(工程量×综合单价)或按总价计量=Σ(计算基数×费率). "
        "=E01本体(综合单价应用公式·计算骨架). 逐项核真"),
    # ── 主轴本体⑤: 清单造价计算母题例题 (C02 案例7.2-1·分部分项费+措施费+其他项目费+增值税+总造价 territory) ──
    "1A435000_039_0053": ("full", "本体·清单计价造价计算母题(1A432000-C02 案例7.2-1): "
        "管理费=人材机×费率; 利润=(人材机+管理费)×费率; 分部分项费=人材机+管理费+利润; "
        "措施费=基数×费率; 其他项目费给定; 增值税=(分部分项费+措施费+其他项目费)×税率; "
        "总造价=分部分项费+措施费+其他项目费+增值税. EP例: 300×8%管理费/×10%利润/×5%措施/3.5其他/×9%税=408.64万元总造价. "
        "=E01母题情境锚(清单计价逐项汇总造价). 逐项核真"),
    # ── 主轴本体⑥: 合同价款确定原则 + 投标总价一致性 + 五大组成 (C05 计算建安工程造价·清单五大组成 territory) ──
    "1A435000_040_0054": ("full", "本体·合同价款确定原则+投标总价一致性(1A432000-C05 分析与答案: 计算建安工程造价): "
        "投标报价不得低于成本价且不得高于最高投标限价; 投标总价应与「分部分项工程+措施项目+其他项目+增值税」合计一致, "
        "不一致时在保持总价不变前提下调整已标价工程量清单; 可调整合同价款事项=清单缺陷/暂列金额/暂估价/总承包服务费/计日工/物价变化/法规变化/工程变更/索赔. "
        "=E01本体(清单五大组成汇总·总价一致性判分眼). 逐项核真"),
}

# 同chunk 剔除噪声卡(造价构成八部分/六阶段·招投标程序·分包合同义务·索赔 等非清单计价判分眼)
NOISE = re.compile(r"八个部分|8个部分|六阶段|投资估算|概算造价|决算价|"
                   r"开标|中标候选人|投标文件接收|投标流程|招标程序|"
                   r"转包|分包商合同义务|总承包商合同义务|劳务分包|"
                   r"不可抗力|工期索赔|费用索赔")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 邻接 territory (留痕)
SKIPPED = {
    "1A432000-C17/C19/C24(工程进度款支付/计量)":
        "进度款支付与计量=【C02 进度款/计量计价】territory, 履约阶段按月计量付款, 非招投标阶段清单编制+清单计价造价构成; 标🔵邻接绕开(同属合同计价判分眼不同)",
    "1A432000-B004/B015/B016(工期索赔/费用索赔)":
        "索赔=【K01 索赔成立与计算】territory, 与清单计价无关; NOISE剔/邻接绕开",
    "1A432002_037_0049(工程造价八部分构成/六阶段 B032/B038)":
        "建设工程造价八部分构成(建筑工程费/设备购置费…)+六阶段(投资估算/概算/预算…)=【造价构成学】territory, 是上位'造价由哪几部分组成'非'清单计价怎么算造价', 同章邻接判分眼不同; 标🔵邻接绕开",
    "1A432001_023/024/025(开标/中标/投标流程 B007/B008/B039/B045)":
        "招投标程序(开标/中标公示/投标流程)=【招投标程序】territory, 同章非清单计价本体; 标🔵邻接绕开",
    "1A432002_028/032/033(总承包/分包合同义务 B010/B011/B040/B042)":
        "总承包/分包合同义务=【合同管理】territory, 与清单计价无关; NOISE剔",
}


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    seen = {}
    for r in recs:
        ch = r["source_ref"].get("chunk_id", "")
        if ch in CHUNK_POLICY and ch not in seen:
            seen[ch] = r

    units = []
    total_sp = 0
    for ch, (mode, note) in CHUNK_POLICY.items():
        r = seen.get(ch)
        if not r:
            print(f"⚠ chunk {ch} 未在bundle找到, 跳过")
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
            if NOISE.search(blob):
                continue
            sps.append({
                "statement": (title + "：" + content).strip("："),
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
            if NOISE.search(rt):
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
            if NOISE.search(desc):
                continue
            sps.append({
                "statement": desc or ("命题点(grading_keywords): " + ",".join(gk)),
                "required_terms": gk,
                "point_id": f"ca:{ch}",
                "quote": (desc + " | grading_keywords=" + ",".join(gk)).strip(" |"),
                "chunk": ch,
                "tier": mode,
            })
        if sps:
            units.append({
                "leaf_id": r.get("leaf_id", ""),
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "E01 工程量清单计价",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 41, primary 1A432000-B037 工程量清单计价方式 resolve✅·名实相符; "
            "supporting 1A432000-B053 清单计价 resolve✅·名实相符. "
            "E01题面'工程量清单计价'判分眼全部落在清单组成(五大清单)/综合单价构成/单价计价vs总价计价/清单计价造价计算/计价风险责任划分, "
            "归 1A432000 招投标与合同管理「工程量清单计价」叶族(B037/B053/B033/B034/B035/B036/B022)+ 同章造价计算 C 叶(C02/C05/C22), "
            "不横跨多章本体, 故 direct 非 composite; 教学卡锚挂 chunk 1A432002_035_0046/037_0048/036_0047 + 1A435000_038_0050/039_0053/040_0054)",
        "编译库覆盖说明": "E01 本体判分眼(清单计价方式: 分部分项宜单价计价/措施项目宜总价计价; 综合单价=不含增值税税前全费用价[人工+材料+机具+管理+利润+风险]; "
            "清单编制依据+缺陷责任[总价合同承包人/单价合同发包人]; 计价风险责任划分[发包人:清单缺陷/数据错误/变更/赶工·承包人:措施清单准确性/效率]; "
            "清单造价计算[分部分项费=Σ(量×综合单价)/措施费/其他项目费/增值税/总造价]; 投标总价五大组成一致性[分部分项+措施+其他+增值税]) "
            "集中在 chunk 035_0046(计价方式核心·B037/B053)/037_0048(编制依据应用规定·B033/B034/B035)/036_0047(计价风险·B022/B062)/"
            "038_0050(建安费构成+综合单价公式·C22)/039_0053(造价计算母题案例7.2-1·C02)/040_0054(合同价款+总价一致性·C05), 名实相符. "
            "⚠️ 真题侧: 真题命中由 _E01_exam_evidence.json 确定性核验(extract_exam_evidence.py), 0命中则诚实标空·全🟢锚来自教材源(kc:/ca: point_id). "
            "邻接绕开: 进度款支付计量(C17/C19/C24·C02 territory)·索赔(B004/B015/B016·K01 territory)·造价八部分构成六阶段(B032/B038·造价构成学)·"
            "招投标程序(开标中标投标流程)·分包总承包合同义务. 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"E01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
