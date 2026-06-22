#!/usr/bin/env python3
"""鲁班案例题作答层 · 异源多模型对抗审 (anti-self-congratulation gate).

前 3 批作答层样板全是 Opus subagent 造 + Opus subagent 自检 = 同源盲点 + 满意度虚高
(memory: cross-model-judge-catches-fabrication-same-source-misses)。本脚本复用
``scripts/m35_gold_judges.py`` 的多模型调用层 (DeepSeek/Qwen HTTP + Codex CLI),
让 **异源** 模型对抗审 Opus 造的作答层 —— 审机器闸 (verify_pack.py) 之外的语义质量。

只读: 读作答层 md + signed 源料, 调模型, 写审计报告。不改作答层、不判分 (作答层
``official_score_allowed=false`` 不变)。模型只产 findings, 真值仍归 signed R5 / 判分内核。

用法:
  python3 scripts/run_luban_answer_layer_cross_model_audit.py --pack-id K01 \
      --models deepseek,qwen,codex [--out artifacts/...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

# 复用 m35_gold_judges 的多模型调用层 (不造第二套调用基础设施)
from m35_gold_judges import (  # noqa: E402
    DASHSCOPE_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_BASE_URL,
    QWEN_MODEL,
    JudgeTransportError,
    _http_post_json,
    _run_cli,
    load_dotenv_file,
    parse_codex_jsonl,
)

# 质量门用顶尖模型 (生产用 v4-flash, 审计用 v4-pro; Qwen/Codex 同 m35)
DEEPSEEK_AUDIT_MODEL = "deepseek-v4-pro"
CODEX_AUDIT_TIMEOUT = 240.0  # codex exec 审 ~20K 字 prompt, 60s 不够


def _codex_audit(prompt: str) -> str | None:
    """codex exec read-only, 大 timeout (m35 的 _codex_call 写死 60s 不够)。"""
    rc, out, err = _run_cli(
        ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "--json", prompt],
        CODEX_AUDIT_TIMEOUT,
    )
    if rc != 0:
        raise JudgeTransportError(f"codex_exit_{rc}: {err[:150]}")
    text, _ = parse_codex_jsonl(out)
    return text


def _big_chat(url: str, api_key: str, model: str, prompt: str) -> str | None:
    """复用 m35 的 _http_post_json, 但放大 max_tokens (判分版写死 400, 审作答层不够)。"""
    body = _http_post_json(
        f"{url.rstrip('/')}/chat/completions",
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 8000,
            "stream": False,
        },
        AUDIT_TIMEOUT,
    )
    choices = body.get("choices") or []
    if choices and isinstance(choices[0], dict):
        return (choices[0].get("message") or {}).get("content")
    return None

KAOYUAN = REPO / "docs/原始数据/考点原料"
AUDIT_TIMEOUT = 120.0  # 语义审比逐点判分长, 放宽

AUDIT_CHECKLIST = """\
你是一建建筑实务命题/阅卷资深专家, 同时是**对抗审查者**。下面是另一个 AI(Opus) 造的"案例题作答层样板"。
你的任务是**找问题, 不是确认**——它由同源模型自检过且自报"红线全守", 你要抓它同源盲点漏掉的。

逐条审 (机器已确定性核过 point_id 存在性/error_code 注册/真题锚年份, 你**不用**重复核这些, 专审语义):
1. 采分点可写化是否忠实: "标准表达""必写关键词"有没有篡改/夸大/偏离 signed R5 原意(R5 原文见下)。
2. 必写关键词的"必写性": 标为必写的词, 缺了真的不得分吗? 有没有把"非必写"误标必写(会误导学生)?
3. 标准表达的事实正确性: 有没有事实错误、过期表述、规范条款张冠李戴?
4. 易错表达→error_code 映射贴不贴切: 映射的 E/M 码对应这个错因吗?
5. 版本状态判断: "新规范优先/旧说法仅背景"标得对吗? 有没有该标新规范却按旧的写?
6. 句式套用是否得当: 套的句式(判断纠错/措施六维/计算判定链等)对这道题对吗? 有没有硬套或该用没用?
7. 整体: 有没有编造、夸大、自嗨式"看起来全面其实漏关键采分点"的问题?

**只输出一个 JSON** (不要别的文字), 形如:
{"verdict":"pass|concerns|fail",
 "findings":[{"severity":"high|medium|low","axis":"1-7的哪条","problem":"具体问题(60字内)","evidence":"原文片段(40字内)"}],
 "summary":"一句话总评"}
