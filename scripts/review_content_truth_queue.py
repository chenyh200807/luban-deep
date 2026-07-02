#!/usr/bin/env python3
"""② content-truth review loop — L3 离线评审 agent(owner 三层最后一层).

runtime 已**永远输出 + 大方 hedge + flag**(L1/L2)：核不到本轮 standard 召回的规范编号被记进
单一事件 sink ``TurnEventLog``。本脚本**离线**(不在请求路径)把这些低置信 claim 用 authority-ladder
仲裁(教材原文 > 异源 DeepSeek)判 accurate/fabricated/uncertain，攒成 **PII-safe** 纠错数据集
喂内容升级(产品飞轮燃料)。

owner 原则：信当下 LLM 能力(输出端不抑制)，准确性靠这条后台 review loop 收敛。评审 agent
**不是 runtime 门**、不新增 runtime decider；真值仍归教材原文(memory authority-ladder)，
DeepSeek 只是异源信号(memory cross-model-judge-catches-fabrication)。

用法：
  # eval-design #5 度量自检(确定性，无网络)：已知真编号必 accurate、已知编造必 fabricated
  python3 scripts/review_content_truth_queue.py --self-test

  # 真实运行：从 TurnEventLog 建队列 → 教材+异源仲裁 → 写纠错数据集
  python3 scripts/review_content_truth_queue.py --days 7 \
      --textbook-dir docs/原始数据/2026_副本/讲义 --models deepseek \
      --out artifacts/content_truth_corrections_YYYY-MM-DD.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from deeptutor.services.observability.content_truth_review_queue import (  # noqa: E402
    apply_review_verdicts,
    build_content_truth_review_queue,
    combine_authority_ladder_verdict,
)
from deeptutor.tutorbot.teaching_modes import _normalize_standard_code  # noqa: E402


# ── 教材原文仲裁(最高权威)：python alltext 核，不 grep(memory) ──────────────────────
def _iter_text(node) -> str:
    """递归把任意 JSON 节点的字符串值拼成 alltext(memory：搜讲义用 alltext 不 grep)。"""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return " ".join(_iter_text(v) for v in node.values())
    if isinstance(node, list):
        return " ".join(_iter_text(v) for v in node)
    return ""


def load_textbook_alltext(textbook_dir: Path | None) -> str | None:
    """把 *_v8 讲义语料拼成单一 alltext。语料不可用 → None(标 textbook_searched=False)。"""
    if textbook_dir is None or not Path(textbook_dir).exists():
        return None
    parts: list[str] = []
    for path in sorted(Path(textbook_dir).rglob("*_v8*.json")):
        try:
            parts.append(_iter_text(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    if not parts:
        return None
    return _normalize_standard_code(" ".join(parts))


def textbook_present(code: str, textbook_alltext: str | None) -> tuple[bool, bool]:
    """(searched, present)：教材 alltext 里是否字面出现该归一化编号。"""
    if textbook_alltext is None:
        return (False, False)
    return (True, _normalize_standard_code(code) in textbook_alltext)


# ── 异源信号：DeepSeek 判编号真伪(复用 m35 调用层，不造第二套基础设施) ──────────────
_DS_PROMPT = (
    "你是中国工程建设标准规范专家。判断下面这个标准编号(含年份版本)是否为**真实存在**的国家/行业"
    "标准。只看编号与年份是否真实存在，不评价内容。严格只回 JSON："
    '{{"verdict":"real|fabricated|uncertain","reason":"≤30字"}}\n\n标准编号：{code}'
)


def deepseek_verdict(code: str, *, api_key: str, base_url: str, model: str) -> str | None:
    """返回 'real' / 'fabricated' / 'uncertain' / None(传输失败)。异源信号，非金标。"""
    from m35_gold_judges import _http_post_json  # noqa: E402

    try:
        body = _http_post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            {
                "model": model,
                "messages": [{"role": "user", "content": _DS_PROMPT.format(code=code)}],
                "temperature": 0.0,
                "max_tokens": 200,
                "stream": False,
            },
            90.0,
        )
    except Exception:
        return None
    choices = body.get("choices") or []
    if not (choices and isinstance(choices[0], dict)):
        return None
    text = (choices[0].get("message") or {}).get("content") or ""
    import re

    match = re.search(r'"verdict"\s*:\s*"(real|fabricated|uncertain)"', text)
    return match.group(1) if match else "uncertain"


def _cross_model_to_ladder(ds: str | None) -> str | None:
    """DeepSeek 'real'→不判死(None 让 ladder 走 uncertain)；'fabricated'→ 传 fabricated。"""
    if ds == "fabricated":
        return "fabricated"
    return None  # real / uncertain / 失败 → 不参与判死，由 ladder 归 uncertain


# ── eval-design #5 度量自检(确定性，无网络) ─────────────────────────────────────────
def run_self_test() -> int:
    """已知真编号必不被冤判 fabricated；已知编造必被判 fabricated。失败 → exit 2。"""
    # 教材 stub：收录真编号 GB50016-2014，不收录编造的 -2019/JGJ999-2099。
    stub = _normalize_standard_code("现行《建筑设计防火规范》GB 50016-2014 ...")
    cases = [
        # (code, deepseek_signal, expect)
        ("GB50016-2014", "real", "accurate"),       # 教材有 → accurate(压过任何异源)
        ("GB50016-2019", "fabricated", "fabricated"),  # 教材无 + 异源判死 → fabricated
        ("JGJ999-2099", "fabricated", "fabricated"),   # 同上
        ("GB55037-2022", "real", "uncertain"),      # 教材未收录但异源没判死 → uncertain(不冤判)
    ]
    failures = []
    for code, ds, expect in cases:
        searched, present = textbook_present(code, stub)
        verdict = combine_authority_ladder_verdict(
            textbook_present=present,
            textbook_searched=searched,
            cross_model_verdict=_cross_model_to_ladder(ds),
        )
        ok = verdict == expect
        print(f"  [{'PASS' if ok else 'FAIL'}] {code}: got={verdict} expect={expect}")
        if not ok:
            failures.append(code)
    if failures:
        print(f"SELF-TEST FAILED: {failures}", file=sys.stderr)
        return 2
    print("SELF-TEST PASSED: clean passes & fabricated caught (eval-design #5)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="content-truth 离线评审纠错")
    ap.add_argument("--self-test", action="store_true", help="确定性度量自检(无网络)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--textbook-dir", default="docs/原始数据/2026_副本/讲义")
    ap.add_argument("--models", default="deepseek")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.self_test:
        return run_self_test()

    queue = build_content_truth_review_queue(days=args.days, limit=args.limit)
    print(f"queue_size={queue['queue_size']} (window {args.days}d)")

    textbook_alltext = load_textbook_alltext(Path(args.textbook_dir))
    if textbook_alltext is None:
        print(f"⚠️ textbook corpus 不可用({args.textbook_dir})→ 教材 searched=False，多归 uncertain")

    use_deepseek = "deepseek" in args.models
    api_key = base_url = model = ""
    if use_deepseek:
        from m35_gold_judges import DEEPSEEK_DEFAULT_BASE_URL, load_dotenv_file  # noqa: E402

        env = load_dotenv_file(REPO / ".env")
        api_key = env.get("DEEPSEEK_API_KEY", "")
        base_url = DEEPSEEK_DEFAULT_BASE_URL
        model = "deepseek-v4-pro"
        use_deepseek = bool(api_key)
        if not api_key:
            print("⚠️ 无 DEEPSEEK_API_KEY → 异源信号缺，多归 uncertain")

    verdicts: dict[str, dict] = {}
    for item in queue["items"]:
        code = item["claim"]
        searched, present = textbook_present(code, textbook_alltext)
        ds = deepseek_verdict(code, api_key=api_key, base_url=base_url, model=model) if use_deepseek else None
        verdict = combine_authority_ladder_verdict(
            textbook_present=present,
            textbook_searched=searched,
            cross_model_verdict=_cross_model_to_ladder(ds),
        )
        authority = "+".join(
            filter(None, ["textbook" if searched else "", "deepseek" if use_deepseek else ""])
        )
        verdicts[code] = {
            "verdict": verdict,
            "authority": authority,
            "citation": "讲义alltext命中" if present else "",
        }
        print(f"  {code}: textbook={'Y' if present else ('?' if not searched else 'N')} "
              f"deepseek={ds or '-'} → {verdict}")

    dataset = apply_review_verdicts(queue, verdicts)
    dataset["run_manifest"] = {
        **queue["run_manifest"],
        "reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models": args.models,
        "textbook_searched": textbook_alltext is not None,
    }
    print(f"corrections: size={dataset['dataset_size']} counts={dataset['verdict_counts']}")

    out_path = args.out or f"artifacts/content_truth_corrections_{time.strftime('%Y-%m-%d')}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out_path} (PII-safe 纠错数据集)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
