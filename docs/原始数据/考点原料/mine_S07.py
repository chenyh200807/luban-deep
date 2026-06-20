#!/usr/bin/env python3
"""S07 安全事故等级判定与上报 — 挖矿器 (确定性).

从 rich_leaf_context_bundle.json 抽 S07 真采分点, 产 _S07_compiled_source.json (照 C06/S06 结构).

考点身份 (注册表 slot 19, **coarse_review**):
  primary  1A436040 常见施工生产安全事故及预防
  support  1A436041 常见施工安全事故类型 / 1A436000-B023 伤亡事故等级 / 1A436000-B066 建筑安全生产事故分类
  ⚠️ 注册表注: 事故等级/分类可锚(编译库有), 但**上报程序(逐级上报/1h/2h/补报30天/事故调查组组成)需补 source_ref**——
     编译库内确实**无上报程序教学锚**(只有事故等级阈值卡 + 事故分类卡), 上报程序判分眼全靠真题侧.
     本 pack 标 coarse_review + needs_leaf_review, 不进学员默认入口.

  编译库现实(直读核真):
    - 真正的"事故等级三阈值(死亡/重伤/直接经济损失)"判分眼集中在 chunk 1A436000_129_0207
      (leaf 1A436000-B023 伤亡事故等级): 特别重大≥30死/≥100伤/≥1亿; 重大10-30死/50-100伤/5000万-1亿;
      较大3-10死/10-50伤/1000万-5000万; 一般<3死/<10伤/<1000万. **三数字门槛是判分眼, 已逐档核真.**
    - 事故分类(按原因及性质: 生产/质量/技术/环境事故)在 chunk 1A436000_128_0206
      (leaf 1A436000-B066 建筑安全生产事故分类). ⚠️ 真题2020第26题答案=AE(生产+环境), 与编译库"四类"口径有差异——
      标textbook-vs-exam冲突, 判分以真题为准.
    - 上报程序(立即报告本单位负责人→逐级上报1h/2h、补报30天、事故调查组组成)**编译库无锚**,
      靠真题侧 _S07_exam_evidence.json(2015第19题补报30天 / 2019第17题立即报告本单位负责人 /
      2017案例三+2016案例2 事故等级判定+调查组组成).

⚠️ 源库标签污染 + 名实不符 supporting leaf 防御 (前面新产都踩过):
  - chunk 1A436000_129_0207: 三个 leaf(B023伤亡事故等级 / B083按严重程度分类 / B085按类别分类)**内容完全相同**
    (都是事故等级阈值卡 + 12类事故卡) —— 名实部分不符(B085名义"按类别"实际也是阈值卡), 只取 B023(registry supporting,
    名实最相符)作本体锚, B083/B085 同卡不重复收(留痕).
  - chunk 1A436000_128_0206: 四个 leaf(B060常见事故类型 / B066事故分类 / B079手持电动工具 / B084按原因性质分类)
    **共用同一张"事故四大分类"卡 + 一张"手持电动工具禁忌"卡** —— B079名义"手持电动工具"实际混入事故分类卡(名实不符).
    只取 B066(registry supporting, 名义=事故分类)作本体锚, 且**剔除手持电动工具禁忌卡**(非S07判分眼). 余leaf绕开留痕.
  - 重大事故隐患(chunk 0009/0010)是**与"事故等级判定"相邻但不同的概念**(隐患判定≠事故等级判定):
    取作🔵邻接外延(2025真题重大隐患印证), 不当S07事故等级主采分点.
  - 与 S01/S02(脚手架/起重)/J01(危大范围)区分: 0010 chunk 含各分项"重大隐患情形"(高处作业/基坑/模板/脚手架/起重),
    属各安全专项的隐患, 仅作邻接外延点名, 不展开当S07采分.
"""
import json, re, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
BUNDLE = os.path.join(ROOT, "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json")
OUT = os.path.join(ROOT, "docs/原始数据/考点原料/_S07_compiled_source.json")

KEYWORDS = ("生产安全事故|事故等级|特别重大事故|重大事故|较大事故|一般事故|死亡人数|重伤|直接经济损失|"
            "事故报告|事故上报|上报程序|逐级上报|1小时|2小时|事故分类|应急预案|事故调查|"
            "30人|10人|3人|1亿元|5000万|1000万")

# 经人工核真的 (chunk, leaf) 白名单 + 每 chunk 允许采用的内容类型.
# mode: "full"=取该 chunk 全部 TC/rule/EP ; "ext"=邻接外延(标🔵外延, 非S07事故等级主采分)
CHUNK_POLICY = {
    # ── 主轴本体 (事故等级 三阈值判分眼) ──
    ("1A436000_129_0207", "1A436000-B023"): ("full", "本体·registry supporting 伤亡事故等级(判分眼): 事故等级依死亡/重伤/直接经济损失划分——特别重大(≥30死/≥100伤/≥1亿)、重大(10-30死/50-100伤/5000万-1亿)、较大(3-10死/10-50伤/1000万-5000万)、一般(<3死/<10伤/<1000万) + 建筑业12类事故. **三数字门槛逐档核真**"),
    # ── 主轴本体 (事故分类) ──
    ("1A436000_128_0206", "1A436000-B066"): ("full", "本体·registry supporting 建筑安全生产事故分类: 按原因及性质分生产/质量/技术/环境事故. ⚠️真题2020第26题答案AE(生产+环境)与编译库'四类'口径差异, 标textbook-vs-exam冲突, 判分以真题为准. (剔除同chunk混入的'手持电动工具禁忌'卡, 非S07判分眼)"),
    # ── 邻接外延 (重大事故隐患——与事故等级判定相邻但不同概念) ──
    ("1A436000_006_0009", "1A436000-B160"): ("ext", "邻接外延·重大事故隐患四大类(隐患判定≠事故等级判定): 企业无证施工/人员无证上岗/特种作业无证/专项方案缺失或未论证. 2025真题重大隐患印证, 标🔵邻接"),
    ("1A436000_007_0010", "1A436000-B161"): ("ext", "邻接外延·重大事故隐患判定标准(各分项): 无证/超资质、基坑超挖/无监测、模板/脚手架/起重/高处作业/临电/拆除各情形. 属各安全专项隐患, 仅点名作邻接, 标🔵"),
    # ── 原理底座 (应急救援/重大危险源控制) ──
    ("1A436000_103_0169", "1A436000-B019"): ("ext", "原理外延·重大危险源控制五要素+应急救援预案: 辨识→评价→管理→安全报告→应急救援预案. 事故上报/应急的原理底座, 标🔵原理非判分眼"),
}

