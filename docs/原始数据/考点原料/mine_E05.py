#!/usr/bin/env python3
"""E05 挣值法/偏差分析 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 E05 真采分点, 产 _E05_compiled_source.json (照 R01/X01/S06 结构).

考点身份 (注册表 slot 39, **direct**):
  primary   1A435020-B010 应用挣值法控制成本   (canonical resolve✅ 名实相符)
            1A435020-B011 挣值法的计算         (canonical resolve✅ 名实相符)
  support   1A435020-B017 赢得值法(挣值法)核心概念 (canonical resolve✅ 名实相符)

  ⚠️ 注册表/编译库现实(直读核真, taxonomy sha 26dbb542...):
     - primary 1A435020-B010/B011 + supporting 1A435020-B017 在 canonical taxonomy
       outline_structure 全部 resolve✅ 且名实相符:
       B010=应用挣值法控制成本 / B011=挣值法的计算 / B017=赢得值法(挣值法)核心概念.
     - rich_leaf_context bundle 内承载 E05 教学卡(三个基本参数公式 + 四个评价指标 + 偏差方向判读)
       的 chunk 是 1A435020 叶族扁平 record:
       · 1A435020_095_0156 (leaf B009/B010/B011): 挣值法三大核心成本值(BCWP/BCWS/ACWP公式) +
         成本与进度偏差判断规则(CV/SV正负→节支超支/提前延误) + 绩效指数(CPI/SPI). =E05本体腹地·主锚.
       · 1A435020_097_0160 (leaf B016/B017): 赢得值法三大核心值 + 偏差计算四公式. =B017核心概念本体.
       · 1A435020_096_0157 (leaf B018): SPI 计算公式与判别(SPI>1提前/<1滞后). =E05本体.
       · 1A435020_096_0158 (leaf B015): 赢得值法三要素(BCWP/BCWS/ACWP定义). =E05本体.
     - **direct (非 composite)**: E05 题面"挣值法/偏差分析"完全落在 1A435020 施工成本分析与控制
       同一叶族内(三个基本参数 BCWP/BCWS/ACWP + 四个评价指标 CV/SV/CPI/SPI + 偏差方向判读),
       不横跨多章, 故 direct (照 S06/B02 direct 模式).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 编码用 pj() 解析 (X02/R01 踩过, 逐项核真):
  - teaching_cards/rules/exam_patterns 是 JSON 字符串, pj() 统一解析.
  - **与成本/进度其他考点 territory 区分(逐 chunk 核真)**:
    · 成本分析方法(因素分析法/差额计算法/比率法/比较法 = 1A435000_091/092)=【成本分析方法学】
      非挣值法本体, 标🔵邻接绕开(挣值法≠因素分析法, 都是成本分析但判分眼不同).
    · 成本考核指标(劳动生产率/材料成本降低率/成本降低率 = 1A435020_098_0161 B013)+
      项目成本考核内容六项(1A435020_098_0162 B012/B021/B022)=【成本考核】territory,
      与挣值法同叶族但是"考核绩效"非"挣值偏差分析", 标🔵邻接绕开.
    · 进度计划监测/调整(1A433000 施工进度管理)=【进度管理】territory, 虽含"进度偏差"字样
      但是横道图/前锋线/S曲线比较法, 非挣值法 SV 进度偏差, 标🔵邻接绕开(名实不符·同字不同考).
    · 价值工程(1A435000-G02)=【价值工程】非挣值法, NOISE剔.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_E05_compiled_source.json")

KEYWORDS = ("挣值|挣值法|赢得值|已完工作预算费用|BCWP|计划工作预算费用|BCWS|已完工作实际费用|ACWP|"
            "费用偏差|进度偏差|费用绩效指数|进度绩效指数|CV|SV|CPI|SPI|偏差分析|成本偏差|进度偏差分析|"
            "三个基本参数|四个评价指标|超支|节支|拖延|提前")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
CHUNK_POLICY = {
    # ── 主轴本体①: 挣值法三大核心成本值 + 偏差判断规则 + 绩效指数 (primary B010/B011 territory · 三个基本参数+四个评价指标全集) ──
    "1A435020_095_0156": ("full", "本体·挣值法三个基本参数+四个评价指标(primary 1A435020-B010 应用挣值法控制成本/B011 挣值法的计算 territory): "
        "三个基本参数 BCWP=已完成工程量×预算单价 / BCWS=计划工程量×预算单价 / ACWP=已完成工程量×实际单价; "
        "费用(成本)偏差 CV=BCWP-ACWP(CV>0节支/CV<0超支); 进度偏差 SV=BCWP-BCWS(SV>0提前/SV<0延误); "
        "费用绩效指数 CPI=BCWP/ACWP(CPI>1节支/CPI<1超支); 进度绩效指数 SPI=BCWP/BCWS(SPI>1提前/SPI<1延误). "
        "公式+偏差方向判读=E05判分核心眼(R5采分眼=公式正确+方向判读). 逐项核真"),
    # ── 主轴本体②: 赢得值法核心概念 + 偏差计算四公式 (support B017 核心概念 territory) ──
    "1A435020_097_0160": ("full", "本体·support 1A435020-B017 赢得值法(挣值法)核心概念(名实相符): "
        "三个基本成本值=已完成工作预算成本(BCWP)/计划完成工作预算成本(BCWS)/已完成工作实际成本(ACWP); "
        "四个评价指标 CV=BCWP-ACWP / SV=BCWP-BCWS / CPI=BCWP/ACWP / SPI=BCWP/BCWS. "
        "赢得值法核心概念=E05本体. EP含某工程第20周末BCWP6370/ACWP6240/BCWS5340计算CV/SV/CPI/SPI. 逐项核真"),
    # ── 主轴本体③: SPI 计算公式与判别 (B018·进度绩效指数 territory) ──
    "1A435020_096_0157": ("full", "本体·进度绩效指数 SPI(1A435020-B018): "
        "SPI=BCWP/BCWS; SPI>1进度提前 / SPI<1进度滞后. SPI判别=E05四个评价指标之一(进度方向判读). 逐项核真"),
    # ── 主轴本体④: 赢得值法三要素定义 (B015·三要素 territory) ──
    "1A435020_096_0158": ("full", "本体·赢得值法三要素(1A435020-B015): "
        "赢得值法使用三项成本值=已完成工作预算成本(BCWP)/计划完成工作预算成本(BCWS)/已完成工作实际成本(ACWP). "
        "三个基本参数定义=E05本体. 逐项核真"),
}

# 同chunk 剔除噪声卡(成本考核/成本分析方法/进度监测 等非挣值法偏差分析判分眼)
NOISE = re.compile(r"劳动生产率|材料成本降低率|成本降低率|考核内容|考核要求|考核指标|"
                   r"因素分析法|差额计算法|比率法|比较法|价值工程|"
                   r"横道|前锋线|S形曲线|香蕉")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 邻接 territory (留痕)
SKIPPED = {
    "1A435020_098_0161(劳动生产率/材料成本降低率/成本降低率 B013)":
        "成本考核绩效指标(劳动生产率=承包价/实际工日·材料成本降低率·成本降低率)=【成本考核】territory, 同叶族但非挣值法偏差分析判分眼(挣值法考CV/SV/CPI/SPI, 不考降低率); 标🔵邻接绕开",
    "1A435020_098_0162(项目成本考核主要指标/考核内容六项 B012/B021/B022)":
        "项目成本管理绩效考核内容=【成本考核】territory, 同叶族但属考核制度非挣值偏差计算; 标🔵邻接绕开",
    "1A435000_091_0149/092_0150/092_0151(因素分析法/差额计算法/比率法/比较法)":
        "成本分析方法学(因素分析法连环替代/差额计算/比率法/比较法)=【成本分析方法】territory, 与挣值法并列但判分眼不同(挣值法≠因素分析法); 标🔵邻接绕开",
    "1A433000_061_0091/0092(进度计划监测/调整 B023/B024/B047/B048)":
        "施工进度计划监测(横道比较/前锋线/S曲线)与调整=【进度管理】territory, 虽含'进度偏差'字样但是图示比较法非挣值SV进度偏差(同字不同考·名实不符); 标🔵邻接绕开",
    "1A435000-G02(价值工程原理)":
        "价值工程(功能/成本比)=【价值工程】territory, 与挣值法无关; NOISE剔",
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
        "考点": "E05 挣值法/偏差分析",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 39, primary 1A435020-B010 应用挣值法控制成本 + 1A435020-B011 挣值法的计算 resolve✅·名实相符; "
            "supporting 1A435020-B017 赢得值法(挣值法)核心概念 resolve✅·名实相符. "
            "E05题面'挣值法/偏差分析'完全落在 1A435020 施工成本分析与控制同一叶族(三个基本参数 BCWP/BCWS/ACWP + 四个评价指标 CV/SV/CPI/SPI + 偏差方向判读), "
            "不横跨多章, 故 direct 非 composite; 教学卡锚挂同叶族 1A435020_095_0156/097_0160/096_0157/096_0158 扁平 record)",
        "编译库覆盖说明": "E05 本体判分眼(三个基本参数: BCWP=已完成工程量×预算单价/BCWS=计划工程量×预算单价/ACWP=已完成工程量×实际单价; "
            "四个评价指标: CV=BCWP-ACWP[CV>0节支/CV<0超支]·SV=BCWP-BCWS[SV>0提前/SV<0延误]·CPI=BCWP/ACWP[CPI>1节支/CPI<1超支]·SPI=BCWP/BCWS[SPI>1提前/SPI<1延误]) "
            "集中在 chunk 095_0156(三大成本值+偏差判断+绩效指数·primary B009/B010/B011)/097_0160(核心概念+四公式·support B016/B017)/"
            "096_0157(SPI判别·B018)/096_0158(三要素定义·B015), 名实相符. "
            "⚠️ 真题侧: 2015–2025 建筑实务真题中【无任何真实挣值法/赢得值法计算题】(确定性核验: 'BCWP|挣值|赢得值|已完工作预算' 在 11 年真题 0 命中); "
            "挣值法为建筑实务低频考点(项目管理科目高频), 故 E05 真题锚为空, 🟢 全部来自教材锚(编译源 point_id), 无 🟢 真题锚. 详见 _E05_exam_evidence.json. "
            "邻接绕开: 成本考核指标(劳动生产率/降低率 098_0161 B013·098_0162 考核内容)·成本分析方法(因素分析法/差额计算法/比率法 1A435000_091/092)·"
            "进度计划监测调整(横道/前锋线/S曲线 1A433000_061·同字不同考)·价值工程(1A435000-G02). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"E05 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
