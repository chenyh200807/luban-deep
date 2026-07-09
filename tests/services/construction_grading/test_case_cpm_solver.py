"""CPM solver golden tests.

Primary golden = the build-validated N01 network (its ES/EF/LS/LF/TF/FF were baked
into the rendered lesson SVG by an INDEPENDENT compute_cpm(); we assert our solver
reproduces every one). Not self-test: an independent implementation is the oracle.
Second case = a two-critical-path structure mirroring 真题 {2015,案例1}(T=25).
"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_cpm_solver import (
    Activity,
    CpmError,
    delay_affects_duration,
    grade_project_duration,
    matches_critical_path,
    solve_cpm,
    total_float_of,
)

# ── N01 golden network (durations + predecessors from the rendered SVG) ──
_N01 = [
    Activity("START", 0, ()),
    Activity("A", 3, ("START",)),
    Activity("B", 2, ("START",)),
    Activity("C", 4, ("A",)),
    Activity("D", 2, ("A", "B")),
    Activity("E", 3, ("C", "D")),
    Activity("END", 0, ("E",)),
]

# Official answer baked into the SVG (早 x-y / 迟 x-y / 总t/自由f):
#  A ES0 EF3 LS0 LF3 TF0 FF0 | B ES0 EF2 LS3 LF5 TF3 FF1 | C ES3 EF7 LS3 LF7 TF0 FF0
#  D ES3 EF5 LS5 LF7 TF2 FF2 | E ES7 EF10 LS7 LF10 TF0 FF0 | 总工期 10 | 关键 START-A-C-E-END
_EXPECTED = {
    "A": (0, 3, 0, 3, 0, 0, True),
    "B": (0, 2, 3, 5, 3, 1, False),
    "C": (3, 7, 3, 7, 0, 0, True),
    "D": (3, 5, 5, 7, 2, 2, False),
    "E": (7, 10, 7, 10, 0, 0, True),
}


def test_n01_golden_timings_match_svg_baked_answer():
    r = solve_cpm(_N01)
    for name, (es, ef, ls, lf, tf, ff, crit) in _EXPECTED.items():
        t = r.timings[name]
        assert (t.es, t.ef, t.ls, t.lf, t.total_float, t.free_float, t.critical) == (
            es, ef, ls, lf, tf, ff, crit
        ), f"activity {name} drifted from official: {t}"


def test_n01_project_duration_and_critical_path():
    r = solve_cpm(_N01)
    assert r.project_duration == 10
    assert r.critical_paths == (("START", "A", "C", "E", "END"),)
    assert r.critical_activities == frozenset({"START", "A", "C", "E", "END"})


def test_n01_critical_path_judging():
    r = solve_cpm(_N01)
    assert matches_critical_path(r, ["START", "A", "C", "E", "END"]) is True
    # the classic distractor: A-D-E (D has 2 float) is NOT critical
    assert matches_critical_path(r, ["START", "A", "D", "E", "END"]) is False
    assert grade_project_duration(r, 10) is True
    assert grade_project_duration(r, 9) is False


def test_n01_delay_judgment_uses_total_float():
    r = solve_cpm(_N01)
    # D has TF=2: delay 1 不影响, delay 3 影响
    assert delay_affects_duration(r, "D", 1) is False
    assert delay_affects_duration(r, "D", 2) is False
    assert delay_affects_duration(r, "D", 3) is True
    # A is critical (TF=0): any delay 影响总工期
    assert delay_affects_duration(r, "A", 1) is True
    assert total_float_of(r, "B") == 3


# ── Two parallel critical paths (真题 {2015,案例1} shape, T=25) ──
_TWO_CRIT = [
    Activity("START", 0, ()),
    Activity("A", 5, ("START",)),
    Activity("B", 7, ("A",)),
    Activity("D", 7, ("A",)),
    Activity("F", 5, ("B",)),
    Activity("G", 5, ("D",)),
    Activity("H", 4, ("F", "G")),
    Activity("I", 4, ("H",)),
    Activity("END", 0, ("I",)),
]


def test_two_parallel_critical_paths():
    r = solve_cpm(_TWO_CRIT)
    assert r.project_duration == 25
    assert set(r.critical_paths) == {
        ("START", "A", "B", "F", "H", "I", "END"),
        ("START", "A", "D", "G", "H", "I", "END"),
    }
    # both paths judged correct; a mixed non-path is not
    assert matches_critical_path(r, ["START", "A", "B", "F", "H", "I", "END"]) is True
    assert matches_critical_path(r, ["START", "A", "D", "G", "H", "I", "END"]) is True
    assert matches_critical_path(r, ["START", "A", "B", "G", "H", "I", "END"]) is False


def test_codex_sub_eps_false_critical_regression():
    # 2026-07-09 Codex 对抗核证伪:SHORT 的 TF≈5e-10 被绝对容差误判为关键。
    # 治本=强制整数工期,该网络在构造期即被拒(非整工期)。
    with pytest.raises(CpmError):
        solve_cpm([
            Activity("S", 0, ()),
            Activity("LONG", 1.0, ("S",)),
            Activity("SHORT", 0.9999999995, ("S",)),
        ])


def test_integer_near_tie_shorter_activity_is_not_critical():
    # 正控:整数工期下,并列较短工作(TF>0)绝不被误判为关键。
    r = solve_cpm([
        Activity("S", 0, ()),
        Activity("LONG", 2, ("S",)),
        Activity("SHORT", 1, ("S",)),
        Activity("END", 0, ("LONG", "SHORT")),
    ])
    assert r.timings["SHORT"].critical is False
    assert r.timings["SHORT"].total_float == 1
    assert r.critical_paths == (("S", "LONG", "END"),)


def test_malformed_networks_raise():
    with pytest.raises(CpmError):
        solve_cpm([Activity("A", 1, ("B",)), Activity("B", 1, ("A",))])  # cycle
    with pytest.raises(CpmError):
        solve_cpm([Activity("A", 1, ("ghost",))])  # unknown predecessor
    with pytest.raises(CpmError):
        solve_cpm([Activity("A", 1), Activity("A", 2)])  # duplicate
    with pytest.raises(CpmError):
        solve_cpm([])  # empty
