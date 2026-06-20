#!/usr/bin/env python3
"""G02 土方回填压实与检测 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 G02 真采分点, 产 _G02_compiled_source.json (照 S06/S07/C06/D13 结构).

考点身份 (注册表 slot 26, **direct**):
  primary  1A413039 土方回填                      (canonical 专属叶子, resolve ✅, name 与 G02 完全相符)
  support  1A413000-B020 土方填筑与压实           (resolve ✅, 承载教学卡的编译库 chunk 锚)
           1A436000-B043 基坑（槽）土方开挖与回填安全技术措施 (resolve ✅, 安全侧)
  ⚠️ 注册表/编译库现实(直读核真):
     - canonical 主锚 1A413039(土方回填)是 taxonomy 树上的专属叶子(name 完全相符), 故 `direct`(非 coarse_review).
       但 1A413039 在编译库 bundle 内**无独立 record**(直读确认 0 条)——真正承载教学卡的编译库 chunk
       挂在 supporting leaf 1A413000-B020(土方填筑与压实)同一 chunk 1A413000_085_0158(同一'土料要求/土方回填/
       土方填筑与压实/基底处理'叶子族, 4 个 leaf B018/B019/B020/B040 **共用同一张卡**, hash b15b633f).
       作弹药内部引用与 canonical 主锚并存. (同 D13 的 1A413134 无 record / 锚挂 R10/R11/R12 模式.)
     - 真正的"土方回填压实判分眼"集中在 chunk 1A413000_085_0158(leaf B018/B019/B020/B040·共用卡):
       填方土料禁用(淤泥/淤泥质土/有机质>5%/含水量不符压实要求的黏性土);
       填方边坡(<10m 1:1.5; >10m 上1:1.5/下1:1.75);
       填土压实参数表(平碾250-300mm/6-8遍; 振动压实机250-350mm/3-4遍; 柴油打夯机200-250mm/3-4遍; 人工打夯<200mm/3-4遍).
       **逐尺寸/逐遍数核真.**
     - 真正的"压实检测判分眼"集中在 chunk 1A434000_064_0095(leaf 1A434000-B007·地基与基础工程质量检验与标准):
       施工结束后应进行标高及压实系数检验; EP"土方回填质量检查必须检查内容=填筑厚度/含水量控制/压实系数"(排水系统非必查).
       **逐条核真.** 注意: 环刀法/灌砂法/灌水法等具体检测方法编译库**全无锚**(全库扫描确认), 判分眼靠真题侧.
     - 换填/压实系数 chunk 1A413030_087_0162(leaf B084)是【地基处理·换填地基】采分轴(灰土≥0.95/其他≥0.97),
       与 G02 土方回填相邻但非同采分眼(换填≠回填), 标🔵邻接外延(参数借力).
     - 安全侧 chunk 1A436000_109_0179(leaf 1A436000-B043)主体是【基坑开挖】(开挖前勘察/操作间距/堆土),
       与 G01(开挖降水)同territory; 仅 TC2"严禁在坑底有人时回填"是 G02 回填安全眼, 取该片段标🔵安全外延, 余绕开.

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前 10 个新产都踩过):
  - chunk 1A413000_085_0158: 4 个 leaf(B018土料要求/B019土方回填/B020土方填筑与压实/B040基底处理)**共用同一张卡**
    (cards hash 完全相同 b15b633f). 只取 B020(registry support, 名实最贴'压实')作本体锚, B018/B019/B040 同卡不重复收(留痕).
  - chunk 1A413030_088_0163 (leaf B031-R01~R08 复合地基/夯实地基/换填/CFG桩): '压实/夯实/碾压'命中但属【地基处理方法】
    采分轴(强夯/换填/桩), 非 G02 土方回填判分眼, 全部绕开(归地基处理本体, 与 G02 不同采分轴).
  - chunk 1A413030_087_0162 (leaf B084 换填地基): 换填地基压实系数(灰土≥0.95)是【地基处理·换填】, 与回填相邻;
    仅取压实系数参数作🔵邻接外延(参数借力), 不当 G02 本体采分点.
  - chunk 1A413000_075_0143/076_0145 (八类土分类/土物理指标): 土方工程通识背景(坚实系数/可松性/天然密度),
    取'可松性'(真题2015第8题印证土方平衡)作🔵通识, 余八类土分类绕开归土方开挖通识.
  - chunk 1A422000_028_0048 (leaf B029 地下防水/B036 基坑开挖回填法规): EP混入'C25/冠梁/防水混凝土抗渗'(D-防水/B02-支护),
    '分层均衡/严禁超挖'是基坑开挖(G01), 非 G02 回填压实判分眼, 绕开(法规章泛词命中).
  - chunk 1A411011_022_0043 / 1A412010_055_0106~0108 ('含水率'命中): 装修裱糊/木材含水率, 与 G02 回填含水率
    **完全异义**(同词不同物), 全部绕开.
  - 安全 chunk 1A436000_109_0179 (基坑开挖安全): 主体=开挖(勘察/间距/堆土)归 G01, 仅'坑底有人禁回填'片段是 G02, 取片段标🔵.
  - 与 G01(开挖降水)区分: G01 是开挖/降水/支护配合, G02 是回填(土料/分层/压实/检测); 严格分界不混.
  - 与 B02(基坑支护)区分: B02 是支护选型/降水/监测, 非回填压实.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_G02_compiled_source.json")

KEYWORDS = ("土方回填|回填土|填方|压实|分层回填|分层夯实|分层压实|压实系数|压实度|虚铺厚度|铺土厚度|含水率|最优含水率|"
            "环刀法|灌砂法|灌水法|取样检测|填料|夯实|碾压|回填材料|基坑回填|管沟回填|对称回填")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP (本体判分眼) ; "ext"=邻接外延/通识(标🔵, 非 G02 回填压实主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (土方回填压实判分眼: 土料/边坡/压实参数表) ──
    ("1A413000_085_0158", "1A413000-B020"): ("full", "本体·registry support 土方填筑与压实(判分眼): 填方土料禁用淤泥/淤泥质土/有机质>5%/含水量不符压实要求的黏性土; 填方边坡<10m 1:1.5/>10m 上1:1.5下1:1.75; 填土压实参数表(平碾250-300mm/6-8遍·振动压实机250-350mm/3-4遍·柴油打夯机200-250mm/3-4遍·人工打夯<200mm/3-4遍). **逐尺寸/逐遍数核真**"),
    # ── 主轴本体 (压实检测判分眼: 压实系数检验/必查内容) ──
    ("1A434000_064_0095", "1A434000-B007"): ("full", "本体·压实检测判分眼(施工质量管理章): 土方回填施工结束后应进行标高及压实系数检验; 质量检查必须检查内容=填筑厚度/含水量控制/压实系数(排水系统非必查). **逐条核真**. 注意: 环刀法/灌砂法/灌水法具体方法编译库无锚, 靠真题侧"),
    # ── 邻接外延 (换填地基压实系数——与回填相邻非同采分眼) ──
    ("1A413030_087_0162", "1A413030-B084"): ("ext", "邻接外延·换填地基压实系数(地基处理章, 与回填相邻非同采分眼): 换填厚度0.5-3m; 灰土配合比2:8或3:7; 分层厚度200-300mm; 压实系数灰土/粉煤灰≥0.95其他≥0.97. 标🔵邻接(换填≠回填, 参数借力非G02本体判分眼)"),
    # ── 通识背景 (土的可松性/物理指标——土方平衡定性层) ──
    ("1A413000_076_0145", "1A413000-B021"): ("ext", "通识背景·土的物理性质指标(土方平衡定性层): 含水量/天然密度/干密度/可松性等指标; 真题2015第8题'土方平衡需重点考虑可松性'印证. 标🔵通识(非回填压实判分眼, 土方平衡背景)"),
    # ── 安全外延 (坑底有人禁回填——G02 回填安全片段) ──
    ("1A436000_109_0179", "1A436000-B043"): ("ext", "安全外延·registry support 基坑(槽)土方开挖与回填安全技术措施: 主体=基坑开挖安全(开挖前五项勘察/操作间距>2.5m/机械间距>10m/堆土距坑边≥1m堆高≤1.5m)归G01开挖; 其中'严禁在坑底有人时回填'是G02回填安全眼. 标🔵安全外延(开挖主体归G01, 仅回填安全片段属G02)"),
}

# ext 模式剔除噪声卡(基坑开挖勘察/堆土/桩/防水/C25 等非 G02 回填压实判分眼)
EXT_NOISE = re.compile(r"勘察内容|操作间距|堆土距坑边|严禁先挖坡脚|危岩|孤石|C25|冠梁|抗渗|防水混凝土|换填地基适用|强夯|CFG|搅拌桩")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A413000_085_0158(B018土料要求/B019土方回填/B040基底处理)": "与 B020(土方填筑与压实)同 chunk 同卡(cards hash 完全相同 b15b633f: 土料禁用/边坡/压实参数表), B020已收(registry support 名实最贴'压实'), B018/B019/B040 不重复收(留痕)",
    "1A413030_088_0163(B031-R01~R08 复合地基/夯实地基/换填/CFG桩)": "'压实/夯实/碾压'命中但属【地基处理方法·强夯/换填/桩】采分轴, 非G02土方回填判分眼, 全部绕开归地基处理本体(与G02不同采分轴)",
    "1A413000_075_0143(B001~B008 八类土分类)": "八类土分类(坚实系数/施工方法)是土方工程通识/土方开挖背景, 非回填压实判分眼; 仅 B021 物理指标'可松性'作🔵通识(2015第8题印证), 八类土分类绕开",
    "1A422000_028_0048(B029地下防水/B036基坑开挖回填法规)": "EP混入'C25/冠梁/防水混凝土抗渗'(D-防水/B02-支护)+'分层均衡/严禁超挖'(基坑开挖G01), 非G02回填压实判分眼, 法规章泛词命中绕开",
    "1A411011_022_0043 / 1A412010_055_0106~0108('含水率'命中)": "装修裱糊/木材含水率, 与G02回填含水率**同词不同物**(完全异义), 全部绕开",
    "1A436000_109_0179 基坑开挖安全主体(勘察/间距/堆土)": "基坑开挖安全(开挖前勘察/操作间距/堆土距坑边)归G01开挖, 非G02回填; 仅'坑底有人禁回填'片段取作🔵安全外延, 开挖主体绕开",
    "G01(开挖降水)territory": "G01是开挖/降水/支护配合采分轴, G02是回填(土料/分层/压实/检测), 严格分界不混(同背景案例的开挖/降水部分非G02判分眼)",
    "B02(基坑支护)territory": "B02是支护选型/降水/监测, 非回填压实, 严格分界",
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
            prefix = "[🔵邻接/通识/安全外延] " if mode == "ext" else ""
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
        "考点": "G02 土方回填压实与检测",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 26, canonical 专属叶子 1A413039 resolve✅ name完全相符; 编译库锚挂 supporting 1A413000-B020 同 chunk)",
        "编译库覆盖说明": "registry primary 1A413039(土方回填)是 canonical taxonomy 专属判断节点(name 与 G02 完全相符, resolve✅, 故 direct 非 coarse_review). 1A413039 在编译库 bundle 内无独立 record(直读确认0条)——真正承载教学卡的编译库 chunk 挂在 supporting leaf 1A413000-B020(土方填筑与压实)同 chunk 1A413000_085_0158(同'土料要求/土方回填/土方填筑与压实/基底处理'叶子族, 4 个 leaf B018/B019/B020/B040 共用同一张卡 hash b15b633f), 作弹药内部引用与 canonical 主锚并存(同 D13 的 1A413134 无record/锚挂 R10/R11/R12 模式). 土方回填压实判分眼(填方土料禁用淤泥/淤泥质土/有机质>5%/含水量不符的黏性土; 填方边坡<10m 1:1.5/>10m 上1:1.5下1:1.75; 填土压实参数表 平碾250-300mm·6-8遍/振动压实机250-350mm·3-4遍/柴油打夯机200-250mm·3-4遍/人工打夯<200mm·3-4遍)集中在 chunk 1A413000_085_0158(leaf 1A413000-B020). 压实检测判分眼(施工结束后标高及压实系数检验; 必查=填筑厚度/含水量/压实系数)集中在 chunk 1A434000_064_0095(leaf 1A434000-B007·施工质量管理章). ⚠️检测侧关键缺口: 环刀法/灌砂法/灌水法等具体检测方法编译库**全无锚**(全库确定性扫描确认), 判分眼全靠真题侧补. 换填地基压实系数(灰土≥0.95)/土可松性标🔵邻接通识; 安全侧 1A436000-B043 主体=基坑开挖归G01, 仅'坑底有人禁回填'片段属G02标🔵安全外延. 真题侧关键补料: 2016第8题(土方回填工艺错误·虚铺厚度应根据压实机具非含水量)/2018案例三问题2(回填料禁建筑垃圾·振动压实机250-350mm·压实3-4遍)/2020第29题(回填正确说法ACE·控含水率·下层压实系数合格后上层施工·先取样点布置图后试验结果)/2022第21题(不能作填方土料=淤泥淤泥质土有机质>5%·ABC)/2019第16题(密实度达不到原因=含水率过大或过小)/2015第8题(土方平衡考虑可松性)是回填压实判分眼真题锚, 详见 pack §8.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"G02 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:48]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
