#!/usr/bin/env python3
"""E06 挖矿（确定性）：工程量清单与合同价款约定（2026·GB/T50500-2024 新规）。

与既有 mine_XXX.py 同族：确定性抽取，零 LLM。差异（2026 新增点管线）：
- 源不是 RichLeaf v3.2 编译库，而是 **2026 教材结构化块**
  （FINAL_CLEANED_BOOK2026-*.json，官方《2026 教材对比明细》认定 GB/T50500-2024
  清单计价整目变动；RichLeaf 编译库基于旧教材，不含本批新增内容）。
- 采分点三类 namespace（全部既有，不新造）：
  * ``cc:<chunk_id>:<n>`` = 教材块 content_markdown **逐字原文**摘句（J01/C01 先例）；
    本脚本对每条 cc quote 做**归一化包含闸**（去空白后必须是块原文子串，fail-closed），
    杜绝改写/编造混入"教材原文"。
  * ``kc:<chunk_id>:<n>`` = 块第 n 张 knowledge_card（LLM 增强产物，非原文，pack 内
    只作辅助锚，凡与 cc 原文冲突以 cc 为准）。
  * ``ca:<chunk_id>`` = 块 assessment 生成题（同上，辅助）。
- 每个 unit 带 source_ref（chunk_id + file_sha256 + span_hash=块 md sha256），
  即"采分点必须教材溯源"铁律的机器可核形态。

用法::

    python3 docs/原始数据/考点原料/mine_E06.py [--book-root <dir>]

注：2026 教材块 JSON 为 gitignored 原始数据，默认读主仓库工作区路径。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BOOK_ROOT = Path(
    "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/原始数据/2026_副本/2026教材/第二次加强"
)
OUT = HERE / "_E06_compiled_source.json"

BOOK_FILE = "FINAL_CLEANED_BOOK2026-222-382_fixed.json"

# ── 目标块（官方变点定位：《2026 教材对比明细》变化#56–#64 = GB/T50500-2024
#    清单计价/合同价款整目变动，粗清单定位 1A432002_035_0046/036_0047/037_0048
#    均 likely_new；031_0041 为争议解决支撑块（unchanged）。）────────────────
CHUNKS = [
    "1A432002_035_0046",
    "1A432002_036_0047",
    "1A432002_037_0048",
    "1A432002_031_0041",
]

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub("", s or "")


# ── 采分点定义：cc quote 全部逐字取自块 content_markdown（含闸核验）───────────
# (point_id, statement, quote)
CC_POINTS: dict[str, list[tuple[str, str]]] = {
    "1A432002_035_0046": [
        ("清单四部分分别编制及计价：分部分项工程项目清单、措施项目清单、其他项目清单和增值税",
         "（1）工程量清单应按分部分项工程项目清单、措施项目清单、其他项目清单和增值税分别编制及计价。"),
        ("清单项目价款可采用单价计价、总价计价；不宜采用时也可采用费率计价等其他计价方式",
         "（2）工程量清单的清单项目价款确定可采用单价计价、总价计价方式。不宜采用单价计价、总价计价方式的，也可采用费率计价等其他计价方式。"),
        ("清单准确性完整性责任：单价合同分部分项清单归发包人；总价合同已标价分部分项清单归承包人；措施项目清单无论何种合同均归承包人",
         "（4）采用单价合同的工程，分部分项工程项目清单的准确性、完整性应由发包人负责；采用总价合同的工程，已标价分部分项工程项目清单的准确性、完整性应由承包人负责。建设工程无论是采用单价合同或总价合同，按项编制的措施项目清单的完整性及准确性均应由承包人负责。"),
        ("综合单价所含因素：总价合同清单缺陷费用/完工交付必要施工任务及辅助工作费用/工序条件气候因素费用",
         "① 总价合同中出现工程量清单缺陷所需的费用；\n\n② 完成符合完工交付要求的相应清单项目必要的施工任务及其不可或缺的辅助工作所需的费用；\n\n③ 因施工工序、施工条件、环境气候等因素影响所引起的费用。"),
        ("措施项目清单列举（15 类）",
         "（3）措施项目主要包括临时设施、脚手架、二次搬运、夜间施工增加、冬雨期施工增加、环境保护、文明施工、安全施工、垂直运输、其他大型机械进出场及安拆、施工排水、施工降水、特殊地区施工增加、已完工程及设备保护、既有建（构）筑物及设施保护。"),
        ("特殊环境施工措施费情形（地下空间/高层超高层/恶劣气候/交叉作业等）",
         "② 在地下空间（地下室、暗室、库内、洞内等），高层或超高层建筑、有害身体健康 的环境、恶劣气温气候、冬雨季、交叉作业等环境下进行施工所需的措施费用；"),
        ("其他项目清单内容：暂列金额、专业工程暂估价、计日工、总承包服务费、合同约定的其他项目",
         "（4）其他项目清单内容包括：暂列金额、专业工程暂估价、计日工、总承包服务费、合同约定的其他项目。"),
        ("总承包服务费可采用费率或总价计价；计日工可采用标准规定的单价计价",
         "① 总承包服务费可采用费率或总价计价方式计价，以其计价基础乘以费率或以项计算清单项目价格；计日工可采用标准规定的单价计价方式计价。"),
        ("暂列金额、专业工程暂估价应按招标工程量清单提供金额填报投标价",
         "② 暂列金额、专业工程暂估价应按招标工程量清单提供的相应金额填报投标价。"),
    ],
    "1A432002_036_0047": [
        ("承包人承担：单价合同下完成清单所有工作所需费用",
         "③ 采用单价合同的工程，承包人为完成工程量清单所有工作所需费用；"),
        ("承包人承担：施工机具/技术/组织管理等自身原因造成的施工费用增加",
         "⑤ 承包人因施工机具使用、施工技术应用以及组织管理水平等自身原因造成的施工费用增加。"),
        ("承包人承担：总价合同已标价清单缺陷（单价计价的暂定数量清单项目除外）",
         "② 采用总价合同的工程，已标价工程量清单存在的缺陷（单价计价的暂定数量清单项目除外）；"),
        ("合同类型：可采用单价/总价/成本加酬金；紧急抢险救灾或特别复杂工程宜成本加酬金",
         "（1）建设工程的施工合同可采用单价合同、总价合同、成本加酬金合同等。紧急抢险、救灾或特别复杂的工程宜采用成本加酬金合同。"),
        ("招标工程合同价格不得背离招标文件实质性内容（工程范围/工期/价款/质量）",
         "（2）实行招标的工程，合同约定的合同价格不得背离招标文件中关于工程范围、工期、价款、质量等实质性内容。"),
        ("单价合同分部分项清单缺陷应按计价标准调整合同价格",
         "（3）采用单价合同的工程，工程量清单中的分部分项工程项目清单存在缺陷的，应按照计价标准相关的规定调整合同价格。"),
        ("总价合同清单缺陷价格视为已含合同总价；已标价清单单价可用于变更/新增计价",
         "（4）采用总价合同的工程，出现工程量清单缺陷的，其价格应视为已包含在合同总价中。已标价工程量清单的单价可按合同约定应用于工程变更、新增工程等合同价格调整的计价。"),
        ("成本加酬金合同总价为暂定价，按实算成本+约定酬金及增值税后调整总价",
         "（5）采用成本加酬金合同的工程，合同总价为暂定价，应按实计算合同工程成本，并按合同的约定计算相应酬金及增值税后调整合同总价。"),
        ("投标报价澄清：开标后至定标前；算术误差可修正但投标总价不得调整；合理性疑问/漏报未报可要求澄清",
         "（1）招标工程进行投标报价澄清或说明的，应在工程开标后至定标前进行。投标人的投标文件存在算术误差及细微偏差的，可按计价标准规定修正，但投标总价不得做任何调整。投标报价存在报价合理性疑问和未按要求完整（漏报或未报）填写投标报价的，可要求投标人作出相应的澄清或说明。"),
    ],
    "1A432002_037_0048": [
        ("清单缺陷处置分流：总价合同承包人补充完善、不做调整；单价合同发包人担责、按计价标准调整",
         "（3）招标工程量清单应用于总价合同，存在工程量清单缺陷的，承包人应承担工程量清单缺陷的补充完善责任，工程量清单缺陷按计价标准的规定不做调整；应用于单价合同时，存在分部分项工程项目清单缺陷的，应由发包人承担相关清单缺陷责任，工程量清单缺陷应按计价标准的规定调整。"),
        ("单价合同分部分项清单工程数量为暂定量，履行中重新计量；措施清单及以项计价清单按总价计价规定计算",
         "（4）采用单价合同的分部分项工程项目清单工程数量为暂定的工程量，在合同履行中应重新计量确定，但措施项目清单和以项计价的分部分项工程项目清单应按计价标准总价计价的规定计算。"),
        ("总价合同内说明为暂定数量的清单项目按单价计价规定重新计量并调整合同价格及总价",
         "（5）采用总价合同的分部分项工程项目清单内说明是暂定数量的清单项目及其工程数量，应按计价标准单价计价的规定重新计量确定并对相关清单项目的合同价格及合同总价进行相应调整。"),
    ],
    "1A432002_031_0041": [
        ("合同争议解决三方式：争议评审/调解/仲裁或诉讼",
         "（1）委托争议评审委员会（或机构）进行评审。\n\n（2）委托具有调解能力的调解人（或机构）进行调解。\n\n（3）仲裁或诉讼。"),
    ],
}

# kc/ca 辅助锚（增强产物，pack 内标注非原文）：按块索引引入
KC_TAKE: dict[str, list[int]] = {
    "1A432002_036_0047": [1, 2],   # 合同类型适用场景 / 投标报价澄清规则
    "1A432002_037_0048": [1],      # 应用规定卡
    "1A432002_031_0041": [2],      # 争议三方式卡
}
CA_TAKE = ["1A432002_036_0047"]

# unit 划分：leaf canonical code -> (chunk, cc 起止序号列表, note, tier)
UNITS_PLAN = [
    ("1A432000-B036", "工程招标投标与合同管理 > 工程量清单规定",
     "1A432002_035_0046", [0, 1, 2],
     "本体·2026 清单规定新表述：四部分分别编制计价 / 费率计价兜底 / 清单准确性完整性责任三分流"
     "（分部分项单价归发包人·总价归承包人·措施清单恒归承包人）。官方变点#57(P246-250 整体变动)。", "full"),
    ("1A432000-B053", "工程招标投标与合同管理 > 清单计价",
     "1A432002_035_0046", [3, 4, 5, 6, 7, 8],
     "本体·2026 新增：综合单价所含因素①②③ / 措施项目 15 类列举与特殊环境措施费 / 其他项目清单"
     "内容 / 总承包服务费费率或总价计价 / 暂列金额暂估价按招标清单金额填报。", "full"),
    ("1A432000-B062", "工程招标投标与合同管理 > 计价风险",
     "1A432002_036_0047", [0, 1, 2],
     "本体·2026 计价风险承包人侧细则（③完成清单所有工作费用 / ⑤自身原因费用增加 / ②总价合同"
     "已标价清单缺陷之暂定数量例外）。E01 已锚风险总表(kc:...:0)，本 unit 只取 E01 未入池的细则句。", "full"),
    ("1A432000-B022", "工程招标投标与合同管理 > 合同选择与要求",
     "1A432002_036_0047", [3, 4, 5, 6, 7],
     "本体·2026 合同价款约定：合同类型三选一及成本加酬金适用 / 不得背离招标实质性内容 / 单价合同"
     "缺陷调整 vs 总价合同视为已含 / 成本加酬金暂定价按实调整。", "full"),
    ("1A432000-B043", "工程招标投标与合同管理 > 投标报价澄清或说明",
     "1A432002_036_0047", [8],
     "本体·2026 新增目：澄清时点（开标后至定标前）/ 算术误差修正但总价不得调整 / 合理性疑问与"
     "漏报未报澄清。", "full"),
    ("1A432000-B034", "工程招标投标与合同管理 > 工程量清单的应用规定",
     "1A432002_037_0048", [0, 1, 2],
     "本体·2026 应用规定：缺陷处置分流（总价补充完善不调 / 单价按标准调）/ 暂定工程量重新计量"
     "机制（单价合同暂定量 / 总价合同内暂定数量项目）。官方变点#57 定位块。", "full"),
    ("1A432000-B017", "工程招标投标与合同管理 > 合同争议处理",
     "1A432002_031_0041", [0],
     "支撑·合同价款争议解决三方式（评审/调解/仲裁或诉讼）。块级 unchanged，作组合案例支撑。", "support"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-root", type=Path, default=DEFAULT_BOOK_ROOT)
    args = ap.parse_args()

    fp = args.book_root / BOOK_FILE
    raw = fp.read_bytes()
    file_sha = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)

    blocks = {}
    for b in data["content_blocks"]:
        if b.get("chunk_id") in CHUNKS:
            sm = b.get("source_meta")
            sm = ast.literal_eval(sm) if isinstance(sm, str) else (sm or {})
            kc = b.get("knowledge_cards")
            kc = ast.literal_eval(kc) if isinstance(kc, str) else (kc or [])
            a = b.get("assessment")
            a = ast.literal_eval(a) if isinstance(a, str) else (a or {})
            blocks[b["chunk_id"]] = {
                "md": b["content_markdown"], "page": sm.get("page_num"),
                "cards": kc, "assessment": a,
            }
    missing = [c for c in CHUNKS if c not in blocks]
    if missing:
        raise SystemExit(f"FAIL: 教材块缺失 {missing}")

    # ── 闸：每条 cc quote 必须是块原文（归一化后子串），fail-closed ────────────
    for cid, pts in CC_POINTS.items():
        md_n = _norm(blocks[cid]["md"])
        for i, (_st, q) in enumerate(pts):
            if _norm(q) not in md_n:
                raise SystemExit(f"FAIL: cc:{cid}:{i} quote 非教材块原文子串")

    units = []
    for leaf, path, cid, idxs, note, tier in UNITS_PLAN:
        b = blocks[cid]
        sps = []
        for i in idxs:
            st, q = CC_POINTS[cid][i]
            sps.append({
                "statement": st,
                "required_terms": [cid],
                "point_id": f"cc:{cid}:{i}",
                "quote": q,
                "chunk": cid,
                "tier": tier,
                "textbook_source": {"chunk_id": cid, "kind": "content_markdown_verbatim"},
            })
        for ki in KC_TAKE.get(cid, []):
            if any(sp["point_id"] == f"kc:{cid}:{ki}" for u in units for sp in u["scoring_points"]):
                continue
            card = b["cards"][ki]
            sps.append({
                "statement": f"{card.get('card_title')}：{card.get('card_content')}",
                "required_terms": [cid],
                "point_id": f"kc:{cid}:{ki}",
                "quote": str(card.get("card_content")),
                "chunk": cid,
                "tier": "aux_llm_enhanced",
                "textbook_source": {"chunk_id": cid, "kind": "knowledge_card_llm_enhanced"},
            })
        if cid in CA_TAKE and not any(
                sp["point_id"] == f"ca:{cid}" for u in units for sp in u["scoring_points"]):
            aq = b["assessment"]
            sps.append({
                "statement": str(aq.get("generated_question")),
                "required_terms": [str(k) for k in (aq.get("grading_keywords") or [])],
                "point_id": f"ca:{cid}",
                "quote": f"{aq.get('generated_question')} | grading_keywords="
                         f"{','.join(str(k) for k in (aq.get('grading_keywords') or []))}",
                "chunk": cid,
                "tier": "aux_llm_enhanced",
                "textbook_source": {"chunk_id": cid, "kind": "assessment_llm_enhanced"},
            })
        units.append({
            "leaf_id": leaf,
            "leaf_name_path": path,
            "source_ref": {
                "chunk_id": cid,
                "file_sha256": file_sha,
                "page_num": b["page"],
                "record_id": f"2026教材/第二次加强/{BOOK_FILE}#chunk:{cid}",
                "source_lane": "textbook",
                "source_path": f"2026教材/第二次加强/{BOOK_FILE}",
                "span_hash": hashlib.sha256(b["md"].encode()).hexdigest(),
            },
            "note": note,
            "tier": tier,
            "scoring_points": sps,
        })

    n_pts = sum(len(u["scoring_points"]) for u in units)
    out = {
        "考点": "工程量清单与合同价款约定(2026·GB/T50500-2024 新规)",
        "keywords": ["措施项目清单", "其他项目清单", "总承包服务费", "暂列金额", "暂估价",
                      "成本加酬金", "投标报价澄清", "费率计价", "合同价款", "暂定工程量"],
        "命中单元": len(units),
        "去重采分点": n_pts,
        "注册表对齐状态": "pending_registry_slot(拟新增 slot 61·E06)·双签前不投产",
        "编译库覆盖说明": (
            "源=2026 教材结构化块（增强版v3.2）content_markdown 逐字原文（cc: 主锚，经归一化包含闸）"
            "+ knowledge_cards/assessment 增强辅助锚（kc:/ca:，非原文）。RichLeaf v3.2 基于旧教材，"
            "不含 GB/T50500-2024 整目变动内容，故本 pack 不走 RichLeaf 挖矿。"
            "官方依据：《2026 教材对比明细》变化#56–#64（P245–263 清单计价/合同价款整目变动）。"),
        "污染绕开chunk": [],
        "units": units,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT.name}: units={len(units)} scoring_points={n_pts} "
          f"(cc 原文闸全过, file_sha={file_sha[:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
