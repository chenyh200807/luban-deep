#!/usr/bin/env python3
"""可宣传质量门 v1 — 固定场景集 + 确定性断言 + 生产入口运行器.

部署后必跑;全绿 = 可宣传态。门里不放 LLM judge:所有断言都是确定性机器可判。

- 场景集: scripts/promo_gate/scenarios/*.json(题面自含在 queries/*.txt,永不删除既有测例)。
- 入口: 复用 scripts/run_student_turn.py 的登录/start-turn/WS 通道,串行打生产入口
  (默认 https://test2.yousenjiaoyu.com)。
- 身份纪律: QA 账号凭据取自 env 或 --env-file 的 WECHAT_QA_USERNAME/PASSWORD;
  运行前导出 DEEPTUTOR_EVAL_RUNNER_AGENT 与唯一 DEEPTUTOR_EVAL_RUN_ID。
- DB 真相: 断言 A6/A7 经 `ssh Aliyun-ECS-2 docker exec deeptutor python -c ...`
  只读(mode=ro)查 chat_history.db 的 result 事件 metadata,不做任何写操作。
- 产出: runs/promo_gate/<run_id>/report.md + report.json + evidence/*.md,
  每个场景跑完立即落盘(增量 checkpoint)。

断言清单(每场景取适用项,配置在 scenario JSON 的 assertions 里):
  A1 半答卷必须出现「未纳入本次判分」,或 miss 用语 + 点名具体漏点;
  A2 得分 X/Y 中 X<=Y,且不得超过场景配置的官方满分;
  A3 「记忆口诀」段若在,必须带出处或为模板句;禁止只由漏点标题+顿号拼接的假口诀;
  A4 库外题必须含「诊断得分预估/不硬估标准分」类免责;
  A5 禁止罐头拒答(「拆小」类语句出现即红);
  A6 result 事件 metadata 必须含非空 score_authority 与 grading_rubric_provenance;
  A7 案例判分必须走 deep(metadata selected_mode);
  A8 预留(错因码分布,拍板后启用,当前 SKIP);
  A9 弱答案不得满分:金标已判定为低能力档的作答,得分率必须 < 场景配置的
     max_score_ratio(默认 0.5)——P0「兜底满分」事故的回归位;
  A10 局部覆盖必须诚实:metadata 的 case_grading_partial_scope 在场时,学员可见
     分母必须是整题名义满分(scenario.nominal_full_score),得分不得超过
     满分×覆盖比例,且 grading_official_score_allowed 必须为 false。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
DEFAULT_ENV_FILE = os.path.expanduser("~/Documents/CYH_2/Markzuo/deeptutor/.env")
REMOTE_HOST = os.getenv("PROMO_GATE_REMOTE_HOST", "Aliyun-ECS-2")
REMOTE_CONTAINER = os.getenv("PROMO_GATE_REMOTE_CONTAINER", "deeptutor")
REMOTE_DB_PATH = "/app/data/user/chat_history.db"
TURN_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# ---------------------------------------------------------------------------
# 确定性断言实现
# ---------------------------------------------------------------------------

A1_PRIMARY = "未纳入本次判分"
A1_MISS_WORDS = [
    "未作答", "漏答", "未见作答", "未提交", "未回答", "没有作答", "未给出作答", "缺答", "未答",
    # 生产判分卡真实 miss 标记形态(2026-07-31 r2 校准;仍须与点名漏点 token 同时成立,语义未弱化)
    "漏点", "漏掉", "漏/错", "没有覆盖", "未覆盖", "需要补",
]
A5_CANNED_REFUSALS = ["拆小", "一道一道发", "一题一题发", "分批发送", "把题目分开发"]
A4_DISCLAIMER_TERMS = [
    "诊断得分预估", "得分预估", "预估得分", "诊断分", "非官方", "不硬估",
    "不代表官方", "无官方评分标准", "仅供参考", "参考性评分", "无法给出官方",
]

# 得分 X/Y:必须贴着「分」或「得分」上下文,避免匹配题面里的日期/序号
SCORE_SLASH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*分")
SCORE_LABEL_RE = re.compile(r"得分[:：]?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
FULLSCORE_PAIR_RE = re.compile(r"得\s*(\d+(?:\.\d+)?)\s*分[^。\n]{0,20}?满分\s*(\d+(?:\.\d+)?)")
MNEMONIC_LINE_RE = re.compile(r"^[^、\s]{2,15}(、[^、\s]{2,15}){2,}$")


def _result(assert_id: str, passed: bool | None, evidence: str) -> dict[str, Any]:
    status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
    return {"id": assert_id, "status": status, "evidence": evidence[:500]}


def check_a1(text: str, missing_tokens: list[str]) -> dict[str, Any]:
    if A1_PRIMARY in text:
        return _result("A1", True, f"命中「{A1_PRIMARY}」")
    miss_hit = [w for w in A1_MISS_WORDS if w in text]
    token_hit = [t for t in missing_tokens if t in text]
    if miss_hit and token_hit:
        return _result("A1", True, f"miss用语{miss_hit[:3]} + 点名漏点{token_hit[:3]}")
    return _result(
        "A1", False,
        f"半答卷未标记漏答:无「{A1_PRIMARY}」;miss用语命中={miss_hit[:3]};漏点点名命中={token_hit[:3]}",
    )


def check_a2(text: str, official_full_score: float | None) -> dict[str, Any]:
    pairs: list[tuple[float, float]] = []
    for m in SCORE_SLASH_RE.finditer(text):
        pairs.append((float(m.group(1)), float(m.group(2))))
    for m in SCORE_LABEL_RE.finditer(text):
        pairs.append((float(m.group(1)), float(m.group(2))))
    for m in FULLSCORE_PAIR_RE.finditer(text):
        pairs.append((float(m.group(1)), float(m.group(2))))
    if not pairs:
        return _result("A2", True, "回复中未出现 X/Y 型得分表述(无可违反面)")
    bad = [(x, y) for x, y in pairs if x > y]
    if bad:
        return _result("A2", False, f"得分 X>Y: {bad}")
    if official_full_score is not None:
        over = [(x, y) for x, y in pairs if x > official_full_score or y > official_full_score]
        if over:
            return _result("A2", False, f"超官方满分{official_full_score}: {over}")
    return _result("A2", True, f"得分对 {pairs} 全部 X<=Y 且不超官方满分")


def check_a3(text: str) -> dict[str, Any]:
    idx = text.find("口诀")
    if idx < 0:
        return _result("A3", True, "无口诀段(N/A)")
    segment = text[idx: idx + 400]
    if "出处" in segment:
        return _result("A3", True, "口诀段带出处")
    for line in segment.splitlines():
        line = line.strip().strip("「」“”\"'::：,。.!?")
        if not line or "口诀" in line:
            continue
        if MNEMONIC_LINE_RE.match(line):
            return _result("A3", False, f"疑似顿号拼接假口诀且无出处: {line[:80]}")
    return _result("A3", True, "口诀段无出处但非顿号拼接形态(按模板句放行)")


def check_a4(text: str) -> dict[str, Any]:
    hits = [t for t in A4_DISCLAIMER_TERMS if t in text]
    if hits:
        return _result("A4", True, f"库外免责命中 {hits[:3]}")
    return _result("A4", False, "库外题未见「诊断得分预估/不硬估标准分」类免责表述")


def check_a5(text: str) -> dict[str, Any]:
    hits = [t for t in A5_CANNED_REFUSALS if t in text]
    if hits:
        return _result("A5", False, f"罐头拒答命中 {hits}")
    return _result("A5", True, "无罐头拒答用语")


def check_a6(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return _result("A6", False, "未取到 result 事件 metadata(远端查询失败或无 result 事件)")
    sa = str(metadata.get("score_authority") or "").strip()
    gp = str(metadata.get("grading_rubric_provenance") or "").strip()
    if sa and gp:
        return _result("A6", True, f"score_authority={sa[:80]}; grading_rubric_provenance={gp[:80]}")
    return _result("A6", False, f"score_authority={sa!r}; grading_rubric_provenance={gp!r}(必须均非空)")


def check_a7(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return _result("A7", False, "未取到 result 事件 metadata")
    mode = str(metadata.get("selected_mode") or "").strip()
    if "deep" in mode.lower():
        return _result("A7", True, f"selected_mode={mode}")
    return _result("A7", False, f"selected_mode={mode!r}(案例判分必须走 deep)")


def _score_pairs(text: str) -> list[tuple[float, float]]:
    """回复中所有 X/Y 型得分对(与 A2 同一解析权威,不许各判各的)。"""
    pairs: list[tuple[float, float]] = []
    for regex in (SCORE_SLASH_RE, SCORE_LABEL_RE, FULLSCORE_PAIR_RE):
        for m in regex.finditer(text):
            pairs.append((float(m.group(1)), float(m.group(2))))
    return pairs


def check_a9(text: str, max_score_ratio: float) -> dict[str, Any]:
    """A9 弱答案不得满分(P0「兜底满分」回归位)。

    金标已判定为低能力档(expected_score_ratio 远低于 0.5)的作答,若判分核给出
    高得分率,就是 2026-08-01 P0 事故的复发。解析不到得分 = 判不了 = FAIL
    (证据缺失不算绿)。"""
    pairs = _score_pairs(text)
    if not pairs:
        return _result("A9", False, "回复中解析不到 X/Y 型得分,无法证明未给满分(证据缺失不算绿)")
    ratios = [(x / y) for x, y in pairs if y > 0]
    if not ratios:
        return _result("A9", False, f"得分对 {pairs} 分母非正,无法计算得分率")
    worst = max(ratios)
    if worst < max_score_ratio:
        return _result("A9", True, f"最高得分率 {worst:.3f} < {max_score_ratio}(得分对 {pairs})")
    return _result(
        "A9", False,
        f"弱答案得分率 {worst:.3f} >= {max_score_ratio}(得分对 {pairs})——P0 兜底满分形态复发",
    )


PARTIAL_SCOPE_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def check_a10(
    text: str, metadata: dict[str, Any] | None, nominal_full_score: float | None
) -> dict[str, Any]:
    """A10 局部覆盖必须诚实(P0 分母修复的回归位)。

    参考答案只覆盖部分小问时,采分点池不得缩放到整题名义满分;学员看到的分母
    必须仍是整题满分(否则「1/4 张卷子的满分」被说成整题满分)。"""
    if metadata is None:
        return _result("A10", False, "未取到 result 事件 metadata(远端查询失败或无 result 事件)")
    scope = str(metadata.get("case_grading_partial_scope") or "").strip()
    if not scope:
        return _result(
            "A10", False,
            "metadata 无 case_grading_partial_scope——本场景的前置(tier-2 命中兄弟行、"
            "参考答案只覆盖部分小问)未成立,判不了分母诚实性",
        )
    m = PARTIAL_SCOPE_RE.match(scope)
    if not m:
        return _result("A10", False, f"case_grading_partial_scope={scope!r} 不是 N/M 形态")
    covered, total = float(m.group(1)), float(m.group(2))
    if not (0 < covered < total):
        return _result("A10", False, f"partial_scope={scope} 不满足 0 < N < M(局部覆盖才该在场)")
    official_allowed = metadata.get("grading_official_score_allowed")
    if official_allowed is not False:
        return _result(
            "A10", False,
            f"partial_scope={scope} 在场但 grading_official_score_allowed={official_allowed!r}"
            "(局部覆盖分不得作官方成绩)",
        )
    pairs = _score_pairs(text)
    if not pairs:
        return _result("A10", False, f"partial_scope={scope},但回复里解析不到 X/Y 得分,分母无从校验")
    if nominal_full_score is None:
        return _result("A10", False, "场景未配置 nominal_full_score,无法校验分母是否为整题满分")
    bad_denominator = [(x, y) for x, y in pairs if abs(y - nominal_full_score) > 0.01]
    if bad_denominator:
        return _result(
            "A10", False,
            f"partial_scope={scope} 在场,但分母不是整题名义满分 {nominal_full_score}: {bad_denominator}",
        )
    cap = nominal_full_score * (covered / total) + 0.01
    over = [(x, y) for x, y in pairs if x > cap]
    if over:
        return _result(
            "A10", False,
            f"partial_scope={scope} 得分超覆盖比例上限 {cap:.2f}: {over}",
        )
    return _result(
        "A10", True,
        f"partial_scope={scope}; 分母={nominal_full_score}(整题满分); 得分对 {pairs} 均 <= "
        f"{cap:.2f}; official_score_allowed=false",
    )


def check_generic(assertion: dict[str, Any], text: str) -> dict[str, Any]:
    aid = str(assertion.get("id") or "GEN")
    atype = str(assertion.get("type") or "")
    terms = assertion.get("terms") or []
    if atype == "contains_any":
        hits = [t for t in terms if t in text]
        return _result(aid, bool(hits), f"contains_any{terms} 命中 {hits[:3]}")
    if atype == "contains_all":
        missing = [t for t in terms if t not in text]
        return _result(aid, not missing, f"contains_all{terms} 缺 {missing}")
    if atype == "not_contains_any":
        hits = [t for t in terms if t in text]
        return _result(aid, not hits, f"not_contains_any 命中 {hits}")
    if atype == "min_length":
        value = int(assertion.get("value") or 0)
        return _result(aid, len(text) >= value, f"len={len(text)} (>={value})")
    return _result(aid, None, f"未知断言类型 {atype},按 SKIP 处理")


def evaluate_assertions(
    scenario: dict[str, Any],
    text: str,
    metadata: dict[str, Any] | None,
    turn_ok: bool,
    turn_status: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    results.append(
        _result("A0", turn_ok, f"turn status={turn_status}; visible_len={len(text)}(入口必须完成且回复非空)")
    )
    for assertion in scenario.get("assertions", []):
        aid = str(assertion.get("id") or "")
        if assertion.get("skip"):
            results.append(_result(aid, None, str(assertion.get("note") or "预留断言")))
            continue
        if aid == "A1":
            results.append(check_a1(text, list(assertion.get("missing_tokens") or [])))
        elif aid == "A2":
            results.append(check_a2(text, scenario.get("official_full_score")))
        elif aid == "A3":
            results.append(check_a3(text))
        elif aid == "A4":
            results.append(check_a4(text))
        elif aid == "A5":
            results.append(check_a5(text))
        elif aid == "A6":
            results.append(check_a6(metadata))
        elif aid == "A7":
            results.append(check_a7(metadata))
        elif aid == "A9":
            results.append(check_a9(text, float(assertion.get("max_score_ratio") or 0.5)))
        elif aid == "A10":
            nominal = scenario.get("nominal_full_score")
            results.append(
                check_a10(text, metadata, float(nominal) if nominal is not None else None)
            )
        else:
            results.append(check_generic(assertion, text))
    return results


# ---------------------------------------------------------------------------
# 远端只读真相(A6/A7): ssh + docker exec + sqlite ro
# ---------------------------------------------------------------------------

_REMOTE_SNIPPET = """
import sqlite3, json
TURN_ID = {turn_id!r}
KEYS = [
    "score_authority", "grading_rubric_provenance", "selected_mode",
    "execution_path", "execution_engine", "requested_response_mode",
    "effective_response_mode", "decision_source", "grading_engine_version",
    "case_grading_adjudication_strategy", "case_rubric_bank_slot",
    "case_mnemonic_source", "question_lifecycle_scene", "capability",
    # P0 分母修复(2026-08-01)的判据面:局部覆盖比例 + 官方成绩闸 + 命中的 bank 行
    "case_grading_partial_scope", "grading_official_score_allowed",
    "case_grading_direct_attempt_qid", "case_subq_coverage",
]
out = {{"found": False}}
try:
    conn = sqlite3.connect("file:{db_path}?mode=ro", uri=True, timeout=5.0)
    row = conn.execute(
        "SELECT metadata_json FROM turn_events WHERE turn_id=? AND type='result' ORDER BY seq DESC LIMIT 1",
        (TURN_ID,),
    ).fetchone()
    trow = conn.execute(
        "SELECT status, capability FROM turns WHERE id=?", (TURN_ID,)
    ).fetchone()
    if row:
        md = json.loads(row[0] or "{{}}")
        out = {{"found": True}}
        for k in KEYS:
            if k in md:
                out[k] = md[k]
    if trow:
        out["turn_status"] = trow[0]
        out["turn_capability"] = trow[1]
