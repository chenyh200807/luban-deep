#!/usr/bin/env python3
"""M0 引擎实测选型 bakeoff（plan §10 M0）。

用法：
  python scripts/run_photo_ocr_engine_bakeoff.py \
      --samples artifacts/photo_ocr_bakeoff/samples \
      --out artifacts/photo_ocr_bakeoff/run_$(date +%Y%m%d)

samples 目录结构（每个样本一对文件）：
  <name>.jpg            拍照图片
  <name>.gt.txt         人工转录真值（盲转录，见 annotation guideline）
  <name>.meta.json      可选：{"slice": "messy|clean|printed_mix|numeric|notebook", "pages": 1}

引擎与凭证（缺 key 的引擎显式跳过并入报告，绝不静默）：
  BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY      百度标准手写（L0 候选）
  DASHSCOPE_API_KEY                              qwen-vl-ocr（L1 候选）
  ALIBABA_CLOUD_ACCESS_KEY_ID / _SECRET          阿里 RecognizeHandwriting（L2 候选）
  TENCENT_SECRET_ID / TENCENT_SECRET_KEY         腾讯 HandwritingEssayOCR（对照，未实现客户端时跳过）

纪律（v3.2 G6 预注册）：跑数前必须先填写 out 目录下生成的
PREREGISTRATION.md 阈值表并由交付负责人确认；本脚本会在报告头部原样
引用该文件，阈值与结果同卷存档。
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import unicodedata
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.photo_answer.engines.base import EngineNotConfigured  # noqa: E402

PREREG_TEMPLATE = """# M0 Bakeoff Pre-registration（先定靶再射箭）

> 本文件必须在跑任何引擎之前填写并冻结（git commit）。
> 阈值来源：plan §3.4 / §9。空着 = 本次跑数无效。

- 冻结人（交付负责人）：__________
- 冻结时间：__________
- 样本配比（誊抄/限时自由作答/真实征集）：____ / ____ / ____

