#!/usr/bin/env python3
"""Live judge adapters for the M35 R2 AI-governed gold labeling pipeline.

Five no-Claude HTTP judges (explicit roles pinned by
``run_luban_m35_ai_governed_gold_labeling.LIVE_MODEL_ROLES``):

  - ``deepseek-chat``     (DeepSeek HTTP, ``DEEPSEEK_API_KEY``)   -> blind panel
  - ``qwen-max``          (DashScope compatible-mode HTTP,
                           ``DASHSCOPE_API_KEY``)                 -> blind panel
  - ``qwen-plus``         (DashScope compatible-mode HTTP,
                           ``DASHSCOPE_API_KEY``)                 -> blind panel
  - ``deepseek-reasoner`` (DeepSeek HTTP, ``DEEPSEEK_API_KEY``)   -> arbiter
  - ``qwen-turbo``        (DashScope compatible-mode HTTP,
                           ``DASHSCOPE_API_KEY``)                 -> adversarial prosecutor

Claude and Codex adapters are kept below but are not part of the default
2026-06-11 panel because Claude Code is session-limited and Codex CLI is too
slow inside mutation replay in this environment.

Every adapter takes ``(scoring_point, student_answer, official_anchor)`` and
returns ``{"verdict": hit|partial|miss, "evidence_span", "confidence"}``.
Any transport failure, timeout (60s) or unparseable output makes the judge
abstain: ``{"verdict": "abstain", ..., "abstain_reason": ...}`` -- never a
fabricated verdict, never counted as an accept.

Per-call token usage (when the transport exposes it) and abstentions are
accumulated in :class:`JudgeStats` for the run report. Successful verdicts
for identical prompts are memoized per judge (mutation cases frequently
reproduce the original text verbatim); abstains are never cached.
"""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
DOTENV_PATH = REPO / ".env"

JudgeFn = Callable[[dict[str, Any], str, dict[str, Any]], dict[str, Any]]

JUDGE_TIMEOUT_SECONDS = 60
# deepseek-reasoner emits chain-of-thought before its answer; allow longer.
REASONER_TIMEOUT_SECONDS = 300
VALID_VERDICTS = ("hit", "partial", "miss")
ABSTAIN_VERDICT = "abstain"

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DASHSCOPE_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"
QWEN_MODEL = "qwen-max"
QWEN_PROSECUTOR_MODEL = "qwen-plus"
QWEN_TURBO_MODEL = "qwen-turbo"
CLAUDE_MODELS = {"opus": "claude-opus-4-8", "fable": "claude-fable-5"}

# List-price estimates (USD per 1M tokens) for metered HTTP providers only.
# CLI judges (codex / claude) run on subscriptions: tokens are reported when
# the transport exposes them but no dollar estimate is fabricated.
PRICING_USD_PER_MTOKEN = {
    "deepseek-chat": {"input": 0.28, "output": 0.42, "basis": "deepseek list price, cache-miss"},
    "deepseek-reasoner": {"input": 0.28, "output": 0.42, "basis": "deepseek list price, cache-miss"},
    "qwen-max": {"input": 0.33, "output": 1.32, "basis": "dashscope qwen-max CNY2.4/9.6 per 1M at 7.25 CNY/USD"},
    "qwen-plus": {"input": 0.11, "output": 0.44, "basis": "dashscope qwen-plus CNY0.8/3.2 per 1M at 7.25 CNY/USD"},
    "qwen-turbo": {"input": 0.041, "output": 0.083, "basis": "dashscope qwen-turbo CNY0.3/0.6 per 1M at 7.25 CNY/USD"},
}


