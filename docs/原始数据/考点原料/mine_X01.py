#!/usr/bin/env python3
"""X01 施工平面布置原则 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 X01 真采分点, 产 _X01_compiled_source.json (照 F03/S06/D13 结构).

考点身份 (注册表 slot 34, **direct**):
  primary  1A431040 施工平面布置          (canonical resolve✅, name 与 X01 施工平面布置原则 相符)
  support  1A431041 施工平面布置图设计      (resolve✅, name 相符)
           1A431042 施工平面管理            (resolve✅, name 相符)

  ⚠️ 注册表/编译库现实(直读核真):
     - 3 个 registry code 全部在 canonical taxonomy nodes_by_code resolve✅:
       1A431040=施工平面布置 / 1A431041=施工平面布置图设计 / 1A431042=施工平面管理 (sha 26dbb542...).
     - primary 1A431040 与 supporting 1A431041/1A431042 在编译库 bundle 内**无独立 record**(直读确认0条);
       真正承载 X01 教学卡的 chunk 全部挂在同叶子族 1A431010-C* 下(建筑工程企业资质与施工组织 >
       施工平面布置图设计/布置临时房屋/场地围护与出入口), 作弹药内部引用与 canonical primary/supporting
       并存(同 F03 的 1A413050-R*/G03 的 1A413067/068/069 无record·锚挂 primary 子项族模式).
     - 即便锚挂在子项族 1A431010-C*, 三个 registry code 名实**完全相符**(都=施工平面布置/设计/管理),
       X01 题面"施工平面布置原则"由 primary(布置)+supporting(图设计+管理)三 code 直接覆盖, 无横跨多无关叶子,
       故 **direct** (照 A01/C05/D11 direct 模式, 非 B02/F03 的 composite).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card JSON 字符串编码用 pj() 解析 + leaf_name_path 可能错挂别章
  (F03 踩过, 逐项核真):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析(F03/D13/G03 踩过).
  - **本批 chunk 直读核真 leaf_name_path 真实属"施工平面布置/施工组织"本体**(施工平面布置图设计/布置临时房屋/
    场地围护与出入口), 未见 F03 那种"错挂地基与基础"的污染; 仍逐 chunk 以 compiled_context 真实内容为准.
  - 与 X02(临设/道路/堆场)/X03(文明/绿色) 区分:
     · X01 = 施工平面布置【原则·步骤·要点·图内容】+ 各设施在平面上【布置位置/相互关系】(占地少/减少二次搬运/
       分区/大门/塔吊泵升降机布置考虑因素/堆场加工厂道路布置/围挡五牌一图/平面管理) = X01 本体判分眼.
     · X02 = 临时设施/道路/堆场的【具体技术规格】(仓库距15m/道路宽度4m6m/宿舍床铺净高/临时用水管径计算) —
       与 X01 同字, 但"具体规格数值"是 X02 territory; X01 取其"在平面上怎么布置/为什么这么布置". 同字不同考,
       规格数值卡标🔵邻接(X02采分眼), 布置原则/位置卡取作 X01 本体.
     · X03 = 文明施工/绿色施工/环保措施【管理内容】(防尘洒水/垃圾封闭/绿化/职业健康) = X03 territory, 标🔵绕开.
     · S05 = 施工临时用电【三级配电/TN-S/二级保护/安全电压/送停电顺序/电缆埋深】= S05 territory(临电安全技术),
       非 X01 平面布置本体; X01 只取"临时用电管网在平面上的布置位置", 三级配电/安全电压规格卡标🔵绕开(S05采分眼).
     · 临时用水量/管径【计算公式】(q4/总用水量Q三情况/管径d公式) = 临设计算 territory(偏 X02/计算型),
       非 X01 平面布置原则判分眼, 标🔵绕开.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_X01_compiled_source.json")

KEYWORDS = ("施工平面布置|施工总平面布置|平面布置图|总平面图|布置原则|布置内容|布置步骤|塔吊布置|起重机械布置|"
            "垂直运输|材料堆场|堆场|加工棚|搅拌站|临时设施|临设|运输道路|场内道路|仓库|办公区|生活区|大门|"
            "围墙|最小占地|减少二次搬运|消防通道|临时用水用电布置")

# 经人工核真(直读 compiled_context)的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (X01 平面布置原则/要点/内容/各设施布置 本体判分眼)
#       "ext" =邻接外延(临设具体规格/文明环保/临电安全, 标🔵, 非 X01 平面布置原则主采分)
CHUNK_POLICY = {
    # ── 主轴本体: 施工总平面布置图 内容+原则+要点(大门/塔吊/泵/升降机布置) (primary 1A431040 territory) ──
    "1A431011_011_0012": ("full", "本体·施工总平面布置图内容+设计原则+设计要点(1A431010-C17~C20, 即 primary 1A431040/supporting 1A431041 territory): 图内容=地形/拟建建构筑物位置/加工运输储存设施/临时道路办公生活用房/安全消防环保设施/周边既有建筑环境; 设计原则=占地少·运输合理·减少干扰(二次搬运)·利用既有设施·分区设置·环保安全·遵守规定; 要点=现场宜≥2个大门(考虑路网/转弯半径/坡度/车辆运输)·塔吊布置(基础/环境/覆盖范围/吊重/运输堆放/附墙/拆除/群塔防撞)·混凝土泵布置(泵管输送距离/罐车停靠/立管固定)·施工升降机布置(地基承载力/平整度/排水/附墙/楼层通道/防护门/围栏). **逐项核真**"),
    # ── 主轴本体: 各临时设施在平面上的布置(堆场/加工厂/道路/临时房屋 布置位置与相互关系=X01本体; 具体规格数值=X02邻接标🔵) ──
    "1A431011_012_0013": ("full", "本体·临时设施平面布置(1A431010-C11~C15/C23/1A431011-B019): 布置仓库堆场·布置加工厂·布置场内临时运输道路·布置临时房屋·布置临时水电管网及动力设施=施工平面布置步骤内容(X01本体); 施工总平面图应按绘图规则/比例/规定代号绘制(B019). **注: 同chunk具体规格(危险品仓库距在建工程≥15m/主干道单行≥4m双行≥6m消防车道≥4m回车场12m×12m转弯半径≥15m/宿舍床铺≤2层净高≥2.5m通道≥0.9m人均≥2.5m²每间≤16人)是临设技术规格=X02 territory, 标🔵邻接(X01取其'在平面上布置'维度, 不取规格数值作X01本体采分眼)**"),
    # ── 主轴本体: 场地围护与出入口(围挡/五牌一图=平面布置图要素与场容管理, X01本体; 环保措施=X03邻接标🔵) ──
    "1A431011_013_0014": ("full", "本体·场地围护与出入口(1A431010-C06/C33): 围挡高度(市区主要路段≥2.5m·一般路段≥1.8m·距路口20m内0.8m以上通透性围挡)·主要出入口设'五牌一图'(工程概况/消防保卫/安全生产/文明施工/管理人员名单及监督电话牌+施工现场总平面图)=场地围护与平面布置图要素(X01本体·真题{2017,案例三}五牌一图补全直命). **注: 同chunk环保措施(排水系统/硬化地面/防尘洒水/封闭垃圾区/绿化/污染防治)=文明绿色施工=X03 territory, 标🔵邻接绕开**"),
}

# full/ext 同chunk 剔除噪声卡(临设具体规格数值/文明环保/临电三级配电安全电压/用水计算等非 X01 平面布置原则判分眼)
# 这些是 X02/X03/S05/计算型 territory, X01 只取"在平面上布置/为什么这么布置", 不取规格/计算/安全技术卡
NOISE = re.compile(r"距在建工程不小于|单行道≥4|双行道≥6|消防车道≥4|回车场12|转弯半径≥15|床铺≤2层|净高≥2\.5|"
                   r"人均面积|每间≤16|排水系统|硬化地面|防尘洒水|封闭垃圾区|绿化布置|污染.*防治|"
                   r"三级配电|TN-S|剩余电流|安全电压|安全特低电压|电缆.*埋|开关箱|配电箱|送电顺序|停电顺序|持证上岗|"
                   r"用水量|管径|消防用水|生活用水|公式")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 邻接 territory (留痕)
SKIPPED = {
    "1A431010-C04/C05/C07/C30/C31/C35(临时用电管理)/C03(临时用电安全技术) chunk 014_0015/015_0016": "三级配电/TN-S接零/二级剩余电流保护/安全电压(36V/24V/12V)/电缆埋深≥0.7m/专用开关箱/送停电顺序/电工持证=【施工临时用电安全技术】=S05(临时用电三级配电)territory, 非X01平面布置原则本体; X01只取'临时用电管网在平面上的布置位置'(已含C12布置临时水电管网, 取其布置维度), 用电安全技术规格卡绕开/NOISE剔",
    "1A431010-C01/C02/C16/C28/C29(临时用水量·管径计算) chunk 016_0017": "生活区用水量q4公式/总用水量Q三情况判定/供水管径d公式/消防用水量=【临时用水量计算】=临设计算型 territory(偏X02/计算), 非X01平面布置原则判分眼; X01取'临时给水管网平面布置位置'不取计算公式, 绕开/NOISE剔",
    "1A431010-C33环保措施 / 1A437000-B*(绿色文明施工)": "排水/硬化/防尘洒水/垃圾封闭/绿化/污染防治/文明施工管理内容/职业健康=X03(文明绿色施工)territory, 标🔵邻接绕开(C33场容围护取'围挡/五牌一图'布置维度, 环保管理内容剔)",
    "临设具体技术规格(仓库距15m/道路宽4m6m/宿舍净高2.5m等) X02 territory": "临时设施/道路/堆场的具体技术规格数值=X02(临设道路堆场)territory; X01取其'在施工平面上的布置位置/相互关系/布置理由'(分区/靠近使用地点/减少二次搬运)作本体, 具体规格数值标🔵邻接不作X01采分眼, 与X02严格分界",
    "案例题背景噪声(2017案例五/问题1-5·2021案例二网络图/流水施工·2024案例一碳排放·2025案例二进度/声学等)": "extract_exam_evidence关键词命中36条(案例31)多为多问案例的背景资料含'临时设施/堆场/垂直运输/塔吊'泛词命中(实考专项论证/流水施工/网络计划/碳排放/混凝土浇筑等别考点小问), 非X01平面布置原则判分问; 仅2018案例(一)平面布置示意图各区识别+布置理由·2021案例二/第1题施工总平面布置图设计要点+布置仓库堆场加工厂道路+升降机布置·2020第27题垂直运输设备MCQ(ans=ABDE)·2017案例三五牌一图补全·2025参考答案(二)施工升降机布置考虑因素 作🟢真题锚(直命X01本体)",
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
        leaves = sorted(set(x.get("leaf_id") for x in recs if x["source_ref"].get("chunk_id", "") == ch))
        lf = leaves[0] if leaves else r.get("leaf_id", "")
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
            prefix = "[🔵临设规格/文明/临电外延] " if mode == "ext" else ""
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
            if NOISE.search(rt):
                continue
            sps.append({
                "statement": ("[🔵临设规格/文明/临电外延] " if mode == "ext" else "") + rt,
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
                "leaf_id": lf,
                "leaf_name_path": r.get("leaf_name_path"),
                "source_ref": r.get("source_ref"),
                "note": note,
                "tier": mode,
                "scoring_points": sps,
            })
            total_sp += len(sps)

    out = {
        "考点": "X01 施工平面布置原则",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 34, primary 1A431040 施工平面布置 resolve✅ name相符; supporting 1A431041 施工平面布置图设计/1A431042 施工平面管理 resolve✅ name相符; 三 code 在编译库无独立record, 锚挂同叶子族 1A431010-C* 子项, 名实完全相符·X01题面由 primary布置+supporting图设计+管理三 code 直接覆盖无横跨无关叶子, 故 direct 非 composite)",
        "编译库覆盖说明": "X01 本体判分眼(施工总平面布置图内容六项·设计原则七条[占地少/运输合理/减少干扰即减少二次搬运/利用既有设施/分区设置/环保安全/遵守规定]·设计要点[≥2个大门考虑路网转弯半径坡度/塔吊布置考虑基础环境覆盖吊重附墙群塔防撞/混凝土泵布置/施工升降机布置考虑地基承载力附墙楼层通道防护门]·临时设施平面布置步骤[布置仓库堆场→加工厂→场内运输道路→临时房屋→临时水电管网]·施工总平面图按绘图规则比例代号绘制·场地围护[围挡高度市区≥2.5m一般≥1.8m通透性围挡]·五牌一图)集中在 1A431010-C* 叶子族 chunk 1A431011_011_0012/012_0013/013_0014, 名实相符. 真题侧关键补料(genuine X01 anchors, 直接考平面布置原则): 2018案例(一)[施工平面布置示意图各区识别(钢筋/木工加工堆场/搅拌站/办公/塔吊/电梯/提升机/泵/大门围墙/冲洗池)+布置理由(靠近材料运输/办公远离作业区/塔吊居中覆盖广)]·2021案例二/第1题[施工总平面布置图设计要点(临时道路/水电/消防/安全防护/环保布置)+布置仓库堆场加工厂场内道路+施工升降机布置考虑因素]·2020第27题[垂直运输设备MCQ ans=ABDE 塔机/施工电梯/物料提升架/混凝土泵·吊篮非垂直运输]·2017案例三[五牌一图补全]·2025参考答案(二)[施工升降机布置考虑地基承载力/附墙位置/楼层平台通道/出入口防护门]. 邻接绕开: 临设具体技术规格(仓库距15m/道路宽4m6m/宿舍净高2.5m等=X02 territory标🔵)·临时用电三级配电安全技术(S05 territory NOISE剔)·临时用水量管径计算(临设计算型 NOISE剔)·环保文明施工管理内容(X03 territory标🔵). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"X01 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/邻接 territory: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
