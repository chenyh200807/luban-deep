"""RTG9 异源分流门:相似度过阈才送异源;异源判等价才进可疑队列;只分流不当真值。"""
from __future__ import annotations

from deeptutor.services.construction_grading.case_light_practice_rtg9 import rtg9_triage


def _item(distractors):
    return {
        "correct_options": [{"text": "分层剥开旧卷材", "source_scoring_point_id": "a5"}],
        "distractors": distractors,
    }


def test_high_similarity_equivalent_distractor_flagged():
    # 干扰项"分层剥离旧卷材"与正确项高相似;异源判"也对"→ 进可疑队列。
    item = _item([{"text": "分层剥离旧卷材", "error_code": "E12"}])
    r = rtg9_triage(item, judge_fn=lambda d, c: True)
    assert r.has_suspects is True
    assert r.triaged_count == 1
    assert r.flagged[0].distractor_text == "分层剥离旧卷材"
    assert r.flagged[0].reason == "cross_source_equivalent"


def test_low_similarity_distractor_not_triaged():
    # 相似度低的干扰项根本不送异源(先便宜后贵)。
    item = _item([{"text": "用水泥砂浆抹平即可", "error_code": "E01"}])
    called = {"n": 0}

    def judge(d, c):
        called["n"] += 1
        return True

    r = rtg9_triage(item, judge_fn=judge)
    assert r.triaged_count == 0
    assert called["n"] == 0
    assert r.has_suspects is False


def test_suspect_but_cross_source_says_not_equivalent():
    # 高相似送异源,但异源判"不等价"→ 不 flag(只分流,采分点才是真值)。
    item = _item([{"text": "分层剥离旧卷材", "error_code": "E12"}])
    r = rtg9_triage(item, judge_fn=lambda d, c: False)
    assert r.triaged_count == 1
    assert r.has_suspects is False


def test_rtg9_only_sorts_never_scores():
    # 结构不变量:RTG9 不含任何分数/采分点改写字段,只产可疑清单。
    item = _item([{"text": "分层剥离旧卷材", "error_code": "E12"}])
    r = rtg9_triage(item, judge_fn=lambda d, c: True)
    # 报告只有分流信息,没有 awarded/score/official 字段
    assert not any("score" in f.lower() or "award" in f.lower() for f in vars(r))
    assert "只分流不当真值" in r.note