class JudgeTransportError(Exception):
    """Transport-level failure (HTTP error, timeout, CLI failure).

    ``retryable`` marks transient network fluctuation (timeout, connection
    reset, 429, 5xx, CLI hang) that a bounded backoff retry can ride out;
    deterministic failures (auth, 4xx, unparseable body, CLI quota) stay
    ``False`` so callers fail fast instead of hammering a wall.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


# Bounded backoff so a momentary network blip (incl. sleep/wake severing live
# sockets) does not turn a single judge call into a permanent abstention.
TRANSPORT_RETRY_ATTEMPTS = 4  # 1 initial try + up to 3 retries
TRANSPORT_RETRY_BASE_DELAY_SECONDS = 1.0  # 1s, 2s, 4s exponential
TRANSPORT_RETRY_MAX_DELAY_SECONDS = 8.0


def _retry_transport(operation: Callable[[], Any]) -> Any:
    """Run ``operation``, retrying only ``retryable`` transport failures.

    Retries on transient network fluctuation with exponential backoff plus
    jitter; re-raises deterministic failures immediately and re-raises the
    last transient failure once attempts are exhausted (callers then abstain,
    exactly as before — the retry layer is transparent to verdict semantics).
    """
    last_error: JudgeTransportError | None = None
    for attempt in range(TRANSPORT_RETRY_ATTEMPTS):
        try:
            return operation()
        except JudgeTransportError as exc:
            last_error = exc
            if not exc.retryable or attempt == TRANSPORT_RETRY_ATTEMPTS - 1:
                raise
            delay = min(
                TRANSPORT_RETRY_MAX_DELAY_SECONDS,
                TRANSPORT_RETRY_BASE_DELAY_SECONDS * (2**attempt),
            )
            time.sleep(delay + random.uniform(0, delay * 0.25))
    raise last_error  # unreachable: loop returns or raises above


class JudgeStats:
    """Thread-safe per-model call/abstention/token accounting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models: dict[str, dict[str, Any]] = {}

    def record(
        self,
        model_id: str,
        *,
        abstained: bool,
        cached: bool = False,
        usage: dict[str, int] | None = None,
        abstain_reason: str | None = None,
    ) -> None:
        with self._lock:
            entry = self._models.setdefault(
                model_id,
                {
                    "calls": 0,
                    "cached_hits": 0,
                    "abstains": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "abstain_reasons": {},
                },
            )
            entry["calls"] += 1
            if cached:
                entry["cached_hits"] += 1
            if abstained:
                entry["abstains"] += 1
                reason = abstain_reason or "unknown"
                entry["abstain_reasons"][reason] = entry["abstain_reasons"].get(reason, 0) + 1
            if usage:
                entry["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
                entry["completion_tokens"] += int(usage.get("completion_tokens") or 0)
                entry["total_tokens"] += int(usage.get("total_tokens") or 0)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            out: dict[str, dict[str, Any]] = {}
            for model_id, entry in self._models.items():
                pricing = PRICING_USD_PER_MTOKEN.get(model_id)
                if pricing is not None:
                    cost = round(
                        entry["prompt_tokens"] / 1_000_000 * pricing["input"]
                        + entry["completion_tokens"] / 1_000_000 * pricing["output"],
                        6,
                    )
                    basis = pricing["basis"]
                else:
                    cost = None
                    basis = "subscription_unmetered"
                out[model_id] = {
                    **{key: value for key, value in entry.items() if key != "abstain_reasons"},
                    "abstain_reasons": dict(entry["abstain_reasons"]),
                    "abstain_rate": round(entry["abstains"] / entry["calls"], 6) if entry["calls"] else 0.0,
                    "estimated_cost_usd": cost,
                    "pricing_basis": basis,
                }
            return out

    def total_known_cost_usd(self) -> float:
        return round(
            sum(entry["estimated_cost_usd"] or 0.0 for entry in self.snapshot().values()), 6
        )


def load_dotenv_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser (no ${VAR} expansion, no shell features)."""
    if not Path(path).is_file():
        return {}
    parsed: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            parsed[key] = value
    return parsed


def build_judge_prompt(
    point: dict[str, Any], student_answer: str, official_anchor: dict[str, Any]
) -> str:
    """Prompt anchored exclusively to the official scoring criterion."""
    return (
        "你是一级建造师《建筑工程管理与实务》案例题阅卷专家。\n"
        "你的唯一判定依据是下面给出的官方评分标准（采分点）。不得使用其他评分依据，不得自创采分点。\n\n"
        f"【题目编号】{official_anchor.get('question_id') or ''}\n"
        f"【题目背景与问题】\n{official_anchor.get('stem') or ''}\n\n"
        f"【官方评分标准·本采分点（满分 {point.get('max_score')} 分）】\n{point.get('criterion') or ''}\n\n"
        f"【学生作答】\n{student_answer}\n\n"
        "【判定规则】\n"
        "- 点隔离铁律：只就【本采分点】判定。学生作答常同时包含多个采分点的内容，"
        "判定时忽略与本采分点无关的部分，也不得仅因措辞/顺序不同或夹杂其它采分点内容而降级——"
        "这条只用于排除无关内容的干扰，不降低本采分点自身的覆盖要求。\n"
        "- 多部分采分点：若本采分点的标准本身含多个子项（如多步计算、N 项清单、多个"
        "“不妥+正确做法”配对），hit 要求覆盖其全部或绝大部分子项；只答其中少数子项"
        "（即便答对）判 partial；几乎未覆盖判 miss。\n"
        "- hit：完整覆盖本采分点的关键判断与关键内容（单一事实点=该事实到位；"
        "多部分点=子项基本齐全），允许同义改写。\n"
        "- partial：仅命中本采分点的部分关键内容（多部分点只答少数子项），"
        "或关键判断正确但理由/做法确有实质缺失。\n"
        "- miss：未覆盖该采分点，或关键判断错误，或仅复述题干/口号式表述而无具体内容。\n"
        "- evidence_span 必须是从学生作答中逐字摘录的最短支撑片段；miss 时为空字符串。\n\n"
        "只输出一行 JSON（不要 markdown 代码块、不要任何解释文字）：\n"
        '{"verdict":"hit|partial|miss","evidence_span":"...","confidence":0.0到1.0}'
    )


def parse_judge_output(text: str) -> dict[str, Any] | None:
    """Extract ``{verdict, evidence_span, confidence}`` from model output.

    Returns ``None`` when no valid judgment JSON can be located (the caller
    abstains; nothing is fabricated).
    """
    if not text or not text.strip():
        return None
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    stripped = text.strip()
    try:
        direct = json.loads(stripped)
        if isinstance(direct, dict):
            candidates.append(direct)
    except ValueError:
        pass
    if not candidates:
        index = stripped.find("{")
        while index != -1:
            try:
                obj, _ = decoder.raw_decode(stripped, index)
            except ValueError:
                index = stripped.find("{", index + 1)
                continue
            if isinstance(obj, dict) and "verdict" in obj:
                candidates.append(obj)
                break
            index = stripped.find("{", index + 1)
    for candidate in candidates:
        verdict = str(candidate.get("verdict") or "").strip().lower()
        if verdict not in VALID_VERDICTS:
            continue
        try:
            confidence = float(candidate.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "verdict": verdict,
            "evidence_span": str(candidate.get("evidence_span") or ""),
            "confidence": min(1.0, max(0.0, confidence)),
        }
    return None


def parse_codex_jsonl(stdout: str) -> tuple[str | None, dict[str, int] | None]:
    """Parse ``codex exec --json`` JSONL: last agent_message text + token usage."""
    message: str | None = None
    usage: dict[str, int] | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        msg = event.get("msg")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            message = str(item.get("text") or item.get("message") or "")
        elif isinstance(msg, dict) and msg.get("type") == "agent_message":
            message = str(msg.get("message") or msg.get("text") or "")
        elif event.get("type") == "agent_message":
            message = str(event.get("message") or event.get("text") or "")
        raw_usage = None
        if isinstance(event.get("usage"), dict):
            raw_usage = event["usage"]
        elif isinstance(msg, dict) and msg.get("type") == "token_count":
            info = msg.get("info") or {}
            raw_usage = info.get("total_token_usage") or info.get("last_token_usage")
        if isinstance(raw_usage, dict):
            prompt_tokens = int(raw_usage.get("input_tokens") or raw_usage.get("prompt_tokens") or 0)
            completion_tokens = int(
                raw_usage.get("output_tokens") or raw_usage.get("completion_tokens") or 0
            )
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
    return message, usage


# ---------------------------------------------------------------- transports


def _http_post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """POST JSON, return decoded JSON body. Retries transient failures."""

    def _attempt() -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise JudgeTransportError(
                f"http_{exc.code}: {detail}",
                retryable=exc.code == 429 or 500 <= exc.code < 600,
            ) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            http.client.HTTPException,
        ) as exc:
            # Includes IncompleteRead / RemoteDisconnected / BadStatusLine —
            # a response truncated mid-stream is transient network fluctuation.
            raise JudgeTransportError(f"{type(exc).__name__}: {exc}", retryable=True) from exc
        except ValueError as exc:
            # Unparseable body is deterministic given the same response.
            raise JudgeTransportError(f"{type(exc).__name__}: {exc}", retryable=False) from exc

    return _retry_transport(_attempt)


_NEUTRAL_CWD: str | None = None
_NEUTRAL_CWD_LOCK = threading.Lock()


def _neutral_cwd() -> str:
    """Empty directory so CLI agents load no project instructions/context."""
    global _NEUTRAL_CWD
    with _NEUTRAL_CWD_LOCK:
        if _NEUTRAL_CWD is None or not Path(_NEUTRAL_CWD).is_dir():
            _NEUTRAL_CWD = tempfile.mkdtemp(prefix="m35-gold-judges-")
        return _NEUTRAL_CWD


def _run_cli(cmd: list[str], timeout: float, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a CLI judge subprocess, retrying transient hangs.

    A CLI hang/timeout (the shape network fluctuation and sleep/wake take for
    codex/claude) is retryable; a clean non-zero exit (quota, auth, parse) is
    returned as-is so the caller classifies it without futile retries.
    """

    def _attempt() -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or _neutral_cwd(),
            )
        except subprocess.TimeoutExpired as exc:
            raise JudgeTransportError(f"timeout after {timeout}s", retryable=True) from exc
        except OSError as exc:
            raise JudgeTransportError(f"{type(exc).__name__}: {exc}", retryable=True) from exc
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    return _retry_transport(_attempt)


