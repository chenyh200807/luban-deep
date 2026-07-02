#!/usr/bin/env python3
"""Shared primitives for the 6 deterministic accuracy probes.

固化纪律(从 scratchpad 探针整理而来, 口径一字不改):
- 主裁决永远是确定性断言; 异源 LLM(DeepSeek/GLM) 仅附加盲点检测, 绝不主裁。
- 终态观测读 **持久化** ``/api/v1/conversations/{cid}/messages``(非流式, 非动作自报)。
- judge 假阳自动降级: network 坏调用 / 限流 / 无 key -> 返回带 ``degraded`` 标记的
  verdict, 调用方据此把该判官信号标 "不计 pass/fail", 绝不当作内容失败。

所有探针通过本模块共享 login / new_conv / turn / 终态读取 / 异源判官, 不再各自硬编码
``BASE`` 或 scratchpad 绝对路径。``BASE`` 与 ``RUNS`` 由参数/环境注入。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

# scripts/quality_gate/probes/_probe_common.py -> repo root is parents[3].
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BASE = os.environ.get(
    "EVAL_BASE",
    os.environ.get("DEEPTUTOR_QA_BASE_URL", "https://test2.yousenjiaoyu.com"),
)
PRIMITIVE = str(PROJECT_ROOT / "scripts" / "run_student_turn.py")

# Verdict returned by a judge whose call could not be trusted (network error,
# rate limit, missing key). Callers MUST treat these as "not counted", never as a
# content pass/fail. This is the anti-self-証 demotion contract.
DEGRADED_VERDICT = "JUDGE_DEGRADED"


def _run(cmd: list[str], timeout: int = 150) -> dict[str, Any]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return {"_error": (r.stderr[-400:] or r.stdout[-400:])}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"_error": f"parse:{e}:{r.stdout[-200:]}"}


def login(base: str, timeout: int = 60) -> str | None:
    return _run(["python", PRIMITIVE, "login", "--api-base-url", base], timeout).get("token")


def new_conv(token: str, base: str, timeout: int = 60) -> str | None:
    return _run(
        ["python", PRIMITIVE, "new", "--token", token, "--api-base-url", base], timeout
    ).get("conversation_id")


def turn(token: str, cid: str, query: str, base: str, timeout: int = 150) -> dict[str, Any]:
    return _run(
        [
            "python", PRIMITIVE, "turn", "--token", token, "--conversation-id", cid,
            "--query", query, "--timeout-seconds", "120", "--api-base-url", base,
        ],
        timeout,
    )


def assistant_messages(token: str, cid: str, base: str, limit: int = 16,
                       timeout: int = 30) -> list[dict]:
    """独立终态观测: 读持久化 /messages(非流式, 非动作自报), 返回 assistant 消息列表."""
    req = urllib.request.Request(
        f"{base}/api/v1/conversations/{cid}/messages?limit={limit}",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=timeout))
    msgs = data.get("messages") or data.get("data") or (data if isinstance(data, list) else [])
    return [m for m in msgs if m.get("role") in ("assistant", "bot", "ai")]


def terminal_messages(token: str, cid: str, base: str, want: int = 2,
                      attempts: int = 6) -> list[dict]:
    """持久化终态 poll-retry: turn 返回与 /messages 落库有短延迟, 等到 >= want 条."""
    last: list[dict] = []
    for _ in range(attempts):
        try:
            last = assistant_messages(token, cid, base)
        except Exception:  # noqa: BLE001
            pass
        if len(last) >= want:
            return last
        time.sleep(2)
    return last


def message_text(msg: dict) -> str:
    c = msg.get("content") or ""
    if isinstance(c, list):
        return " ".join(
            str(x.get("text", "") if isinstance(x, dict) else x) for x in c
        )
    if not isinstance(c, str):
        return json.dumps(c, ensure_ascii=False)
    return c


# ---------------- cross-source judges (附加, 带自动降级) ----------------

def _post_json(url: str, key: str, body: dict, timeout: int = 90) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    return resp


def _is_rate_limit(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        return True
    return "429" in str(exc) or "rate" in str(exc).lower()


def deepseek_judge(system: str, user: str) -> dict[str, Any]:
    """DeepSeek 异源判官(附加). 网络/限流/无 key -> DEGRADED, 调用方不计 pass/fail."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    if not key:
        return {"verdict": DEGRADED_VERDICT, "degraded": True, "reason": "no DEEPSEEK_API_KEY"}
    url = f"{base}/chat/completions"
    body = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = _post_json(url, key, body)
            return json.loads(resp["choices"][0]["message"]["content"])
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if _is_rate_limit(e) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            if attempt < 2:
                time.sleep(2)
                continue
    return {"verdict": DEGRADED_VERDICT, "degraded": True, "reason": f"deepseek:{str(last_exc)[:140]}"}


def glm_judge(system: str, user: str) -> dict[str, Any]:
    """GLM 异源判官(附加). 网络/限流/无 key -> DEGRADED, 调用方不计 pass/fail."""
    key = os.environ.get("BIGMODEL_API_KEY", "")
    if not key:
        return {"verdict": DEGRADED_VERDICT, "degraded": True, "reason": "no BIGMODEL_API_KEY"}
    url = os.environ.get(
        "BIGMODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    ).rstrip("/") + "/chat/completions"
    body = {
        "model": os.environ.get("BIGMODEL_MODEL", "glm-4.6"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
    }
    import re
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = _post_json(url, key, body, timeout=60)
            txt = resp["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            return json.loads(m.group(0)) if m else {"verdict": "PARSE_ERR", "reason": txt[:120]}
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if _is_rate_limit(e) and attempt < 1:
                time.sleep(3)
                continue
    return {"verdict": DEGRADED_VERDICT, "degraded": True, "reason": f"glm:{str(last_exc)[:140]}"}


def is_degraded(verdict: dict[str, Any] | None) -> bool:
    if not verdict:
        return True
    return bool(verdict.get("degraded")) or verdict.get("verdict") == DEGRADED_VERDICT


def run_dimension(
    name: str,
    units: list[Callable[[], dict[str, Any]]],
    runs: int,
) -> dict[str, Any]:
    """统一维度跑法: 每个 unit 跑 ``runs`` 轮, 收集 pass/None(inconclusive).

    每个 unit() 返回 dict, 至少含 ``pass``(True/False/None). None = inconclusive,
    不计 pass/fail。失败率口径 = fail / 有效轮; 复现率 = 同一断言重复 fail 次数。
    """
    rows: list[dict[str, Any]] = []
    for unit in units:
        for r in range(runs):
            try:
                rec = unit()
            except Exception as e:  # noqa: BLE001
                rec = {"pass": None, "inconclusive": True, "why": f"exc:{str(e)[:150]}"}
            rec.setdefault("run", r + 1)
            rows.append(rec)
    conclusive = [x for x in rows if x.get("pass") is not None]
    failed = [x for x in conclusive if x.get("pass") is False]
    passed = [x for x in conclusive if x.get("pass") is True]
    return {
        "dim": name,
        "runs_per_unit": runs,
        "rows": rows,
        "conclusive": len(conclusive),
        "inconclusive": len(rows) - len(conclusive),
        "passed": len(passed),
        "failed": len(failed),
        "fail_rate": (len(failed) / len(conclusive)) if conclusive else None,
        "reproduced": len(failed) > 0,
    }
