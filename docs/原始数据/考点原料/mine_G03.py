#!/usr/bin/env python3
"""G03 桩基施工与质量问题 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 G03 真采分点, 产 _G03_compiled_source.json (照 G02/S06/D13 结构).

考点身份 (注册表 slot 27, **direct**):
  primary  1A413032 桩基础施工                  (canonical 专属叶子, resolve ✅, name 与 G03 完全相符)
  support  1A413067 钢筋混凝土预制桩            (resolve ✅, name 相符)
           1A413068 钢筋混凝土灌注桩            (resolve ✅, name 相符)
           1A413069 桩基检测技术                (resolve ✅, name 相符)
  ⚠️ 注册表/编译库现实(直读核真):
     - 4 个 registry code 全部在 canonical taxonomy nodes_by_code resolve✅ 且 name 与 G03 完全相符
       (桩基础施工/钢筋混凝土预制桩/钢筋混凝土灌注桩/桩基检测技术), 故 `direct` (非 coarse_review).
     - canonical 主锚 1A413032 在编译库 bundle 内**有完整 record 家族**: 13 个细分 leaf 1A413032-R01~R13
       (人工挖孔护壁/成桩过程/桩基检测/桩基础施工/桩底注浆/沉管灌注/泥浆护壁流程/泥浆护壁要求/灌注桩分类/
       预制桩/锤击沉桩/静力压桩/静压控制要点), 散布 chunk 1A413030_090_0165 ~ 092_0173. 名实完全相符,
       无标签污染(直读核真). 这是覆盖最好的考点之一(对比 G02/D13/S07 编译库覆盖薄).
     - 而 supporting leaf 1A413067/1A413068/1A413069 在编译库 bundle 内**无独立 record**(直读确认0条)——
       真正承载教学卡的 chunk 挂在同叶子族 primary 子项 1A413032-R*, 作弹药内部引用与 canonical supporting
       并存(同 D13 的 1A413134 无record/锚挂 R10/R11/R12 模式, 同 G02 的 1A413039 无record 模式).
     - 桩基检测判分眼(桩身完整性Ⅰ-Ⅳ类/钻芯法孔数/低应变高应变声波透射适用条件/抽检比例) 集中在两处:
       chunk 1A413030_093_0174 (leaf 1A413033-R* 混凝土基础施工·检测细则) +
       chunk 1A434000_065_0096 (leaf 1A434000-B025/B039 打压预制桩/灌注桩基础·抽检比例 1%/3根/20%/10根).
       这正是 1A413069 桩基检测技术 territory 的编译库落点. **逐数值/逐类核真.**
     - "质量问题"轴(题目名含"质量问题"): chunk 1A434000_070_0109 (预制桩身断裂质量通病 B078) +
       chunk 1A434000_071_0110 (干作业成孔孔底虚土 B023 / 泥浆护壁坍孔 B032). **质量通病判分眼.**
     - 桩位偏差/验收检验(法规章 1A422000_027_0045 leaf B105·桩基): 灌注桩验收=桩长/桩径/桩位偏差/岩性/
       混凝土强度试件; 预制桩=桩位偏差/桩身完整性. 桩位偏差是 G03 keyword, 取作🔵验收外延(法规章但桩基本体相关).
     - 灌注桩施工安全(1A436000_111_0183 leaf B124): 专项方案/封孔/漏电保护/安全帽——桩基施工安全侧,
       标🔵安全外延(非桩基施工/质量主采分眼, 但属桩基territory).

⚠️ 源库标签污染 + 名实不符 supporting leaf + teaching_card 可能 JSON 字符串编码需解析 (前 10+ 个新产都踩过):
  - teaching_cards/rules/exam_patterns 可能是 JSON 字符串, pj() 统一解析(D13 踩过).
  - chunk 1A413030_088_0163 (leaf 1A413031-R* 复合地基/夯实地基/换填/CFG/强夯): '桩/灌注/沉管'命中但属
    【常用地基处理方法】采分轴(强夯/换填/CFG复合地基), 非 G03 桩基础施工判分眼, 全部绕开归地基处理本体
    (与 G02/G04 territory, 与 G03 桩基不同采分轴). ⚠️CFG桩成桩工艺虽 2021第1题考过, 但 CFG=复合地基处理桩,
    标🔵邻接(真题侧), 不当 G03 桩基础施工本体.
  - chunk 1A422000_031_0051 (灰土挤密桩/水泥土搅拌桩/CFG/高压喷射注浆地基): 全属【地基处理法规】, 绕开.
  - chunk 1A422000_032_0052 (地基承载力检验·单桩复合地基载荷试验): 复合地基承载力检验, 归地基处理, 绕开.
  - chunk 1A413000_077_0148 (灌注桩排桩支护/地下连续墙/深基坑支护): '灌注桩排桩'命中但属【基坑支护】(B02),
    非 G03 桩基础(承载用桩); 排桩=围护结构非承载桩, 绕开归 B02. (2022第30题/2023第25题地下连续墙同此, 绕开.)
  - chunk 1A413000_086_0159 (桩基工程验槽/天然地基验槽): '桩基验槽'命中但属【验槽】(G04 territory), 绕开.
  - chunk 1A434000_081_0130 (子分部划分/地下防水验收资料): 地基基础通识 + 地下防水, 非桩基判分眼, 绕开.
  - chunk 1A437000_012_0018 / 136_0219 (绿色施工/深化设计/源头减量): 绿色施工泛词命中('桩'背景), 绕开.
  - 与 G01(基坑开挖降水)区分: G01 是开挖/降水/支护配合, G03 是桩基(沉桩/灌注/检测/质量); 严格分界不混.
  - 与 G02(土方回填)区分: G02 是回填压实, 与 G03 桩基无交集.
  - 与 B02(基坑支护)区分: 灌注桩排桩/地下连续墙=围护结构归 B02, 承载桩(预制/灌注/沉管)归 G03, 严格分界.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_G03_compiled_source.json")

KEYWORDS = ("桩基|桩基础|预制桩|混凝土预制桩|钢桩|灌注桩|混凝土灌注桩|泥浆护壁|干作业成孔|沉管灌注|锤击沉桩|"
            "静压沉桩|沉桩|接桩|送桩|钢筋笼|导管|水下混凝土|桩身完整性|低应变|高应变|单桩承载力|静载试验|"
            "断桩|缩颈|桩位偏差|打桩顺序|挤土效应")

# 经人工核真的 chunk 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (本体判分眼) ; "ext"=邻接外延/安全外延(标🔵, 非 G03 桩基施工/质量主采分)
CHUNK_POLICY = {
    # ── 主轴本体: 桩基础施工 (预制桩/沉桩/灌注桩/泥浆护壁/沉管/人工挖孔/桩底注浆) primary 1A413032-R* ──
    "1A413030_090_0165": ("full", "本体·预制桩/锤击沉桩/静力压桩(R04/R10/R11/R12): 预制桩强度70%可起吊·100%可运输打桩; 吊点距桩端0.2L; 接桩头高出地面0.5~1m; 沉桩顺序先深后浅/先大后小/先长后短/先密后疏; 静压前必试压桩≥3根·最大压桩力<机架重+配重0.9倍·不得边压边挖. **逐数值/逐顺序核真**"),
    "1A413030_091_0166": ("full", "本体·静压桩终止沉桩标准(R13): 摩擦桩/端承摩擦桩以标高为主压力为辅; 端承桩以压力为主标高为辅. **逐类核真**"),
    "1A413030_091_0167": ("full", "本体·灌注桩施工方法分类(R09): 泥浆护壁/沉管/长螺旋钻孔压灌/干作业成孔灌注桩"),
    "1A413030_091_0168": ("full", "本体·泥浆护壁灌注桩施工流程(R07): 场地平整→桩位放线→开挖浆池→护筒埋设→钻机就位→成孔→清孔→下钢筋笼→浇筑混凝土→成桩"),
    "1A413030_091_0169": ("full", "本体·泥浆护壁灌注桩关键参数(R08): 清孔后孔底沉渣厚度 端承型≤50mm/摩擦型≤100mm/抗拔抗水平≤200mm; 水下混凝土坍落度180~220mm; 超灌高度≥1m; 充盈系数≥1. **逐数值核真**"),
    "1A413030_092_0170": ("full", "本体·桩底注浆终止条件(R05): 以注浆量为主, 注浆总量达设计要求 或 注浆量≥80%且压力>设计值"),
    "1A413030_092_0171": ("full", "本体·沉管灌注桩成桩流程(R02/R06): 桩机就位→锤击沉管→上料→边振边拔→下钢筋笼→继续浇筑→成桩"),
    "1A413030_092_0172": ("full", "本体·人工挖孔灌注桩护壁(R01): 桩距<2.5m应间隔开挖浇筑·最小间距≥5m; 挖土先中间后周边, 扩底先挖圆柱体再扩底"),
    "1A413030_092_0173": ("full", "本体·桩基检测方法汇总(R03): 静载试验(抗压/抗拔/水平)/钻芯法(测强度桩长沉渣)/低应变法(测缺陷)/高应变法(测承载力)/声波透射法(测缺陷)"),
    # ── 主轴本体: 桩基检测判分眼 (桩身完整性/钻芯/低应变高应变适用) 1A413069 territory ──
    "1A413030_093_0174": ("full", "本体·桩基检测判分眼(混凝土基础施工章 1A413033-R*): 高应变法判单桩竖向抗压承载力/桩身完整性/土阻力·声波透射法测灌注桩缺陷; 低应变/声波透射要求混凝土强度≥设计70%且≥15MPa·钻芯法龄期≥28d; 桩身完整性Ⅰ类完整/Ⅱ类轻微缺陷不影响承载力/Ⅲ类明显缺陷影响承载力/Ⅳ类严重缺陷; 钻芯孔数 桩径<1.2m为1~2孔/1.2~1.6m为2孔/>1.6m为3孔·距桩中心(0.15~0.25)D. **逐数值/逐类核真**"),
    # ── 主轴本体: 检测抽检比例判分眼 (1%/3根/20%/10根) 打压预制桩/灌注桩基础 ──
    "1A434000_065_0096": ("full", "本体·桩基检测抽检比例判分眼(施工质量管理章 B025打压预制桩/B039灌注桩): 甲级或地质复杂用静载试验·检验桩数≥总桩数1%且≥3根·<50根时≥2根; 桩身完整性检验抽检≥总桩数20%且≥10根·每承台下桩抽检≥1根. **逐比例核真**"),
    # ── 主轴本体: 质量问题轴(题目名含"质量问题") 地基与基础质量通病 ──
    "1A434000_070_0109": ("full", "本体·桩基质量通病·预制桩身断裂(施工质量管理章 B078): 断裂常因桩身弯曲/遇障碍物/稳桩不直/接桩偏心/混凝土强度不足; 施工前清障·检查桩身质量·垂直沉桩·接桩对中·避免运输损伤. (注: 同chunk B058边坡塌方属土方非G03, 见EXT_NOISE剔)"),
    "1A434000_071_0110": ("full", "本体·桩基质量通病·孔底虚土/坍孔(施工质量管理章 B023干作业成孔/B032泥浆护壁): 干作业成孔孔底虚土≤100mm·超则二次投钻/勺钻清理/孔底压力灌浆; 泥浆护壁防坍孔=保证护壁效果/维持水头压力/合理钻进参数/及时处理孔口坍塌"),
    # ── 验收外延 (桩位偏差/验收检验内容·法规章桩基本体相关) ──
    "1A422000_027_0045": ("ext", "验收外延·桩基验收检验要点(法规章 B105·桩基): 灌注桩验收=桩长/桩径/桩位偏差/岩性/混凝土强度试件; 预制桩=桩位偏差/桩身完整性; 钢桩=桩位偏差/断面尺寸/桩长/矢高; 人工挖孔桩=终孔持力层检验. 标🔵验收外延(桩位偏差是G03 keyword, 法规章但桩基本体相关)"),
    # ── 安全外延 (灌注桩施工安全·桩基territory) ──
    "1A436000_111_0183": ("ext", "安全外延·灌注桩施工安全控制要点(施工安全管理章 B124): 施工前编专项方案·成孔未浇前封孔或设防护栏·电路架空设漏电保护·作业人员戴安全帽禁酒后作业·浇筑后及时抽浆回填. 标🔵安全外延(桩基施工安全, 非桩基施工/质量主采分眼)"),
}

# ext 模式 + full模式同chunk 剔除噪声卡(地基处理/边坡塌方/防水/CFG复合地基 等非 G03 桩基判分眼)
EXT_NOISE = re.compile(r"强夯|换填|灰土挤密|水泥土搅拌|高压喷射|复合地基|边坡塌方|地下防水|地下连续墙|排桩支护|验槽|绿色施工|CFG复合")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A413030_088_0163(1A413031-R* 复合地基/夯实/换填/CFG/强夯)": "'桩/灌注/沉管'命中但属【常用地基处理方法】采分轴(强夯/换填/CFG复合地基), 非G03桩基础施工判分眼, 绕开归地基处理本体(与G03不同采分轴); CFG成桩工艺虽2021第1题考过但属复合地基处理桩, 标🔵邻接真题侧不当G03本体",
    "1A422000_031_0051(灰土挤密桩/水泥土搅拌桩/CFG/高压喷射注浆地基)": "全属【地基处理法规】(挤密/搅拌/喷射注浆地基处理), 非G03承载桩判分眼, 绕开",
    "1A422000_032_0052(B033 地基承载力检验·单桩复合地基载荷试验)": "复合地基承载力检验(单桩复合地基载荷试验), 归地基处理, 非G03桩基检测判分眼, 绕开",
    "1A413000_077_0148(灌注桩排桩支护/地下连续墙/深基坑支护)": "'灌注桩排桩'命中但属【基坑支护】(B02·围护结构非承载桩), 排桩=围护非承载桩, 绕开归B02; 2022第30题/2023第25题地下连续墙同此绕开",
    "1A413000_086_0159(桩基工程验槽/天然地基验槽)": "'桩基验槽'命中但属【验槽】(G04 territory), 绕开",
    "1A434000_081_0130(子分部划分/地下防水验收资料)": "地基基础子分部划分通识 + 地下防水验收资料, 非桩基判分眼, 绕开",
    "1A437000_012_0018 / 136_0219(绿色施工/深化设计/源头减量)": "绿色施工泛词命中('桩'背景资料), 非桩基判分眼, 绕开(2025案例一绿色施工同此)",
    "1A434000_070_0109(B058 边坡塌方·同chunk)": "同chunk B078预制桩身断裂已收(full本体), B058边坡塌方属土方开挖通病(G01/土方), EXT_NOISE剔除不收(留痕)",
    "G01(基坑开挖降水)territory": "G01是开挖/降水/支护配合采分轴, G03是桩基(沉桩/灌注/检测/质量), 严格分界不混(同背景案例的开挖/降水部分非G03判分眼)",
    "B02(基坑支护)territory": "灌注桩排桩/地下连续墙=围护结构归B02, 承载桩(预制/灌注/沉管)归G03, 严格分界",
}


def main():
    d = json.load(open(BUNDLE, encoding="utf-8"))
    recs = d["records"]
    # chunk -> first record (代表卡)
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
            if EXT_NOISE.search(blob):  # full/ext 都剔噪声(地基处理/边坡/防水)
                continue
            prefix = "[🔵验收/安全外延] " if mode == "ext" else ""
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
            if EXT_NOISE.search(rt):
                continue
            sps.append({
                "statement": ("[🔵验收/安全外延] " if mode == "ext" else "") + rt,
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
            if EXT_NOISE.search(desc):
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
        "考点": "G03 桩基施工与质量问题",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 27, canonical 主锚 1A413032 桩基础施工 resolve✅ name完全相符, 编译库有13个细分leaf 1A413032-R01~R13 完整record家族; supporting 1A413067/068/069 resolve✅ name相符但无独立record, 锚挂 primary 子项 R*)",
        "编译库覆盖说明": "registry primary 1A413032(桩基础施工)是 canonical taxonomy 专属判断节点(name 与 G03 完全相符, resolve✅, 故 direct 非 coarse_review), 且编译库覆盖**最好的考点之一**: 13 个细分 leaf 1A413032-R01~R13(人工挖孔护壁/成桩过程/桩基检测/桩基础施工/桩底注浆/沉管灌注/泥浆护壁流程+要求/灌注桩分类/预制桩/锤击沉桩/静力压桩/静压控制要点)散布 chunk 1A413030_090_0165~092_0173, 名实完全相符无标签污染(直读核真). supporting 1A413067(钢筋混凝土预制桩)/1A413068(钢筋混凝土灌注桩)/1A413069(桩基检测技术) 在编译库 bundle 内无独立 record(直读确认0条)——真正承载教学卡的 chunk 挂在同叶子族 primary 子项 1A413032-R*, 作弹药内部引用与 canonical supporting 并存(同 D13 的 1A413134 无record/锚挂 R10/R11/R12 模式, 同 G02 的 1A413039 无record 模式). 桩基施工本体判分眼(预制桩强度70%起吊/100%运输打桩·沉桩顺序先深后浅先大后小先长后短先密后疏·静压试压桩≥3根·灌注桩沉渣端承≤50mm摩擦≤100mm抗拔≤200mm·坍落度180~220mm·超灌≥1m·桩底注浆≥80%·人工挖孔间距≥5m)集中在 chunk 1A413030_090_0165~092_0172. 桩基检测判分眼(桩身完整性Ⅰ-Ⅳ类·钻芯孔数桩径<1.2m为1~2孔/1.2~1.6m为2孔/>1.6m为3孔·低应变高应变声波透射适用·混凝土强度≥设计70%且≥15MPa·龄期≥28d·抽检≥总桩数20%且≥10根每承台≥1根·甲级静载≥1%且≥3根)集中在 chunk 1A413030_093_0174(1A413033-R*)+1A434000_065_0096(B025/B039). 质量问题轴(题目名含'质量问题': 预制桩身断裂B078/干作业孔底虚土≤100mm B023/泥浆护壁坍孔B032)集中在 chunk 1A434000_070_0109+071_0110. 桩位偏差/验收检验(法规章1A422000_027_0045 B105)标🔵验收外延; 灌注桩施工安全(1A436000_111_0183 B124)标🔵安全外延. 真题侧关键补料(genuine G03 pile anchors): 2015第24题(预制桩锤击沉桩顺序ABC)/2017第26题(锤击法重锤低击低锤重打BD)/2018第8题(试验桩=单桩极限承载力D)/2021第14题(钻芯法判桩端持力层A)/2024第9题(预制桩沉桩先密后疏D)/2016案例1问题1(灌注桩超灌0.8~1.0m·甲级抽检≥30%且≥20根)/2022案例三(沉管灌注单打/复打/反插法·边锤击边拔管浇筑)/2023办公楼案例(检测钻芯低应变声波透射·抽检20%≥10根每承台≥1根)/2024案例二(排桩灌注桩身≥C25·先桩后帷幕·泛浆≥500mm)/2025案例三(灌注桩试件随意留置不正确·验收桩长桩径·检测低应变高应变声波透射钻芯). CFG桩成桩工艺2021第1题标🔵邻接(CFG=复合地基处理桩非G03承载桩). 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"G03 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