没问题就 findings 空数组、verdict=pass。发现 high 即 verdict=fail。"""


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _r5_points(src_path: Path, answer_md: str) -> str:
    """signed R5 采分点 (供异源核'采分点逐字/必写性')。

    **只喂作答层实际引用的 point_id 对应的采分点** —— compiled_source 是挖矿中间产物,
    一个文件可能杂糅多考点 (考点字段对、units 混入无关考点); 喂全集会让异源误判"考点不符"。
    作答层是否忠实, 应对照它**引用的那些** point_id 的真实 statement/quote。
    """
    if not src_path.exists():
        return "(无 compiled_source; 该考点真值以 pack 正文 R5 为准)"
    d = json.loads(src_path.read_text(encoding="utf-8"))
    # 作答层引用的 point_id (含/不含尾 :idx)
    cited = set(re.findall(r"(?:ca|kc|m35):[0-9A-Za-z_\-一-鿿]+(?::[0-9A-Za-z]+)?", answer_md))
    cited_base = {p.rsplit(":", 1)[0] if re.search(r":[0-9A-Za-z]+$", p) and p.count(":") >= 2 else p
                  for p in cited}
    want = cited | cited_base
    lines = []
    for u in d.get("units", []):
        for sp in u.get("scoring_points", []):
            pid = sp.get("point_id", "")
            if pid in want or pid.rsplit(":", 1)[0] in want:
                lines.append(
                    f"- [{pid}] {sp.get('statement','')} "
                    f"| 必含词:{sp.get('required_terms') or []} | quote:{(sp.get('quote') or '')[:90]}"
                )
    if not lines:
        return "(作答层引用的 point_id 在 compiled_source 未匹配到; 真值以 pack 正文 R5 为准)"
    return f"作答层引用了 {len(lines)} 个 point_id, 其 signed 真值如下(作答层须忠实于这些):\n" + "\n".join(lines)


def build_audit_prompt(pack_id: str, answer_md: str, r5: str, exam_years: list[str]) -> str:
    return (
        f"{AUDIT_CHECKLIST}\n\n"
        f"=== 考点 {pack_id} 的 signed R5 采分点(真值, 作答层必须忠实派生) ===\n{r5}\n\n"
        f"=== 该考点证据包真题年份(真题锚只能用这些) ===\n{exam_years}\n\n"
        f"=== 待审作答层样板 ===\n{answer_md}\n\n"
        f"现在输出你的对抗审查 JSON:"
    )


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```json\s*(.+?)\s*```", text, re.DOTALL) or re.search(
        r"(\{.*\})", text, re.DOTALL
    )
    raw = m.group(1) if m else text
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def call_model(model: str, prompt: str, env: dict[str, str]) -> dict:
    """复用 m35 调用层。返回 {model, ok, verdict, findings, raw, error}。"""
    try:
        if model == "deepseek":
            text = _big_chat(DEEPSEEK_DEFAULT_BASE_URL, env.get("DEEPSEEK_API_KEY", ""), DEEPSEEK_AUDIT_MODEL, prompt)
        elif model == "qwen":
            text = _big_chat(DASHSCOPE_DEFAULT_BASE_URL, env.get("DASHSCOPE_API_KEY", ""), QWEN_MODEL, prompt)
        elif model == "codex":
            text = _codex_audit(prompt)
        else:
            return {"model": model, "ok": False, "error": f"unknown model {model}"}
    except JudgeTransportError as exc:
        return {"model": model, "ok": False, "error": str(exc)}
    parsed = _parse_json(text or "")
    if parsed is None:
        return {"model": model, "ok": False, "error": "unparseable", "raw": (text or "")[:500]}
    return {
        "model": model,
        "ok": True,
        "verdict": parsed.get("verdict"),
        "findings": parsed.get("findings") or [],
        "summary": parsed.get("summary", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-id", required=True)
    ap.add_argument("--models", default="deepseek,qwen,codex")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    pid = args.pack_id
    answer_md = _load(next(iter(KAOYUAN.glob(f"成品/{pid}_*作答层样板.md")), Path("/nonexistent")))
    if not answer_md:
        print(f"[ERR] 找不到 {pid} 作答层样板")
        return 2
    r5 = _r5_points(KAOYUAN / f"_{pid}_compiled_source.json", answer_md)
    ev_path = KAOYUAN / f"_{pid}_exam_evidence.json"
    exam_years = sorted(set(re.findall(r"20\d\d", _load(ev_path)))) if ev_path.exists() else []

    env = load_dotenv_file(REPO / ".env")
    prompt = build_audit_prompt(pid, answer_md, r5, exam_years)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print(f"=== {pid} 异源对抗审 (models={models}, prompt~{len(prompt)}字) ===")
    results = []
    for m in models:
        print(f"  调 {m} ...", flush=True)
        r = call_model(m, prompt, env)
        results.append(r)
        if r["ok"]:
            fs = r["findings"]
            print(f"    [{m}] verdict={r['verdict']} findings={len(fs)} :: {r['summary'][:80]}")
            for f in fs:
                print(f"       - ({f.get('severity')}) 轴{f.get('axis')}: {f.get('problem','')[:100]}")
        else:
            print(f"    [{m}] ✗ {r.get('error')} | raw: {(r.get('raw') or '')[:400]!r}")

    # 跨模型汇总
    ok = [r for r in results if r["ok"]]
    high = sum(1 for r in ok for f in r["findings"] if f.get("severity") == "high")
    verdicts = [r["verdict"] for r in ok]
    print("  ───")
    print(f"  异源响应 {len(ok)}/{len(models)} | verdicts={verdicts} | high-findings={high}")

    out = {"pack_id": pid, "models": models, "results": results,
           "high_findings": high, "verdicts": verdicts}
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  报告 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