# ---------------------------------------------------------------- adapters


def _abstain(reason: str) -> dict[str, Any]:
    return {
        "verdict": ABSTAIN_VERDICT,
        "evidence_span": "",
        "confidence": 0.0,
        "abstain_reason": reason,
    }


def _wrap_judge(
    model_id: str,
    stats: JudgeStats,
    call_fn: Callable[[str], tuple[str | None, dict[str, int] | None]],
) -> JudgeFn:
    """Shared judge skeleton: prompt -> transport -> parse -> verdict/abstain.

    Successful verdicts are memoized by prompt hash; abstains never are.
    """
    cache: dict[str, dict[str, Any]] = {}
    cache_lock = threading.Lock()

    def judge(point: dict[str, Any], student_answer: str, official_anchor: dict[str, Any]) -> dict[str, Any]:
        prompt = build_judge_prompt(point, student_answer, official_anchor)
        cache_key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        with cache_lock:
            cached = cache.get(cache_key)
        if cached is not None:
            stats.record(model_id, abstained=False, cached=True)
            return dict(cached)
        try:
            text, usage = call_fn(prompt)
        except JudgeTransportError as exc:
            stats.record(model_id, abstained=True, abstain_reason=str(exc))
            return _abstain(str(exc))
        parsed = parse_judge_output(text or "")
        if parsed is None:
            stats.record(model_id, abstained=True, usage=usage, abstain_reason="unparseable_output")
            return _abstain("unparseable_output")
        stats.record(model_id, abstained=False, usage=usage)
        with cache_lock:
            cache[cache_key] = dict(parsed)
        return dict(parsed)

    return judge