except Exception as exc:
    out = {{"found": False, "error": str(exc)}}
print(json.dumps(out, ensure_ascii=False))
"""


def fetch_remote_result_metadata(turn_id: str) -> dict[str, Any] | None:
    """只读查生产 chat_history.db 里该 turn 的 result 事件 metadata(A6/A7 证据)。"""
    if not turn_id or not TURN_ID_RE.match(turn_id):
        return None
    src = _REMOTE_SNIPPET.format(turn_id=turn_id, db_path=REMOTE_DB_PATH)
    b64 = base64.b64encode(src.encode("utf-8")).decode("ascii")
    remote_cmd = (
        f"docker exec {REMOTE_CONTAINER} python -c "
        f"\"import base64;exec(base64.b64decode('{b64}').decode())\""
    )
    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=15", REMOTE_HOST, remote_cmd],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        payload = json.loads(line[-1])
    except json.JSONDecodeError:
        return None
    return payload if payload.get("found") else None


def fetch_deploy_sha() -> str:
    """只读记录 test2 当前部署 SHA(报告标注用)。"""
    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=15", REMOTE_HOST,
             "grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)=' /root/deeptutor/.env"],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout.strip() or "unknown"
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"


# ---------------------------------------------------------------------------
# 凭据 / eval 身份纪律
# ---------------------------------------------------------------------------

def load_qa_credentials(env_file: str) -> tuple[str, str]:
    username = os.getenv("WECHAT_QA_USERNAME", "").strip()
    password = os.getenv("WECHAT_QA_PASSWORD", "").strip()
    if not (username and password) and env_file and os.path.exists(env_file):
        for raw in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("WECHAT_QA_USERNAME=") and not username:
                username = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("WECHAT_QA_PASSWORD=") and not password:
                password = line.split("=", 1)[1].strip().strip('"')
    if not username or not password:
        raise SystemExit(f"WECHAT_QA_USERNAME/PASSWORD 未找到(env 或 {env_file})")
    return username, password


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def scenario_verdict(assertion_results: list[dict[str, Any]]) -> str:
    if any(r["status"] == "FAIL" for r in assertion_results):
        return "FAIL"
    return "PASS"


def write_reports(run_dir: Path, report: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 可宣传质量门 v1 — 运行报告",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- base_url: {report['base_url']}",
        f"- 部署 SHA(test2): `{report['deploy_sha']}`",
        f"- 开始: {report['started_at']}  结束: {report.get('finished_at', '(运行中)')}",
        f"- 结果: **{report['summary']['pass']} PASS / {report['summary']['fail']} FAIL / "
        f"{report['summary']['total']} 场景**(全绿 = 可宣传态)",
        "",
        "| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |",
        "|---|---|---|---|---|",
    ]
    for s in report["scenarios"]:
        failed = ",".join(r["id"] for r in s["assertion_results"] if r["status"] == "FAIL") or "-"
        detail = " ".join(
            f"{r['id']}:{r['status']}" for r in s["assertion_results"] if r["status"] != "SKIP"
        )
        lines.append(f"| {s['id']} | {s['title']} | **{s['verdict']}** | {failed} | {detail} |")
    lines += ["", "## 逐场景证据摘录", ""]
    for s in report["scenarios"]:
        lines.append(f"### {s['id']} — {s['verdict']}")
        lines.append(f"- {s['title']}(form={s['form']}; turn_id=`{s.get('turn_id', '')}`; "
                     f"status={s.get('turn_status', '')}; latency={s.get('latency_ms', 0):.0f}ms)")
        for r in s["assertion_results"]:
            lines.append(f"  - {r['id']} **{r['status']}** — {r['evidence']}")
        excerpt = (s.get("response_excerpt") or "").replace("\n", " ")
        lines.append(f"  - 回复摘录: {excerpt[:300]}")
        lines.append("")
    lines.append("完整回复与 metadata 见 `evidence/<场景id>.md`。")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_evidence(run_dir: Path, scenario: dict[str, Any], record: dict[str, Any],
                   query: str, response: str, metadata: dict[str, Any] | None) -> None:
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    body = [
        f"# {scenario['id']} — {record['verdict']}",
        f"- title: {scenario['title']}",
        f"- turn_id: {record.get('turn_id', '')}",
        f"- turn_status: {record.get('turn_status', '')}",
        "",
        "## 断言",
    ]
    for r in record["assertion_results"]:
        body.append(f"- {r['id']} **{r['status']}** — {r['evidence']}")
    body += [
        "",
        "## result 事件 metadata(远端只读摘取)",
        "```json",
        json.dumps(metadata, ensure_ascii=False, indent=2) if metadata else "null",
        "```",
        "",
        "## 发送的题面/作答",
        "```",
        query,
        "```",
        "",
        "## 完整回复",
        "```",
        response,
        "```",
    ]
    (ev_dir / f"{scenario['id']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_scenarios(only: list[str]) -> list[dict[str, Any]]:
    scenarios = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        if only and scenario["id"] not in only:
            continue
        query_file = SCENARIO_DIR / scenario["query_file"]
        scenario["_query"] = query_file.read_text(encoding="utf-8").strip()
        scenarios.append(scenario)
    order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6, "T7": 7, "T8": 8}
    scenarios.sort(key=lambda s: (order.get(s.get("question_group"), 9), s["id"]))
    return scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="可宣传质量门 v1 运行器(串行,生产入口,只读)")
    parser.add_argument("--base-url", default=os.getenv("DEEPTUTOR_QA_BASE_URL", "https://test2.yousenjiaoyu.com"))
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--only", default="", help="逗号分隔的场景 id,只跑这些")
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    parser.add_argument("--skip-remote", action="store_true", help="跳过远端 DB 查询(A6/A7 将 FAIL)")
    parser.add_argument("--infra-retries", type=int, default=2,
                        help="入口5xx/WS传输异常的重试次数(超时/挂死不重试,保留为质量FAIL)")
    parser.add_argument("--infra-backoff-seconds", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true", help="只校验场景文件,不打生产")
    args = parser.parse_args(argv)

    only = [x.strip() for x in args.only.split(",") if x.strip()]
    scenarios = load_scenarios(only)
    if not scenarios:
        raise SystemExit("没有匹配的场景")
    if args.dry_run:
        for s in scenarios:
            print(f"{s['id']}: query {len(s['_query'])} chars, "
                  f"assertions={[a.get('id') for a in s.get('assertions', [])]}")
        print(f"dry-run ok: {len(scenarios)} scenarios")
        return 0

    # eval 身份纪律
    run_id = args.run_id or f"promo_gate_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}"
    os.environ["DEEPTUTOR_EVAL_RUNNER_AGENT"] = os.getenv("DEEPTUTOR_EVAL_RUNNER_AGENT", "claude_code")
    os.environ["DEEPTUTOR_EVAL_RUN_ID"] = run_id
    username, password = load_qa_credentials(args.env_file)
    os.environ["DEEPTUTOR_QA_USERNAME"] = username
    os.environ["DEEPTUTOR_QA_PASSWORD"] = password

    from scripts.run_student_turn import _login, _new_conversation, _turn  # noqa: E402

    base_url = args.base_url.rstrip("/")
    run_dir = PROJECT_ROOT / "runs" / "promo_gate" / run_id
    deploy_sha = fetch_deploy_sha() if not args.skip_remote else "unknown(--skip-remote)"

    report: dict[str, Any] = {
        "run_id": run_id,
        "base_url": base_url,
        "deploy_sha": deploy_sha,
        "started_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "eval_runner_agent": os.environ["DEEPTUTOR_EVAL_RUNNER_AGENT"],
        "summary": {"total": len(scenarios), "pass": 0, "fail": 0},
        "scenarios": [],
    }

    auth = asyncio.run(_login(base_url, 60.0))
    token = auth["token"]
    print(f"[promo-gate] login ok user_id={auth.get('user_id')} run_id={run_id}", flush=True)

    def _is_infra_error(out: dict[str, Any]) -> bool:
        """基础设施级失败(入口 5xx / WS 传输异常)可重试;
        WS 超时/挂死**不算**——那是判分死亡事故的形态,必须保留为质量 FAIL。"""
        status = str(out.get("status") or "")
        ws_error = str(out.get("ws_error") or "")
        if status == "ws_exception":
            return True
        # WS 握手级超时(零事件+低延迟,websockets 默认 open_timeout=10s)是传输层,可重试;
        # 跑满 --timeout-seconds 的真挂死(判分死亡事故形态)绝不重试。
        if status == "ws_timeout" and not out.get("event_types") and float(out.get("latency_ms") or 0) < 60000:
            return True
        if "create_conversation_failed:5" in status or "start_turn_failed:5" in status:
            return True
        return bool(re.search(r"failed:5\d\d", ws_error))

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["id"]
        print(f"[promo-gate] ({i}/{len(scenarios)}) {sid} ...", flush=True)
        started = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            try:
                conv = asyncio.run(_new_conversation(base_url, token, 60.0))
                turn_out = asyncio.run(
                    _turn(
                        base_url, token, conv["conversation_id"], scenario["_query"],
                        args.timeout_seconds,
                        client_turn_id=f"{run_id}_{sid}_a{attempts}",
                    )
                )
            except SystemExit as exc:
                turn_out = {"ok": False, "status": f"driver_error:{exc}", "visible_response": "",
                            "turn_id": "", "latency_ms": (time.monotonic() - started) * 1000}
            if turn_out.get("ok") or attempts > args.infra_retries or not _is_infra_error(turn_out):
                break
            print(f"[promo-gate] {sid} infra error ({turn_out.get('status')}), "
                  f"retry {attempts}/{args.infra_retries} in {args.infra_backoff_seconds:.0f}s", flush=True)
            time.sleep(args.infra_backoff_seconds)
        response = str(turn_out.get("visible_response") or "")
        turn_id = str(turn_out.get("turn_id") or "")
        turn_status = str(turn_out.get("status") or "unknown")
        turn_ok = bool(turn_out.get("ok")) and bool(response.strip())

        metadata: dict[str, Any] | None = None
        needs_remote = any(a.get("id") in ("A6", "A7", "A10") for a in scenario.get("assertions", []))
        if turn_id and not args.skip_remote:
            # 案例场景一律摘取 metadata 作观测;A6/A7 场景是断言必需
            if needs_remote or scenario.get("case_grading") or scenario.get("question_group") in ("T1", "T2", "T3", "T4"):
                time.sleep(3)  # 给 result 事件落盘留一点余量
                metadata = fetch_remote_result_metadata(turn_id)

        assertion_results = evaluate_assertions(scenario, response, metadata, turn_ok, turn_status)
        verdict = scenario_verdict(assertion_results)
        record = {
            "id": sid,
            "title": scenario["title"],
            "form": scenario.get("form"),
            "question_group": scenario.get("question_group"),
            "qid": scenario.get("qid"),
            "verdict": verdict,
            "turn_id": turn_id,
            "turn_status": turn_status,
            "attempts": attempts,
            "latency_ms": float(turn_out.get("latency_ms") or 0.0),
            "assertion_results": assertion_results,
            "observed_metadata": {
                k: metadata.get(k) for k in (
                    "score_authority", "grading_rubric_provenance", "selected_mode",
                    "execution_path", "turn_capability",
                    "case_grading_partial_scope", "grading_official_score_allowed",
                    "case_grading_direct_attempt_qid")
            } if metadata else None,
            "response_excerpt": response[:400],
        }
        report["scenarios"].append(record)
        report["summary"]["pass"] = sum(1 for s in report["scenarios"] if s["verdict"] == "PASS")
        report["summary"]["fail"] = sum(1 for s in report["scenarios"] if s["verdict"] == "FAIL")
        write_reports(run_dir, report)  # 增量落盘
        write_evidence(run_dir, scenario, record, scenario["_query"], response, metadata)
        print(f"[promo-gate] {sid} -> {verdict} "
              f"({', '.join(r['id'] + ':' + r['status'] for r in assertion_results if r['status'] == 'FAIL') or 'all green'})",
              flush=True)

    report["finished_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    write_reports(run_dir, report)
    total, npass = report["summary"]["total"], report["summary"]["pass"]
    print(f"[promo-gate] done: {npass}/{total} PASS -> {run_dir}/report.md", flush=True)
    return 0 if npass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