| 指标 | L0 达标阈值 | 备注 |
| --- | --- | --- |
| ① 盲转录 CER（全集） | ≤ ____% | |
| ① 盲转录 CER（messy 切片） | ≤ ____% | |
| ③ 未高亮错误漏检率 | ≤ ____% | 需确认页原型，首轮可标 N/A |
| ④ 关键数字错误率 | ≤ ____% | 工期/金额/编号 token 级 |
| ⑥ 确认后批改分差 ≤1 分占比 | ≥ ____% | 需批改链路，首轮可标 N/A |
| 体验参考：人均修改字符 | ≤ 6 字/题 | 非质量门 |
"""


def _norm(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text or "").split())


def cer(hypothesis: str, reference: str) -> float:
    """字符错误率 = 编辑距离 / 真值长度（NFKC 归一化、去空白）。"""
    h, r = _norm(hypothesis), _norm(reference)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i]
        for j, hc in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(r)


def numeric_token_error_rate(hypothesis: str, reference: str) -> float | None:
    import re

    nums_ref = re.findall(r"\d+(?:\.\d+)?", _norm(reference))
    if not nums_ref:
        return None
    nums_hyp = _norm(hypothesis)
    missed = sum(1 for n in nums_ref if n not in nums_hyp)
    return missed / len(nums_ref)


def _load_engines() -> dict[str, object]:
    engines: dict[str, object] = {}
    skipped: dict[str, str] = {}

    def _try(name: str, factory):
        try:
            engines[name] = factory()
        except EngineNotConfigured as exc:
            skipped[name] = str(exc)

    from deeptutor.services.photo_answer.engines.aliyun_handwriting import AliyunHandwritingEngine
    from deeptutor.services.photo_answer.engines.baidu_handwriting import BaiduHandwritingEngine
    from deeptutor.services.photo_answer.engines.qwen_vl_ocr import QwenVlOcrEngine

    _try("baidu_handwriting", BaiduHandwritingEngine.from_env)
    _try("qwen_vl_ocr", QwenVlOcrEngine.from_env)
    _try("aliyun_handwriting", AliyunHandwritingEngine.from_env)
    skipped.setdefault(
        "tencent_essay", "客户端未实现——若 M0 需要腾讯对照，先在 engines/ 补薄客户端"
    )
    engines["__skipped__"] = skipped  # type: ignore[assignment]
    return engines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个样本（冒烟用）")
    ap.add_argument("--sleep", type=float, default=0.15, help="请求间隔秒（敬畏 QPS）")
    args = ap.parse_args()

    samples_dir = Path(args.samples)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    prereg = out_dir / "PREREGISTRATION.md"
    if not prereg.exists():
        prereg.write_text(PREREG_TEMPLATE, encoding="utf-8")
        print(f"[BLOCKED] 已生成 {prereg}")
        print("先填写并冻结阈值（commit），再重新运行本脚本。先定靶再射箭。")
        return
    prereg_text = prereg.read_text(encoding="utf-8")
    if "____" in prereg_text.split("|")[0] or "冻结人（交付负责人）：__________" in prereg_text:
        print(f"[BLOCKED] {prereg} 阈值未填写/未冻结。先定靶再射箭。")
        return

    images = sorted(samples_dir.glob("*.jpg")) + sorted(samples_dir.glob("*.jpeg"))
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"[BLOCKED] {samples_dir} 没有样本图片")
        return

    engines = _load_engines()
    skipped = engines.pop("__skipped__")

    rows: list[dict] = []
    for img_path in images:
        gt_path = img_path.with_suffix("").with_suffix(".gt.txt")
        if not gt_path.exists():
            gt_path = Path(str(img_path).rsplit(".", 1)[0] + ".gt.txt")
        if not gt_path.exists():
            print(f"[skip] {img_path.name}: 缺真值 .gt.txt")
            continue
        reference = gt_path.read_text(encoding="utf-8")
        meta_path = Path(str(img_path).rsplit(".", 1)[0] + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        image_bytes = img_path.read_bytes()
        for name, engine in engines.items():
            t0 = time.time()
            try:
                result = engine.recognize(image_bytes)  # type: ignore[attr-defined]
                elapsed = time.time() - t0
                row = {
                    "sample": img_path.name,
                    "slice": meta.get("slice", "unknown"),
                    "engine": name,
                    "cer": round(cer(result.raw_text, reference), 4),
                    "numeric_err": numeric_token_error_rate(result.raw_text, reference),
                    "latency_s": round(elapsed, 2),
                    "cost_micros": result.cost_micros,
                    "provider_usage_id": result.provider_usage_id,
                    "hyp_chars": len(_norm(result.raw_text)),
                    "ref_chars": len(_norm(reference)),
                }
            except Exception as exc:  # noqa: BLE001 — 评测脚本如实记录每类失败
                row = {
                    "sample": img_path.name,
                    "slice": meta.get("slice", "unknown"),
                    "engine": name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))
            time.sleep(args.sleep)

    (out_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8"
    )

    # 汇总
    lines = ["# M0 Bakeoff FINDING", "", "## Pre-registration（原样引用）", "", prereg_text, "", "## 跳过的引擎", ""]
    for name, reason in skipped.items():
        lines.append(f"- `{name}`: {reason}")
    lines += ["", "## 引擎对照（全集）", "", "| 引擎 | 样本数 | CER 均值 | CER P90 | 数字错误率均值 | 时延 P50(s) | 单页成本(micros) | 失败数 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    by_engine: dict[str, list[dict]] = {}
    for r in rows:
        by_engine.setdefault(r["engine"], []).append(r)
    for name, items in sorted(by_engine.items()):
        ok = [r for r in items if "cer" in r]
        errs = [r for r in items if "error" in r]
        if ok:
            cers = sorted(r["cer"] for r in ok)
            nums = [r["numeric_err"] for r in ok if r.get("numeric_err") is not None]
            lats = sorted(r["latency_s"] for r in ok)
            costs = [r["cost_micros"] for r in ok]
            lines.append(
                f"| {name} | {len(ok)} | {statistics.mean(cers):.4f} | "
                f"{cers[min(len(cers)-1, int(0.9*len(cers)))]:.4f} | "
                f"{(statistics.mean(nums) if nums else float('nan')):.4f} | "
                f"{lats[len(lats)//2]:.2f} | {int(statistics.mean(costs))} | {len(errs)} |"
            )
        else:
            lines.append(f"| {name} | 0 | - | - | - | - | - | {len(errs)} |")
    lines += [
        "",
        "## 分切片 CER",
        "",
        "| 切片 | " + " | ".join(sorted(by_engine)) + " |",
        "| --- | " + " | ".join("---" for _ in by_engine) + " |",
    ]
    slices = sorted({r["slice"] for r in rows})
    for sl in slices:
        cells = []
        for name in sorted(by_engine):
            vals = [r["cer"] for r in by_engine[name] if r.get("slice") == sl and "cer" in r]
            cells.append(f"{statistics.mean(vals):.4f}" if vals else "-")
        lines.append(f"| {sl} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 裁决（人工填写）",
        "",
        "- [ ] L0 裁决：____（依据预注册阈值逐项核对）",
        "- [ ] 标记 `provisional`（上线 30 天真实数据回归前不转正）",
        "- [ ] 若触发换防条款（百度不达标→阿里→超预算）：停止，回用户重批预算",
    ]
    (out_dir / "FINDING_photo_ocr_bakeoff.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告：{out_dir / 'FINDING_photo_ocr_bakeoff.md'}")


if __name__ == "__main__":
    main()