def _chat_completions_call(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: float = JUDGE_TIMEOUT_SECONDS,
    max_tokens: int = 400,
) -> tuple[str | None, dict[str, int] | None]:
    body = _http_post_json(
        url,
        {"Authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        },
        timeout,
    )
    choices = body.get("choices") or []
    content = None
    if choices and isinstance(choices[0], dict):
        content = ((choices[0].get("message") or {}).get("content"))
    raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    usage = {
        "prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(raw_usage.get("completion_tokens") or 0),
        "total_tokens": int(raw_usage.get("total_tokens") or 0),
    }
    return content, usage


def make_deepseek_judge(api_key: str, stats: JudgeStats, base_url: str | None = None) -> JudgeFn:
    url = f"{(base_url or DEEPSEEK_DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    return _wrap_judge(
        "deepseek-chat",
        stats,
        lambda prompt: _chat_completions_call(url, api_key, DEEPSEEK_MODEL, prompt),
    )


def make_deepseek_reasoner_judge(
    api_key: str, stats: JudgeStats, base_url: str | None = None
) -> JudgeFn:
    """Same DeepSeek chat-completions transport, reasoner model + longer timeout."""
    url = f"{(base_url or DEEPSEEK_DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    return _wrap_judge(
        "deepseek-reasoner",
        stats,
        lambda prompt: _chat_completions_call(
            url,
            api_key,
            DEEPSEEK_REASONER_MODEL,
            prompt,
            timeout=REASONER_TIMEOUT_SECONDS,
            max_tokens=1200,
        ),
    )


def make_qwen_model_judge(
    model_id: str,
    model: str,
    api_key: str,
    stats: JudgeStats,
    base_url: str | None = None,
) -> JudgeFn:
    url = f"{(base_url or DASHSCOPE_DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    return _wrap_judge(
        model_id,
        stats,
        lambda prompt: _chat_completions_call(url, api_key, model, prompt),
    )


