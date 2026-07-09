"""RTG9 —— 异源分流门(§1限制③ 第 9 道)。

确定性门(RTG1-8)判不了"干扰项其实也对 / 语义等价"。RTG9 只对**相似度过阈**的
干扰项,交**异源模型(非 DeepSeek 生成器;用 Qwen/dashscope 换厂)**批量判别
"这个干扰项是不是也对/和正确项语义等价?"——命中 → **进可疑队列**。

铁律:**只分流,不当真值**(§4 红线:LLM 不得越权当 ground truth)。采分点原文才是
真值;RTG9 既不改分、也不改采分点,只把可疑干扰项挑出来交人工/后续处理。异源判别是
**注入 seam**(`judge_fn`):单测注入 stub,阿里云注入真 Qwen(dashscope)。

先便宜后贵:先用确定性相似度过滤(只对像的才送异源),不把每个干扰项都送 LLM。
Deterministic orchestration;唯一非确定性是注入的 judge_fn。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from deeptutor.services.construction_grading.case_light_practice_rtg import normalize

# 异源语义判别函数:(干扰项文本, 正确项文本) -> True 表示"也对/语义等价"(可疑)。
CrossSourceJudge = Callable[[str, str], bool]

_DEFAULT_SUSPECT_THRESHOLD = 0.5  # 相似度过阈才送异源(Jaccard on normalized chars)


def _similarity(a: str, b: str) -> float:
    ta, tb = set(normalize(a)), set(normalize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass(frozen=True)
class RTG9Flag:
    distractor_text: str
    correct_text: str
    similarity: float
    reason: str  # "cross_source_equivalent" —— 异源判为也对/语义等价


@dataclass(frozen=True)
class RTG9Report:
    flagged: tuple[RTG9Flag, ...]   # 进可疑队列的干扰项(只分流)
    triaged_count: int              # 送异源判别的干扰项数(相似度过阈的)
    note: str = "RTG9 只分流不当真值;采分点原文才是真值"

    @property
    def has_suspects(self) -> bool:
        return bool(self.flagged)


def rtg9_triage(
    item: Mapping[str, object],
    *,
    judge_fn: CrossSourceJudge,
    suspect_threshold: float = _DEFAULT_SUSPECT_THRESHOLD,
) -> RTG9Report:
    """对 item 的每个干扰项:与任一正确项相似度过阈 → 送异源 judge_fn 判"是否也对";
    异源判为等价 → flag 进可疑队列。**只分流**,不改分不改采分点。"""
    correct = [str((o or {}).get("text", "")) for o in (item.get("correct_options") or [])]
    correct = [c for c in correct if c]
    distractors = [str((d or {}).get("text", "")) for d in (item.get("distractors") or [])]
    distractors = [d for d in distractors if d]

    flagged: list[RTG9Flag] = []
    triaged = 0
    for d in distractors:
        # 取与它最像的正确项
        best_c, best_sim = "", 0.0
        for c in correct:
            s = _similarity(d, c)
            if s > best_sim:
                best_c, best_sim = c, s
        if best_c and best_sim >= suspect_threshold:
            triaged += 1
            if judge_fn(d, best_c):  # 异源判为"也对/语义等价"
                flagged.append(RTG9Flag(d, best_c, round(best_sim, 3), "cross_source_equivalent"))
    return RTG9Report(flagged=tuple(flagged), triaged_count=triaged)


__all__ = ["CrossSourceJudge", "RTG9Flag", "RTG9Report", "rtg9_triage"]
