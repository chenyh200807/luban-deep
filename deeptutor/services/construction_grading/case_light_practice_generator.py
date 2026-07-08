"""Case light-practice runtime generator (点选题) — LLM as an injected seam.

设计(§1限制③ + §4 红线):
  - **correct 选项 = 采分点 statement 逐字**(确定性),LLM **只生成干扰项 + error_code**。
    "LLM 只写措辞、绝不碰真值":正确项由真采分点直接兑现,天然过 RTG8,把编造面
    压到最小;LLM 的活是"造采分点可辨识的错误变形 + 归错因"。
  - LLM 调用是**注入式 seam**(`complete_fn: Callable[[str], str]`):单测注入 stub 纯
    验证编排;阿里云注入真 DeepSeek(base_url pin deepseek + temperature=0,见 §7)。
    本模块不 import 任何 LLM 客户端 —— 保持纯编排、可测。
  - 出题后过 `run_post_gen_gates`(RTG1–RTG8);BLOCK→重生成 ≤`max_regen`;仍 BLOCK→
    降级(degraded,不出给学员)。
  - **qid 门**:非 `dev_fixture` 调用必过 `assert_qid_allowed`(未过教研验收的 qid
    代码层拒绝);`dev_fixture=True` 仅用于内部 demo/build,`official_score_allowed=false`。

Deterministic orchestration; the ONLY nondeterminism is the injected complete_fn.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
    assert_qid_allowed,
)
from deeptutor.services.construction_grading.case_light_practice_rtg import (
    PostGenReport,
    Verdict,
    run_post_gen_gates,
)

CompleteFn = Callable[[str], str]

# Case-series error codes the generator may offer the LLM (RTG3/RTG4 pre-screen).
_CASE_ERROR_CODES = tuple(c for c, spec in ERROR_CODE_REGISTRY.items() if spec.get("series") == "E")


class GenStatus(str, Enum):
    OK = "ok"  # verdict PASS
    SOFT = "soft"  # verdict SOFT_FAIL → 可疑队列
    NEEDS_HUMAN = "needs_human"  # RTG3 NEEDS_REVIEW
    DEGRADED = "degraded"  # all attempts BLOCK → do not serve


@dataclass(frozen=True)
class GenerationResult:
    status: GenStatus
    item: dict | None
    report: PostGenReport | None
    attempts: int


# ── Dev fixture loading (DEV ONLY — never production supply) ────────────────────

_DEV_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "runtime_supply" / "case_light_practice" / "dev_fixtures"
)


def load_dev_fixture(name: str) -> tuple[str, list[LubanCaseScoringPoint]]:
    """Load a DEV fixture (e.g. ``F16_qigu_gebu``) → (qid, points).

    Refuses a fixture that does not declare ``dev_fixture: true`` +
    ``official_score_allowed: false`` — a dev harness must never accidentally
    load a production-claiming artifact.
    """
    path = _DEV_FIXTURE_DIR / f"{name}.dev.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("dev_fixture") or data.get("official_score_allowed") is not False:
        raise ValueError(f"{path} is not a valid dev fixture (dev_fixture/official_score_allowed)")
    qid = str(data["source_qid"])
    points = [_point_from_dict(p) for p in data.get("points") or []]
    return qid, points


def _point_from_dict(p: dict) -> LubanCaseScoringPoint:
    ref = SourceRef("exam_reference_answer", p.get("qid", ""))
    return LubanCaseScoringPoint(
        point_id=str(p["point_id"]),
        sub_no=str(p.get("sub_no", "")),
        qid=str(p["qid"]),
        sub_qid=str(p.get("sub_qid", p["qid"])),
        statement=str(p["statement"]),
        authority_source="official_answer",
        point_type=PointType(p.get("point_type", "程序")),
        required_terms=tuple(p.get("required_terms") or ()),
        acceptable_variants=(AcceptableVariant(str(p["statement"]), ref),),
        max_score=float(p.get("max_score", 0.0)),
        textbook_source_refs=(ref,),
        answer_key_authority="exam_reference_answer",
    )


# ── Prompt (LLM produces distractors ONLY) ─────────────────────────────────────


def build_distractor_prompt(
    target: LubanCaseScoringPoint,
    all_points: Sequence[LubanCaseScoringPoint],
    *,
    num_distractors: int,
    error_code_candidates: Sequence[str],
) -> str:
    code_menu = "\n".join(
        f"  - {c}: {ERROR_CODE_REGISTRY[c]['label']}" for c in error_code_candidates if c in ERROR_CODE_REGISTRY
    )
    other = "\n".join(f"  - {p.statement}" for p in all_points if p.point_id != target.point_id)
    return (
        "你在为一建建筑实务案例题出一道『命中采分点』点选题。正确项已给定(采分点原文),\n"
        "你只需生成迷惑性干扰项——每个干扰项必须是**采分点的可辨识错误变形**:\n"
        "禁止与正确项字面相同、禁止『其实也对』、禁止只加『不』做廉价反转。\n\n"
        f"【正确采分点(不要改写)】{target.statement}\n"
        f"【本小问其它真采分点(不可当干扰项)】\n{other or '  (无)'}\n\n"
        f"【可选错因码(每个干扰项选一个;拿不准填 NEEDS_REVIEW)】\n{code_menu}\n\n"
        f"输出严格 JSON:{{\"distractors\":[{{\"text\":\"...\",\"error_code\":\"E0X\"}}]}},共 {num_distractors} 个。只输出 JSON。"
    )


def _parse_distractors(raw: str) -> list[dict]:
    """Parse the LLM completion into a distractor list. Tolerates code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.lstrip("json").strip().strip("`").strip()
    # find first { ... last }
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in completion: {raw[:120]!r}")
    obj = json.loads(s[start : end + 1])
    return list(obj.get("distractors") or [])