def make_qwen_judge(api_key: str, stats: JudgeStats, base_url: str | None = None) -> JudgeFn:
    return make_qwen_model_judge("qwen-max", QWEN_MODEL, api_key, stats, base_url=base_url)


def _codex_error_message(stdout: str) -> str | None:
    """Extract the real failure cause from codex JSONL error events."""
    message: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error" and event.get("message"):
            message = str(event["message"])
        elif event.get("type") == "turn.failed" and isinstance(event.get("error"), dict):
            message = str(event["error"].get("message") or message or "")
    return message or None


def _codex_call(prompt: str) -> tuple[str | None, dict[str, int] | None]:
    returncode, stdout, stderr = _run_cli(
        [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            "read-only",
            "--json",
            prompt,
        ],
        JUDGE_TIMEOUT_SECONDS,
    )
    if returncode != 0:
        # The JSONL error event carries the real cause (e.g. usage limits);
        # stderr is usually just "Reading additional input from stdin...".
        detail = _codex_error_message(stdout) or stderr
        raise JudgeTransportError(f"codex_exit_{returncode}: {detail[:200]}")
    return parse_codex_jsonl(stdout)


def make_codex_judge(stats: JudgeStats) -> JudgeFn:
    return _wrap_judge("gpt-codex", stats, _codex_call)


def _claude_call(claude_model: str, prompt: str) -> tuple[str | None, dict[str, int] | None]:
    returncode, stdout, stderr = _run_cli(
        [
            "claude",
            "-p",
            prompt,
            "--model",
            claude_model,
            "--output-format",
            "text",
            "--no-session-persistence",
            "--strict-mcp-config",
        ],
        JUDGE_TIMEOUT_SECONDS,
    )
    if returncode != 0:
        raise JudgeTransportError(f"claude_exit_{returncode}: {stderr[:200]}")
    # --output-format text exposes no token usage; report none rather than guess.
    return stdout, None


def make_claude_judge(model_id: str, claude_model: str, stats: JudgeStats) -> JudgeFn:
    return _wrap_judge(model_id, stats, lambda prompt: _claude_call(claude_model, prompt))


# ---------------------------------------------------------------- factory


def build_live_judges(
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, JudgeFn], JudgeStats]:
    """Build all five live judges or raise RuntimeError listing what is missing.

    ``env=None`` reads ``os.environ`` with repo ``.env`` as fallback. An
    explicit ``env`` mapping is treated as the complete environment (hermetic
    callers must not pick up real keys from ``.env``).
    """
    if env is None:
        import os

        merged: dict[str, str] = {**load_dotenv_file(DOTENV_PATH), **dict(os.environ)}
    else:
        merged = dict(env)

    def key_of(name: str) -> str:
        return str(merged.get(name) or "").strip()

    missing: list[str] = []
    deepseek_key = key_of("DEEPSEEK_API_KEY")
    dashscope_key = key_of("DASHSCOPE_API_KEY")
    if not deepseek_key:
        missing.append("DEEPSEEK_API_KEY")
    if not dashscope_key:
        missing.append("DASHSCOPE_API_KEY")
    if missing:
        raise RuntimeError(
            "live judges unavailable, missing prerequisites: " + ", ".join(missing)
        )

    stats = JudgeStats()
    judge_fns: dict[str, JudgeFn] = {
        "deepseek-chat": make_deepseek_judge(
            deepseek_key, stats, base_url=key_of("DEEPSEEK_BASE_URL") or None
        ),
        "deepseek-reasoner": make_deepseek_reasoner_judge(
            deepseek_key, stats, base_url=key_of("DEEPSEEK_BASE_URL") or None
        ),
        "qwen-plus": make_qwen_model_judge(
            "qwen-plus",
            QWEN_PROSECUTOR_MODEL,
            dashscope_key,
            stats,
            base_url=key_of("DASHSCOPE_BASE_URL") or None,
        ),
        # Cross-vendor CLI seats. Opus arbitrates split / majority-review points
        # only (low volume). Codex/GPT prosecutes accepted points (per-point, so
        # its usage-cap abstention -> row downgrade is monitored via the manifest
        # adversarial_prosecutor_abstained count). Neither runs in mutation
        # replay, so CLI latency does not multiply across the 900+ mutation cases.
        "claude-opus-4-8": make_claude_judge("claude-opus-4-8", CLAUDE_MODELS["opus"], stats),
        "gpt-codex": make_codex_judge(stats),
    }
    return judge_fns, stats
