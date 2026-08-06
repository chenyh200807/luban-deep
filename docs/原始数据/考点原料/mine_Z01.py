#!/usr/bin/env python3
"""Z01 挖矿（确定性）：智能建造/智能施工/建筑机器人（2026 新增《智能建造技术导则（试行）》）。

与 mine_E06.py 同族（2026 新增点管线）：源 = 2026 教材结构化块
`FINAL_CLEANED_BOOK2026-167-221v3_fixed.json` 块 `1A422000_052_0078` / `053_0079` /
`054_0080`（粗清单块级三档全部 likely_new；官方《2026 教材对比明细》标注新增
《智能建造技术导则（试行）》（建办市〔2025〕14号））。

namespace / 闸与 mine_E06.py 完全一致：cc:=逐字原文（归一化包含闸 fail-closed）、
kc:/ca:=LLM 增强辅助锚（非原文）。

用法::

    python3 docs/原始数据/考点原料/mine_Z01.py [--book-root <dir>]
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
OUT = HERE / "_Z01_compiled_source.json"

BOOK_FILE = "FINAL_CLEANED_BOOK2026-167-221v3_fixed.json"

CHUNKS = ["1A422000_052_0078", "1A422000_053_0079", "1A422000_054_0080"]

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub("", s or "")


CC_POINTS: dict[str, list[tuple[str, str]]] = {
    "1A422000_052_0078": [
        ("导则通用要求：以「提品质、降成本」为目标，集成数字勘察/数字设计/智能生产/智能施工/智慧运维五阶段关键技术",
         "（1）以“提品质、降成本”为目标，因地制宜集成应用数字勘察、数字设计、智能生产、智能施工、智慧运维等各阶段的关键技术产品，实现高效益、高质量、低消耗、低排放的建造过程，提升建筑业工业化、数字化、绿色化水平。"),
        ("通用要求：智能建造装备促进「危、繁、脏、重」场景人机协同作业",
         "（3）采用建筑机器人、智能顶升集成建造平台、智能施工电梯、三维激光扫描等智能建造装备，促进“危、繁、脏、重”等场景下的人机协同作业，提高工程建设工业化、智能化水平。"),
        ("数字勘察：数字技术贯穿勘察数据采集/成果形成/质量控制/成果应用/服务扩展全过程",
         "采用数字技术进行工程勘察的数据采集、成果形成、质量控制、成果应用和服务扩展，实现工程勘察全过程数据的快速准确采集、高效共享和贯通应用。"),
        ("智能生产关键工艺环节：钢筋制作安装/模具安拆/混凝土浇筑/钢构件制作/装配式围护与一体化装修/机电装配式单元加工，建设智能生产线",
         "（1）在钢筋制作安装、模具安拆、混凝土浇筑、钢构件制作、装配式围护体系和一体化装修、机电装配式单元加工等工厂生产关键工艺环节中，推进建筑部品部件生产工艺流程数字化和建筑机器人的应用，建设建筑部品部件智能生产线，实现生产数据贯通化、制造柔性化和管理智能化。"),
        ("智能生产：以标准部品部件为基础的专业化、模块化、数字化生产体系（型钢构件/预制墙板/叠合楼板/预制楼梯/装修墙板/机电支吊架/机电装配式单元）",
         "（2）建立以标准部品部件为基础的专业化、模块化、数字化生产体系，实现型钢构件、预制混凝土墙板、叠合楼板、预制楼梯、装修墙板、机电支吊架、机电装配式单元等通用建筑部品部件的工厂化、数字化、智能化生产，满足标准化设计选型要求。"),
    ],
    "1A422000_053_0079": [
        ("智能施工总则：编制智能施工专项实施方案→过程跟踪指导→完成后效果评估；「危繁脏重」环节推行人机协同",
         "编制智能施工专项实施方案，明确主要工序环节中对智能建造技术和装备的应用计划，依据方案对施工过程进行跟踪指导，并在施工完成后对方案实施效果进行评估。在“危、繁、脏、重”施工环节推行人机协同施工作业，大力推广应用技术成熟度高、实施效益明显的智能建造装备及建筑机器人。"),
        ("数据驱动施工管理：BIM 施工组织方案模拟分析优化（总平面布置规划/工序模拟优化/进度模拟与资源配置优化/专项方案比选）",
         "② 采用 BIM 技术进行施工组织方案模拟分析和优化，包括施工总平面布置规划、施工工序模拟和优化、施工进度模拟和资源配置优化、专项施工方案比选等，实现施工现场的合理布局以及施工工序的顺畅衔接。"),
        ("数据驱动施工管理：复杂结构施工精度模拟与虚拟预拼装（数据模型/三维扫描/图像识别/雷达成像）",
         "③ 综合运用数据模型、三维扫描、图像识别、雷达成像等技术对复杂结构进行施工精度模拟和虚拟预拼装，与数据模型进行拟合匹配，获得目标控制值，指导施工。"),
        ("地基基础智能施工：机器人辅助测量放线/桩基施工/土方开挖/钢筋加工",
         "① 采用智能建造装备及建筑机器人进行辅助施工作业，包括测量放线、桩基施工、土方开挖、钢筋加工等，提升施工质量、效率、安全性。"),
        ("主体结构智能施工：机器人辅助测量放样/构件吊装/钢筋绑扎/混凝土布料/收面/自动灌浆/钢结构/砌体/木结构/木模板加工安装",
         "① 采用智能建造装备及建筑机器人辅助施工作业，包括测量放样、构件吊装、钢筋绑扎、混凝土布料、混凝土收面、自动灌浆、钢结构施工、砌体结构施工、木结构施工、木模板加工及安装等环节，提升施工质量、效率、安全性。"),
        ("主体结构：智能顶升集成建造平台集成智能塔吊/智能施工电梯/智能运输车/悬挂式布料机/水平运输设备/隔音降噪装置/物联感知与通信设备/建筑机器人/设备控制与监测平台，实现钢筋绑扎、模架顶升、模板安装、混凝土浇筑养护协同作业",
         "② 采用智能顶升集成建造平台，集成智能塔吊、智能施工电梯、智能运输车、悬挂式布料机、水平运输设备、隔音降噪装置、物联感知与通信设备、建筑机器人、设备控制与监测平台等施工装备，进行主体结构施工，实现钢筋绑扎、模架顶升、模板安装、混凝土浇筑和养护以及其他辅助工序协同作业。"),
        ("主体结构：智能化灌浆装备对预制构件灌浆套筒连接，灌浆质量自动检测",
         "③ 采用智能化灌浆装备及管理平台，对预制构件的灌浆套筒进行连接，实现灌浆质量的自动检测。"),
        ("主体结构：砌体施工用 BIM 获取二次结构（砌块/圈梁/构造柱/导墙/顶砖/门窗洞口及过梁）空间位置信息并排布检查优化",
         "⑤ 对砌体结构施工，采用 BIM 技术获取砌块、圈梁、构造柱、导墙、顶砖、门窗洞口及过梁等二次结构的空间位置信息，并进行排布检查和优化，减少返工，缩短工期。"),
        ("围护结构：实测实量机器人等智能检测工具检测围护结构实体质量，自动化数据收集分析及安全风险预警",
         "② 采用实测实量机器人等智能检测工具对围护结构工程实体质量进行检测，实现自动化数据收集、分析及安全风险预警。"),
        ("装饰装修：装配式装修部品集成技术（集成卫浴/集成厨房/架空楼面/隔墙和墙面/集成吊顶/设备和管线系统）",
         "② 采用装配式装修部品集成技术，主要包括集成卫浴系统、集成厨房系统、架空楼面系统、隔墙和墙面系统、集成吊顶系统、设备和管线系统等。"),
        ("装饰装修：机器人辅助测量放样/抹灰/铺贴/地坪打磨/地坪喷漆/腻子涂敷/乳胶漆喷涂",
         "③ 采用建筑机器人辅助施工作业，包括测量放样、抹灰、铺贴、地坪打磨、地坪喷漆、腻子涂敷、乳胶漆喷涂等。"),
    ],
    "1A422000_054_0080": [
        ("装备应用统筹：综合技术适用性、成本投入、效益产出，明确应用需求及进场计划",
         "① 统筹智能建造装备及建筑机器人在施工全过程中的应用，综合考虑各类智能建造装备及建筑机器人的技术适用性、成本投入、效益产出等因素，明确应用需求及进场计划。"),
        ("BIM 模型作为装备/机器人协同作业、路径规划、导航及调度的基础",
         "② 采用 BIM 模型作为智能建造装备及建筑机器人协同作业、路径规划、导航及调度的基础，提升自动化水平。"),
        ("无人机：航拍自动化测算场地平整/基坑开挖/填筑土方量，定期生成三维实景模型展示进度",
         "③ 采用无人机进行航拍，对场地平整、基坑开挖及填筑土方量进行自动化测量计算，定期生成不同时间段施工现场三维实景模型，直观展示施工现场进度。"),
        ("手持式智能钢筋捆扎机：辅助人工钢筋捆扎作业",
         "④ 采用手持式智能钢筋捆扎机，辅助人工进行钢筋捆扎作业。"),
        ("搬运机器人：物料自动化运输，与智能升降机数据联网（自动导航/栈板叉取/障碍物识别），垂直+水平运输联动",
         "⑤ 采用搬运机器人进行物料自动化运输作业，通过与智能升降机的数据联网，进行自动导航、栈板叉取、障碍物识别，实现垂直运输和水平运输的高效联动。"),
        ("喷涂机器人：外立面墙漆喷涂，路径自动规划，底漆/中涂/面漆/罩光漆自动喷涂",
         "⑥ 采用喷涂机器人进行建筑外立面墙漆喷涂施工，实现作业路径自动规划以及底漆、中涂、面漆、罩光漆自动喷涂。"),
        ("施工数据交付：数字化交付方案，内容=模型（建筑/结构/机电/装饰/幕墙）+图纸+工程量清单+工程所处环境信息，明确数据要求/职责权限/交付计划",
         "制定数字化交付方案，交付内容包括模型（建筑、结构、机电、装饰、幕墙等）、图纸、工程量清单、工程所处环境信息，明确数字化交付的数据要求、职责权限、交付计划。"),
        ("智慧运维：平台自动采集人员/设备/能耗数据，提供人员管理/设备监控/能耗监测，用于结构健康监测/功能运行维护/安全风险应急管理，实现数据承载/风险感知/辅助决策/末端设备自动控制",
         "建立智慧运维平台，自动采集项目人员、设备、能耗等关键要素数据，提供人员管理、设备监控、能耗监测等管理能力，用于建筑结构健康监测、建筑功能运行维护、安全风险应急管理等，实现数据承载、风险感知、辅助决策和末端设备的自动控制。"),
    ],
}

KC_TAKE: dict[str, list[int]] = {
    "1A422000_053_0079": [0],  # 智能施工五大领域(分类卡)
    "1A422000_054_0080": [1],  # 施工数据交付内容(记忆卡)
}
CA_TAKE = ["1A422000_053_0079", "1A422000_054_0080"]

UNITS_PLAN = [
    ("1A422000-B098", "相关标准 > 智能建造技术导则 > 智能施工",
     "1A422000_053_0079", list(range(11)),
     "本体·智能施工：专项实施方案生命周期（编制→跟踪指导→效果评估）+ 五大领域"
     "（数据驱动施工管理/地基基础/主体结构/围护结构/装饰装修）各自的装备与技术清单。"
     "官方标注 2026 新增《智能建造技术导则（试行）》；块级 likely_new。", "full"),
    ("1A422000-B097", "相关标准 > 智能建造技术导则 > 智能建造装备及建筑机器人应用",
     "1A422000_054_0080", list(range(8)),
     "本体·装备与机器人应用统筹 + 专用装备场景（无人机/钢筋捆扎机/搬运机器人/喷涂"
     "机器人）+ 施工数据交付 + 智慧运维。块级 likely_new。", "full"),
    ("1A422000-B099", "相关标准 > 智能建造技术导则 > 通用要求与智能生产",
     "1A422000_052_0078", list(range(5)),
     "本体·导则通用要求（提品质降成本目标/五阶段关键技术/危繁脏重人机协同）+ 数字"
     "勘察 + 智能生产（关键工艺环节/标准部品部件生产体系）。块级 likely_new。", "full"),
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
        if cid in CA_TAKE:
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
        "考点": "智能建造/智能施工/建筑机器人（2026 新增《智能建造技术导则（试行）》）",
        "keywords": ["智能建造", "智能施工", "建筑机器人", "智能顶升集成建造平台", "无人机",
                      "喷涂机器人", "搬运机器人", "智慧运维", "数字化交付", "智能生产",
                      "数字勘察", "数字设计"],
        "命中单元": len(units),
        "去重采分点": n_pts,
        "注册表对齐状态": "pending_registry_slot(拟新增 slot 62·Z01)·双签前不投产",
        "编译库覆盖说明": (
            "源=2026 教材结构化块（增强版v3.2）content_markdown 逐字原文（cc: 主锚，经归一化包含闸）"
            "+ knowledge_cards/assessment 增强辅助锚（kc:/ca:，非原文）。《智能建造技术导则（试行）》"
            "（建办市〔2025〕14号）为 2026 教材新增内容，RichLeaf v3.2 编译库无覆盖。"
            "官方依据：《2026 教材对比明细》标注新增智能建造技术导则；粗清单块级 likely_new"
            "（1A422000_052_0078/053_0079/054_0080），句级新增点 #1/#2/#3/#4/#6/#7/#8/#12/"
            "#13/#15/#17/#18/#19/#22/#23/#24/#25/#33。"),
        "污染绕开chunk": [],
        "units": units,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {OUT.name}: units={len(units)} scoring_points={n_pts} "
          f"(cc 原文闸全过, file_sha={file_sha[:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