# ── Generator ──────────────────────────────────────────────────────────────────


def generate_point_select_item(
    points: Sequence[LubanCaseScoringPoint],
    *,
    complete_fn: CompleteFn,
    target_point_id: str | None = None,
    qid: str | None = None,
    dev_fixture: bool = False,
    num_distractors: int = 3,
    max_regen: int = 2,
    error_code_candidates: Iterable[str] | None = None,
    consistent_point_ids: Iterable[str] | None = None,
) -> GenerationResult:
    """Generate one 点选题 whose correct option is a scoring point原文 verbatim.

    Non-dev callers MUST supply a whitelisted ``qid`` (``assert_qid_allowed``);
    ``dev_fixture=True`` bypasses the whitelist for internal demos only.
    """
    if not points:
        raise ValueError("no scoring points supplied")
    if not dev_fixture:
        if qid is None:
            raise ValueError("qid required for non-dev generation")
        assert_qid_allowed(qid)  # raises WhitelistError if未过教研验收

    target = next((p for p in points if p.point_id == target_point_id), points[0])
    candidates = list(error_code_candidates) if error_code_candidates is not None else list(_CASE_ERROR_CODES)
    prompt = build_distractor_prompt(
        target, points, num_distractors=num_distractors, error_code_candidates=candidates
    )

    last_report: PostGenReport | None = None
    attempts = 0
    for attempts in range(1, max_regen + 2):
        try:
            distractors = _parse_distractors(complete_fn(prompt))
        except (ValueError, json.JSONDecodeError):
            continue  # unparseable → regenerate
        item = {
            "stem": f"关于『{target.sub_no or target.qid}』,下列哪一项是正确的采分点?",
            "correct_options": [
                {"text": target.statement, "source_scoring_point_id": target.point_id}
            ],
            "distractors": distractors,
        }
        report = run_post_gen_gates(
            item,
            points,
            error_code_candidates=candidates,
            consistent_point_ids=consistent_point_ids,
        )
        last_report = report
        if report.verdict != Verdict.BLOCK:
            status = {
                Verdict.PASS: GenStatus.OK,
                Verdict.SOFT_FAIL: GenStatus.SOFT,
                Verdict.NEEDS_HUMAN: GenStatus.NEEDS_HUMAN,
            }[report.verdict]
            return GenerationResult(status=status, item=item, report=report, attempts=attempts)

    return GenerationResult(status=GenStatus.DEGRADED, item=None, report=last_report, attempts=attempts)


__all__ = [
    "CompleteFn",
    "GenStatus",
    "GenerationResult",
    "load_dev_fixture",
    "build_distractor_prompt",
    "generate_point_select_item",
]