# ext 模式剔除噪声卡(手持电动工具/砂轮等非S07判分眼)
EXT_NOISE = re.compile(r"手持电动工具|砂轮|双重.*绝缘|刀具.*模具")


def pj(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(x) if isinstance(x, str) else None
    except Exception:
        return None


# 明确绕开的污染 / 跨考点 / 名实不符 leaf (留痕)
SKIPPED = {
    "1A436000_129_0207(B083/B085 按严重程度/按类别分类)": "与 B023(伤亡事故等级)同 chunk 同卡(完全相同的事故等级阈值卡+12类事故卡), B023已收(registry supporting名实最相符), B083/B085名实部分不符(B085名义'按类别'实际是阈值卡)不重复收",
    "1A436000_128_0206(B060/B079/B084 事故类型/手持工具/按原因性质)": "与 B066(事故分类)同 chunk 共用同卡, B066已收(registry supporting). B079名义'手持电动工具'实际混入事故分类卡(名实不符), B060/B084与B066同义不重复收; 该chunk的'手持电动工具禁忌'卡属电动工具安全非S07判分眼, 已在B066收点时剔除",
    "1A436000_006_0009(B067/B159 重大隐患判定标准/重大事故隐患)": "与 B160(重大隐患四大类)同 chunk, B160已收作邻接外延. 重大隐患=隐患判定概念, 与S07'事故等级判定'相邻但不同, 仅收一锚作🔵邻接, 不重复",
    "1A436000_007_0010(B031/B040/B068/B069/B075/B091/B112/B141/B156/B179 各分项隐患情形)": "危大/基坑/临电/模板/脚手架/起重/高处作业各分项重大隐患情形 —— 属各安全专项(S01脚手架/S02起重/J01危大)的隐患清单, B161已收作'各分项隐患'代表锚作邻接🔵, 其余分项情形绕开归各自考点不展开",
    "1A436000_103_0169(B162~B166 重大危险源控制/评价/辨识)": "重大危险源控制/评价/辨识五步 —— 与 B019(应急救援预案)同 chunk, B019已收作原理底座, 余重大危险源细分卡属危险源辨识考点(非S07事故等级/上报判分眼)绕开",
    "上报程序(逐级上报/1h/2h/补报30天/事故调查组组成)": "⚠️编译库内**无上报程序教学锚**(全库扫描: 1h/2h匹配全是楼梯净高/混凝土养护等跨考点噪声). 上报程序判分眼为S07核心但编译库未覆盖, 全靠真题侧 _S07_exam_evidence.json(2015第19题补报30天/2019第17题立即报告本单位负责人/2017案例三+2016案例2 等级判定+调查组组成). **这正是注册表coarse_review/needs_leaf_review的根因**",
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
        "考点": "S07 安全事故等级判定与上报",
        "keywords": KEYWORDS,
        "命中单元": len(units),
        "去重采分点": total_sp,
        "注册表对齐状态": "coarse_review (slot 19, needs_leaf_review, 不进学员默认入口)",
        "编译库覆盖说明": "registry primary 1A436040(常见施工生产安全事故及预防)/supporting 1A436041(常见施工安全事故类型) 为taxonomy树节点; 真'事故等级三阈值'判分眼集中在编译库 chunk 1A436000_129_0207(leaf 1A436000-B023 伤亡事故等级·registry supporting): 特别重大≥30死/≥100伤/≥1亿、重大10-30死/50-100伤/5000万-1亿、较大3-10死/10-50伤/1000万-5000万、一般<3死/<10伤/<1000万; 事故分类(生产/质量/技术/环境)在 chunk 1A436000_128_0206(leaf 1A436000-B066·registry supporting). ⚠️**上报程序(立即报告本单位负责人→逐级上报1h/2h、补报30天、事故调查组组成)编译库无教学锚**(全库扫描确认), 判分眼全靠真题侧 _S07_exam_evidence.json —— 这正是注册表coarse_review/'上报程序需补source_ref'的根因. coarse 考点弹药事故等级阈值锚集中(主轴卡少), 上报/调查组判分眼靠真题侧补.",
        "污染绕开chunk": SKIPPED,
        "units": units,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"S07 挖矿: {len(units)} 单元 / {total_sp} 采分点 → {os.path.basename(OUT)}")
    print(f"绕开污染/跨考点/名实不符 chunk: {len(SKIPPED)} 类")
    for u in units:
        print(f"  [{u['tier']:4}] [{u['source_ref'].get('chunk_id')} / {u['leaf_id']}] {u['note'][:46]} :: {len(u['scoring_points'])} sp")


if __name__ == "__main__":
    main()
