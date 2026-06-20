#!/usr/bin/env python3
"""真题锚确定性核验器 (机器闸 Layer-1 扩展, 凌驾AI裁判之上的ground-truth仲裁).

用法: python verify_exam_anchors.py <pack.md> "<主题关键词|管道分隔>"
读 pack 里的真题引用("20XX 第N题"/"20XX 案例X"), 直接去真考卷 JSON 核:
  (1) 该题号是否真存在 (chunks[].source_meta.original_anchor == 第N题)
  (2) 该题主题是否相关 (题干/选项/解析含主题关键词)
不存在 或 主题不相关 = 题号漂移嫌疑, 报🔴。这是确定性的, 不靠任何AI判断。
"""
import sys, re, json, glob, os

ROOT = "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor"
EXAM_GLOB = ROOT + "/docs/原始数据/2026_副本/题库/**/FINAL_CLEANED_EXAM_V{year}.json"

def load_exam(year):
    fs = glob.glob(EXAM_GLOB.format(year=year), recursive=True)
    if not fs: return None
    return json.load(open(fs[0], encoding="utf-8")), os.path.basename(fs[0])

def chunk_text(c):
    parts = [c.get("content_markdown", "")]
    for e in c.get("exercises", []):
        qd = e.get("question_data", {})
        parts.append(str(qd.get("stem", "")))
        for o in qd.get("options", []):
            parts.append(str(o.get("value", "")))
        parts.append(str(qd.get("analysis", "")))
    return " ".join(parts)

def main():
    pack = sys.argv[1]
    # 关键词优先级(真修法): argv[2]显式 > 源料json的keywords字段(按考点) > 建工广集兜底
    kw_str = sys.argv[2] if len(sys.argv) > 2 else None
    src_kw_used = False
    if not kw_str:
        m = re.match(r"([A-Z]\d+)", os.path.basename(pack))
        if m:
            d0 = os.path.dirname(pack)
            sp = glob.glob(os.path.join(d0, f"_{m.group(1)}*_compiled_source.json")) \
                or glob.glob(os.path.join(os.path.dirname(d0), f"_{m.group(1)}*_compiled_source.json"))
            if sp:
                try:
                    kw_str = json.load(open(sp[0], encoding="utf-8")).get("keywords")
                    src_kw_used = bool(kw_str)
                except Exception:
                    pass
    DEFAULT = (r"脚手架|模板|支架|扣件|连墙件|剪刀撑|危大|危险性较大|搭设|拆除|验收|检验批|分项|分部|主控项目|一般项目|隐蔽|实体检验|见证取样|"
        r"混凝土|大体积|水化热|温度裂缝|裂缝|养护|测温|水胶比|蜂窝|麻面|空鼓|露筋|质量通病|渗漏|防水|"
        r"起重|吊装|塔式起重机|塔吊|履带|汽车起重机|吊钩|钢丝绳|司索|吊索具|起重量|力矩限制器|群塔|缆风绳|钢结构|垂直运输|提升|"
        r"网络计划|双代号|关键线路|时差|工期|流水|索赔|不可抗力|进度款|计量|计价|合同|专家论证|高宽比|操作平台|安全等级|荷载|"
        r"砌体|砌筑|砌块|多孔砖|砖砌|马牙槎|灰缝|抹灰|饰面|瓷砖|石材|涂料|涂膜|卷材|屋面|保温|隔汽|女儿墙|地面|楼地面|墙面|龄期")
    kw = re.compile(kw_str if kw_str else DEFAULT)
    text = open(pack, encoding="utf-8").read()

    # 单选/多选: "20XX ... 第N题"
    singles = sorted(set(re.findall(r"(20\d\d)[^。\n]{0,6}第\s*(\d+)\s*题", text)))
    # 案例: "20XX ... 案例X"
    cases = sorted(set(re.findall(r"(20\d\d)[^。\n]{0,8}案例\s*([一二三四五六1-6])", text)))

    cache = {}
    def exam(y):
        if y not in cache: cache[y] = load_exam(y)
        return cache[y]

    rows, bad = [], 0
    for year, num in singles:
        e = exam(year)
        if not e:
            rows.append((f"{year} 第{num}题", "考卷缺失", "-", "🔴")); bad += 1; continue
        d, fn = e
        # 题号可能重名(单选第N题 + 多选第N题), 查全部, 任一主题相关即命中
        hits = [c for c in d["chunks"] if c.get("source_meta", {}).get("original_anchor", "") == f"第{num}题"]
        if not hits:
            rows.append((f"{year} 第{num}题", "题号不存在", fn, "🔴")); bad += 1; continue
        topic = any(kw.search(chunk_text(h)) for h in hits)
        rows.append((f"{year} 第{num}题", "存在·主题相关" if topic else "存在·主题不符", fn, "🟢" if topic else "🔴"))
        if not topic: bad += 1

    for year, cs in cases:
        e = exam(year)
        if not e:
            rows.append((f"{year} 案例{cs}", "考卷缺失", "-", "🔴")); bad += 1; continue
        d, fn = e
        # 案例题号难精确定位"第几问", 软核: 该年case_study里是否有主题相关案例
        casetexts = [chunk_text(c) for c in d["chunks"] if any(x.get("type") == "case_study" for x in c.get("exercises", []))]
        topic = any(kw.search(t) for t in casetexts)
        rows.append((f"{year} 案例{cs}", "该年案例含主题" if topic else "该年案例无主题", fn, "🟢" if topic else "🔴"))
        if not topic: bad += 1

    print(f"=== 真题锚确定性核验: {os.path.basename(pack)} ===")
    print(f"{'引用':<14}{'核查结果':<16}{'考卷文件':<42}判定")
    for c, r, fn, v in rows:
        print(f"{c:<14}{r:<16}{fn[:40]:<42}{v}")
    print("─" * 60)
    print(f"单选/多选锚 {len(singles)} 个, 案例锚 {len(cases)} 个; 题号漂移/不符/缺失 {bad} 个")
    print("裁决: " + ("❌ 有题号漂移, 需修" if bad else "✅ 真题锚全部确定性命中"))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
