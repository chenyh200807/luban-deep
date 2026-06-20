#!/usr/bin/env python3
"""D11 抹灰工序与质量控制 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 D11 真采分点, 产 _D11_compiled_source.json (照 C06/C01/S05/N01 结构).

考点身份 (注册表 slot 21, **direct**):
  primary    1A434030-E01 装饰装修——抹灰工程
  supporting 1A422000-B012 不同材料基体交接处抹灰防裂措施
  taxonomy sha 26dbb542b31601d6b3255d53463d0007c0c7eaea5a24ad9c338b3742baa976c8

  ⚠️ 编译库现实(诚实标注): 注册表两 code(1A434030-E01 / 1A422000-B012)均【名实相符】直读核真确属抹灰工程本体
  (1A434030-E01=抹灰加强措施 35mm/100mm; 1A422000-B012=不同材料基体交接处防裂网100mm + 抹灰基层含水率 + 耐水腻子),
  故 status=direct (与 C06/S07 的 coarse_review 不同——D11 主锚名实相符)。
  但 RichLeaf 编译库对【一般抹灰底/中/面三层工序、水泥砂浆/混合砂浆配比、护角阳角、墙面抹灰空鼓开裂防治】
  几乎【零专用 leaf】(全库确定性扫描确认: 抹灰本体卡集中在 1A422000_042/043 两个相关法规 chunk 的"加强措施/防裂网/含水率"
  几张卡)。故 D11 弹药【教材锚很薄、主轴判分眼(底中面三层/砂浆配比/护角/空鼓防治程序)靠真题侧补足】——
  这正是注册表把 D11 锚到"加强措施+交接处防裂"两点而非"全抹灰工序"的根因。挖矿层老实标"教材锚薄·judge靠真题"。

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前 7 个新产 C07/S05/N01/C01/J01/C06/S07 都踩过):
  - 必须核 compiled_context 真实内容确属"抹灰加强措施/不同材料基体交接处防裂/抹灰基层含水率/找平耐水腻子"抹灰本体,
    名实不符卡(同 chunk 的"门窗射钉禁令")绕开并留痕。
  - 与 D12(饰面砖/板·空鼓)/涂饰工程/外保温薄抹灰/地面板块空鼓 严格区分:
    * "粘贴保温板薄抹灰/抹面胶浆/玻纤网"(1A413050-R10/R12/R43) 是【外保温系统】territory(薄抹灰≠一般抹灰),
      命题考保温构造非抹灰工序 → 绕开归保温考点。
    * "涂饰工程应在抹灰...完成后进行"(1A413064-R03/R05/R07/R08) 抹灰是涂饰的【前置工序衔接】,涂饰本体非抹灰本体
      → 仅取"涂饰在抹灰后"工序衔接句作 🔵 外延(工序先后), 涂饰分类/环境温度卡绕开归涂饰考点。
    * "地面板块类空鼓起拱"(1A434000-B011) 是【地面工程】空鼓(板块铺贴), 非【墙面抹灰】空鼓 → 绕开归 D14/地面考点。
    * "填充墙裂缝防治 2φ6@500mm/加强网片"(1A434000-B013/B046) 是 C06/Q03 territory(填充墙交接裂缝),
      与 D11"不同材料基体交接处加强网"邻接但本体不同 → 标 🔵 邻接参照, 不当 D11 抹灰采分主点。
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_D11_compiled_source.json")

KEYWORDS = ("抹灰|一般抹灰|装饰抹灰|底层|中层|面层|抹灰层|水泥砂浆|混合砂浆|空鼓|开裂|裂缝|护角|阳角|交接处|"
            "不同材料基体|防裂|挂网|加强网|分层抹灰|平整度|垂直度|找平|界面处理|界面剂|含水率|耐水腻子|搭接宽度")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型 + 每卡级过滤.
# mode: "full"=取该 chunk 全部抹灰本体 TC/rule/EP ; "ext"=本体/工序邻接外延(标本体外延); "wai"=验收/通病/邻接外延(标🔵外延)
# card_keep: 只保留 title/content 命中此正则的卡(剔同 chunk 名实不符卡, 如门窗射钉禁令)
CHUNK_POLICY = {
    # ── 主轴本体 (抹灰加强措施 / 交接处防裂网 / 基层含水率 / 找平耐水腻子) ──
    ("1A422000_042_0068", "1A434030-E01"): (
        "full", "本体·primary 注册表主锚(名实相符): 抹灰工程加强措施——抹灰总厚度≥35mm时应采取加强措施; 不同材料基体交接处加强网搭接宽度≥100mm — D11 抹灰本体最核心判分眼",
        re.compile(r"抹灰|加强|搭接|交接|基体")),
    ("1A422000_043_0069", "1A422000-B012"): (
        "full", "本体·supporting 注册表辅锚(名实相符): 不同材料基体交接处抹灰防裂措施——加强网与各基体搭接宽度≥100mm + 抹灰基层含水率(溶剂型≤8%/乳液型≤10%/木材≤12%) + 厨卫找平层耐水腻子 (门窗射钉禁令同chunk名实不符已剔)",
        re.compile(r"抹灰|加强网|搭接|交接|基体|含水率|耐水腻子|找平|界面")),
    # ── 本体外延 (重复主锚, 作冗余核真) ──
    ("1A422000_042_0068", "1A422000-B019"): (
        "ext", "本体外延·分项工程及主控项目: 抹灰工程加强措施(与 E01 同卡·35mm/100mm, 作冗余核真锚)",
        re.compile(r"抹灰|加强|搭接|交接|基体")),
    # ── 工序衔接 / 含水率 外延 (标🔵外延, 非抹灰本体主采分) ──
    ("1A413030_141_0276", "1A413064-R07"): (
        "wai", "🔵外延·工序衔接: 涂饰工程应在抹灰、吊顶、细部、地面湿作业及电气工程等完成后进行(抹灰=涂饰前置工序; 涂饰本体非抹灰本体, 仅取工序先后句)",
        re.compile(r"抹灰.*完成后|完成后进行")),
    ("1A411011_022_0043", "1A411020-R34"): (
        "wai", "🔵外延·抹灰基层含水率(建筑构造设计层重复卡): 混凝土或抹灰基层含水率≤8%/木材≤12%/乳液型≤10% (与 B012 含水率重复, 作冗余核真; 同卡饰面砖伸缩缝/地面构造层属D12/地面考点已剔)",
        re.compile(r"抹灰基层含水率|抹灰基层")),
}

# wai/full 模式按 card_keep 逐卡过滤(剔同 chunk 名实不符 / 跨考点卡)
NOISE_BLOCK = re.compile(r"射钉|门窗安装|饰面砖伸缩缝|地面构造层次|涂饰工程分类|按成膜物质")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 chunk (留痕)
SKIPPED = {
    "1A413030_127_0241/128_0242/128_0243(1A413050-R10/R12/R43 外保温薄抹灰)": "屋面与防水>外墙保温>粘贴保温板薄抹灰/抹面胶浆+玻纤网/EPS钢丝网架厚抹灰层 — 属【外墙外保温系统】territory(薄抹灰是保温系统构造层, 非一般/装饰抹灰工序), 命题考保温系统分类/构造, 绕开归保温考点",
    "1A413030_141_0276(1A413064-R03/R05/R08 涂饰分类/环境)": "装饰装修>墙体饰面>涂饰工程分类(水性/溶剂型/美术涂料)+环境温度5~35℃ — 属【涂饰工程】territory, 涂饰本体非抹灰本体; 仅 R07 的'涂饰应在抹灰后进行'工序衔接句取作🔵外延, 涂饰分类/环境卡绕开归涂饰考点",
    "1A434000_078_0123(1A434000-B011 地面板块空鼓起拱)": "施工质量管理>地面工程中板块类地面空鼓起拱 — 属【地面工程/D14】空鼓(板块铺贴层空鼓·界面剂+背砂), 非【墙面抹灰层】空鼓; 命题考地面板块铺贴, 绕开归地面/饰面考点(D11空鼓主轴是墙面抹灰层空鼓, 编译库无专用卡, 靠真题侧)",
    "1A434000_074_0116(1A434000-B013/B046 填充墙裂缝/焊缝/地基)": "施工质量管理 chunk 0116 名实不符混卡: 填充墙裂缝防治(2φ6@500mm/14d后施工/半砖斜砌/加强网片)=C06/Q03 territory(填充墙交接裂缝, 与D11'不同材料基体抹灰防裂'邻接但本体不同, 标🔵邻接参照非D11采分主点); 焊缝夹渣/地基不均沉降/地下防水渗漏卡全部绕开归各自考点(钢结构/Q03/防水)",
    "1A411011_022_0043(1A411020-R26/R28/R30/R35/R36 地面/裱糊/饰面砖/软包/饰面板构造)": "建筑设计与构造>建筑构造设计要求>地面装修/墙体裱糊/外墙饰面砖/织物软包/饰面板构造 — 属【装修构造设计层】(命题语境是构造设计而非抹灰施工工序); 仅 R34 的'抹灰基层含水率'卡取作🔵外延冗余核真, 其余构造设计卡绕开归装修构造/D12饰面考点",
    "1A422000_043_0069(1A422000-B156 门窗安装)": "相关法规>门窗安装要求(砌体上安装门窗严禁射钉固定) — 与 B012 同 chunk 但属【门窗安装】territory名实不符, 卡级过滤已剔(NOISE_BLOCK), 绕开归门窗考点",
    "1A437000_138_0221(1A437000-B065/B066 绿色施工)": "绿色建造>装饰装修绿色施工要点(抹灰墙面宜喷雾养护泛词) — 属【绿色施工/环境管理】territory, '抹灰墙面'仅泛词命中(养护措施非抹灰工序本体), 绕开归绿色施工考点",
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
    for (ch, lf), (mode, note, card_keep) in CHUNK_POLICY.items():
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
            if NOISE_BLOCK.search(blob):
                continue
            if card_keep and not card_keep.search(blob):
                continue
            content = t.get("content", "") or ""
            prefix = "[🔵外延] " if mode == "wai" else ""
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
            if NOISE_BLOCK.search(rt):
                continue
            if card_keep and not card_keep.search(rt):
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
            if NOISE_BLOCK.search(desc):
                continue
            if card_keep and not card_keep.search(desc) and not re.search(r"抹灰|加强|基层|交接|防裂", desc):
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
        "考点": "D11 抹灰工序与质量控制",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "direct (slot 21; primary 1A434030-E01 / supporting 1A422000-B012 名实相符直读核真)",
        "编译库覆盖说明": (
            "注册表两 code(1A434030-E01 装饰装修——抹灰工程 / 1A422000-B012 不同材料基体交接处抹灰防裂措施)均【名实相符】"
            "直读核真确属抹灰本体, 故 status=direct(非 C06/S07 的 coarse_review)。但 RichLeaf 编译库对【一般抹灰底/中/面三层工序、"
            "水泥砂浆/混合砂浆配比、护角阳角、墙面抹灰层空鼓开裂防治程序】几乎零专用 leaf——抹灰本体教材锚集中在 "
            "1A422000_042/043 两个相关法规 chunk 的'加强措施(35mm/100mm)/交接处防裂网(≥100mm)/基层含水率(8%/10%/12%)/找平耐水腻子'"
            "几张卡(全库确定性扫描确认)。故 D11 教材锚很薄、主轴判分眼(底中面三层/砂浆配比/护角/空鼓防治)【靠真题侧补足】——"
            "这正是注册表把 D11 锚到'加强措施+交接处防裂'两点而非'全抹灰工序'的根因。数值判读锚靠真题侧 _D11_exam_evidence.json。"),
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"D11 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:50]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
