"""RAG retrieval quality eval — diagnostic baseline (P0-1, T2).

Single-file harness: IR metrics + golden loader + staleness preflight (1B) +
deterministic eval fixture (4A) + pytest gate. The gate emits a per-shape
Recall@K / MRR report with Wilson 95% CI (3A: honest about small-n).

Run the offline unit tests:
    pytest tests/services/rag/test_retrieval_quality.py -v

Run the e2e baseline (CI/staging — needs RAG_EVAL_KB_NAME + annotated golden):
    RAG_EVAL_KB_NAME=<kb> pytest tests/services/rag/test_retrieval_quality.py \
        -k baseline -v -s
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os

from _pytest.outcomes import Skipped
import pytest

# ── Metrics ────────────────────────────────────────────────────────────


def compute_recall_at_k(retrieved: list[str], expected: list[str], k: int) -> float:
    """Fraction of expected chunk_ids that appear in the top-k retrieved."""
    if not expected:
        return 0.0
    top = set(retrieved[:k])
    return sum(1 for e in expected if e in top) / len(expected)


def compute_mrr(retrieved: list[str], expected: list[str]) -> float:
    """Reciprocal rank of the earliest retrieved chunk that is expected."""
    exp = set(expected)
    for rank, cid in enumerate(retrieved, 1):
        if cid in exp:
            return 1.0 / rank
    return 0.0


def compute_wilson_ci(p_hat: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI for a proportion. 3A: honest reporting at n=12-20.

    Returns (0.0, 0.0) for n == 0 (never NaN).
    """
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ── Golden set ─────────────────────────────────────────────────────────

_VALID_SHAPES = {"concept_like", "mcq_like", "case_like", "standard_like", "calc_like"}
_REQUIRED_FIELDS = ("id", "query", "query_shape", "expected_chunk_ids", "annotator")


@dataclass(frozen=True)
class GoldenItem:
    id: str
    query: str
    query_shape: str  # one of _VALID_SHAPES
    expected_chunk_ids: list[str]
    annotator: str
    notes: str = ""


def load_golden_set(path: str) -> list[GoldenItem]:
    """Load + validate the expert-annotated golden set. Fails loud on bad rows."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    items: list[GoldenItem] = []
    for r in raw:
        for required in _REQUIRED_FIELDS:
            if required not in r:
                raise ValueError(f"golden item missing '{required}': {r.get('id', '?')}")
        if r["query_shape"] not in _VALID_SHAPES:
            raise ValueError(f"invalid query_shape: {r['query_shape']} (id={r.get('id', '?')})")
        if not isinstance(r["expected_chunk_ids"], list):
            raise ValueError(f"expected_chunk_ids must be a list (id={r.get('id', '?')})")
        items.append(
            GoldenItem(**{k: r[k] for k in r if k in GoldenItem.__annotations__})
        )
    return items


def collect_expected_chunk_ids(items: list[GoldenItem]) -> set[str]:
    return {cid for item in items for cid in item.expected_chunk_ids}


# ── Preflight staleness check (1B) ─────────────────────────────────────


class StaleGoldenSetError(RuntimeError):
    """Raised when golden expected_chunk_ids no longer exist in the KB."""


async def preflight_check_stale(
    items: list[GoldenItem],
    kb_name: str,
    *,
    pipeline=None,
) -> None:
    """1B: verify every expected chunk_id still exists in the KB.

    Stale set -> raise StaleGoldenSetError (CI red, list the gone ids).
    Supabase unreachable -> pytest.skip (infra, not a RAG failure).
    pipeline is injectable for tests; defaults to a real SupabasePipeline.
    """
    all_ids = collect_expected_chunk_ids(items)
    if not all_ids:
        return
    if pipeline is None:
        from deeptutor.services.rag.pipelines.supabase import SupabasePipeline

        pipeline = SupabasePipeline()
    try:
        existing = await pipeline.check_chunk_ids_exist(sorted(all_ids), kb_name)
    except StaleGoldenSetError:
        raise
    except Exception as exc:  # infra: Supabase down / misconfigured
        pytest.skip(f"Supabase unreachable for preflight: {exc}")
        return
    missing = all_ids - set(existing)
    if missing:
        ordered = sorted(missing)
        raise StaleGoldenSetError(
            f"Golden set stale: {len(missing)}/{len(all_ids)} chunk_ids missing in KB "
            f"'{kb_name}'. First 5: {ordered[:5]}. "
            f"Re-annotate golden set or check KB reindex history."
        )


# ── Eval fixture: deterministic mode (4A) ──────────────────────────────


@contextmanager
def _eval_fixture():
    """4A: turn rerank OFF during eval; measure pure RRF retrieval quality.

    rerank is high-variance LLM-based; its noise swamps the small-move signal
    the eval is meant to detect. Eval measures retrieval, not rerank.
    """
    overrides = {"SUPABASE_RAG_ENABLE_RERANK": "false"}
    old = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── Result extraction + reporting ──────────────────────────────────────


def _extract_retrieved_chunk_ids(out: dict) -> list[str]:
    """Ranked chunk_ids from a RAGService.search payload.

    The retrieval order lives in the top-level ``sources`` list (chunk_id per
    item, ranked); evidence_bundle.sources mirrors it. NOTE: content_blocks is
    rendered text, NOT chunk dicts — do not read chunk_id from there.
    """
    sources = out.get("sources")
    if not sources:
        sources = (out.get("evidence_bundle") or {}).get("sources") or []
    return [
        str(s.get("chunk_id")).strip()
        for s in sources
        if isinstance(s, dict) and str(s.get("chunk_id") or "").strip()
    ]


def _format_baseline_report(results: list[tuple[GoldenItem, list[str]]], k: int = 5) -> str:
    """Per-shape Recall@k / MRR with Wilson 95% CI (3A honest small-n note)."""
    by_shape: dict[str, list[tuple[GoldenItem, list[str]]]] = {}
    for item, retrieved in results:
        by_shape.setdefault(item.query_shape, []).append((item, retrieved))

    lines = ["", "=" * 60, "RAG Retrieval Quality Baseline", "=" * 60]
    for shape, group in sorted(by_shape.items()):
        n = len(group)
        recalls = [compute_recall_at_k(r, i.expected_chunk_ids, k) for i, r in group]
        mrrs = [compute_mrr(r, i.expected_chunk_ids) for i, r in group]
        r_mean = sum(recalls) / n
        mrr_mean = sum(mrrs) / n
        r_lo, r_hi = compute_wilson_ci(r_mean, n)
        lines.append(
            f"  {shape:14s} n={n:3d}  Recall@{k}={r_mean:.3f} "
            f"[CI {r_lo:.2f}, {r_hi:.2f}]  MRR={mrr_mean:.3f}"
        )
    lines.append("=" * 60)
    if by_shape:
        sizes = [len(g) for g in by_shape.values()]
        lines.append(
            f"NOTE: Wilson 95% CI. n={min(sizes)}-{max(sizes)} per shape — "
            f"only detects >=15pp moves reliably (3A)."
        )
    return "\n".join(lines)


# ── Fixtures ───────────────────────────────────────────────────────────

_GOLDEN_PATH = "tests/fixtures/rag_retrieval_golden_v1.json"


@pytest.fixture
def rag_kb_name() -> str:
    kb = os.getenv("RAG_EVAL_KB_NAME", "").strip()
    if not kb:
        pytest.skip("RAG_EVAL_KB_NAME not set — e2e baseline runs in CI/staging only")
    return kb


# ── Test doubles ───────────────────────────────────────────────────────


class _FakePipeline:
    def __init__(self, existing: set[str]) -> None:
        self._existing = set(existing)

    async def check_chunk_ids_exist(self, chunk_ids: list[str], kb_name: str) -> set[str]:
        return {c for c in chunk_ids if c in self._existing}


class _FailingPipeline:
    async def check_chunk_ids_exist(self, chunk_ids: list[str], kb_name: str) -> set[str]:
        from deeptutor.services.rag.exceptions import RAGSearchError

        raise RAGSearchError(
            "supabase down", provider="supabase", stage="pipeline.select", retryable=True
        )


def _golden(id_: str, shape: str, expected: list[str]) -> GoldenItem:
    return GoldenItem(
        id=id_, query=f"q-{id_}", query_shape=shape,
        expected_chunk_ids=expected, annotator="tester",
    )


# ── Unit tests: metrics ────────────────────────────────────────────────


def test_recall_at_k_all_expected_in_topk():
    assert compute_recall_at_k(["a", "b", "c"], ["a", "b"], 5) == 1.0


def test_recall_at_k_partial():
    assert compute_recall_at_k(["a", "b", "c"], ["a", "x"], 5) == 0.5


def test_recall_at_k_respects_k_cutoff():
    assert compute_recall_at_k(["a", "b", "c", "d"], ["d"], 3) == 0.0


def test_recall_at_k_empty_expected_is_zero():
    assert compute_recall_at_k(["a"], [], 5) == 0.0


def test_recall_at_k_empty_retrieved_is_zero():
    assert compute_recall_at_k([], ["a"], 5) == 0.0


def test_mrr_first_rank_is_one():
    assert compute_mrr(["a", "b", "c"], ["a"]) == 1.0


def test_mrr_second_rank_is_half():
    assert compute_mrr(["a", "b", "c"], ["b"]) == 0.5


def test_mrr_no_hit_is_zero():
    assert compute_mrr(["a", "b"], ["z"]) == 0.0


def test_mrr_uses_earliest_retrieved_expected():
    # b is at rank 2, c at rank 3; earliest expected hit wins
    assert compute_mrr(["a", "b", "c"], ["c", "b"]) == 0.5


def test_wilson_ci_zero_n_is_zero():
    assert compute_wilson_ci(0.0, 0) == (0.0, 0.0)


def test_wilson_ci_known_value():
    lo, hi = compute_wilson_ci(0.5, 20)
    assert lo == pytest.approx(0.299, abs=0.01)
    assert hi == pytest.approx(0.701, abs=0.01)


def test_wilson_ci_bounds_are_clamped():
    lo, hi = compute_wilson_ci(1.0, 20)
    assert 0.0 <= lo <= hi <= 1.0


# ── Unit tests: golden loader ──────────────────────────────────────────


def _write_json(tmp_path, payload) -> str:
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_load_golden_set_parses_valid(tmp_path):
    path = _write_json(tmp_path, [
        {"id": "1", "query": "防水等级", "query_shape": "standard_like",
         "expected_chunk_ids": ["a", "b"], "annotator": "expert-1", "notes": "why"},
    ])
    items = load_golden_set(path)
    assert len(items) == 1
    assert items[0].query_shape == "standard_like"
    assert items[0].expected_chunk_ids == ["a", "b"]
    assert items[0].notes == "why"


def test_load_golden_set_missing_field_raises(tmp_path):
    path = _write_json(tmp_path, [
        {"id": "1", "query": "q", "query_shape": "concept_like",
         "expected_chunk_ids": ["a"]},  # missing annotator
    ])
    with pytest.raises(ValueError, match="annotator"):
        load_golden_set(path)


def test_load_golden_set_invalid_shape_raises(tmp_path):
    path = _write_json(tmp_path, [
        {"id": "1", "query": "q", "query_shape": "bogus_like",
         "expected_chunk_ids": ["a"], "annotator": "x"},
    ])
    with pytest.raises(ValueError, match="invalid query_shape"):
        load_golden_set(path)


def test_collect_expected_chunk_ids_dedupes_across_items():
    items = [_golden("1", "concept_like", ["a", "b"]),
             _golden("2", "mcq_like", ["b", "c"])]
    assert collect_expected_chunk_ids(items) == {"a", "b", "c"}


# ── Unit tests: preflight (1B) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_preflight_passes_when_all_chunks_exist():
    fake = _FakePipeline({"a", "b"})
    await preflight_check_stale([_golden("1", "concept_like", ["a", "b"])], "kb", pipeline=fake)


@pytest.mark.asyncio
async def test_preflight_raises_stale_when_chunk_missing():
    fake = _FakePipeline({"a"})  # "b" gone after reindex
    with pytest.raises(StaleGoldenSetError) as exc:
        await preflight_check_stale(
            [_golden("1", "concept_like", ["a", "b"])], "kb", pipeline=fake
        )
    assert "b" in str(exc.value)
    assert "1/2" in str(exc.value)


@pytest.mark.asyncio
async def test_preflight_skips_on_infra_error():
    with pytest.raises(Skipped):
        await preflight_check_stale(
            [_golden("1", "concept_like", ["a"])], "kb", pipeline=_FailingPipeline()
        )


@pytest.mark.asyncio
async def test_preflight_noop_on_empty_items():
    fake = _FakePipeline(set())
    await preflight_check_stale([], "kb", pipeline=fake)  # no raise, no skip


# ── Unit tests: eval fixture (4A) ──────────────────────────────────────


def test_eval_fixture_disables_rerank_and_restores_absent(monkeypatch):
    monkeypatch.delenv("SUPABASE_RAG_ENABLE_RERANK", raising=False)
    with _eval_fixture():
        assert os.environ["SUPABASE_RAG_ENABLE_RERANK"] == "false"
    assert "SUPABASE_RAG_ENABLE_RERANK" not in os.environ


def test_eval_fixture_restores_prior_value(monkeypatch):
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "true")
    with _eval_fixture():
        assert os.environ["SUPABASE_RAG_ENABLE_RERANK"] == "false"
    assert os.environ["SUPABASE_RAG_ENABLE_RERANK"] == "true"


# ── Unit tests: extraction + reporting ─────────────────────────────────


def test_extract_chunk_ids_preserves_ranked_order():
    out = {"sources": [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]}
    assert _extract_retrieved_chunk_ids(out) == ["a", "b", "c"]


def test_extract_chunk_ids_falls_back_to_evidence_bundle():
    out = {"evidence_bundle": {"sources": [{"chunk_id": "x"}, {"chunk_id": "y"}]}}
    assert _extract_retrieved_chunk_ids(out) == ["x", "y"]


def test_extract_chunk_ids_skips_blank_and_non_dicts():
    out = {"sources": [{"chunk_id": ""}, {"chunk_id": "a"}, {"foo": 1}, "junk"]}
    assert _extract_retrieved_chunk_ids(out) == ["a"]


def test_format_baseline_report_includes_per_shape_metrics():
    results = [
        (_golden("1", "concept_like", ["a"]), ["a", "b"]),   # hit @1
        (_golden("2", "concept_like", ["z"]), ["a", "b"]),   # miss
    ]
    report = _format_baseline_report(results)
    assert "concept_like" in report
    assert "Recall@5" in report
    assert "CI" in report
    assert "MRR" in report
    assert "n=  2" in report


def test_format_baseline_report_empty_is_safe():
    report = _format_baseline_report([])
    assert "RAG Retrieval Quality Baseline" in report


# ── E2E pytest gate ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rag_retrieval_quality_baseline(rag_kb_name):
    """Diagnostic baseline gate — emits a per-shape report to stdout + artifact.

    Skips cleanly until its inputs exist: needs RAG_EVAL_KB_NAME (fixture) and
    the annotated golden set (T3). Failure modes: stale golden set ->
    StaleGoldenSetError (1B, CI red); Supabase down -> skip (infra, not RAG).
    """
    if not os.path.exists(_GOLDEN_PATH):
        pytest.skip(f"golden set not yet annotated (T3): {_GOLDEN_PATH}")

    items = load_golden_set(_GOLDEN_PATH)
    await preflight_check_stale(items, rag_kb_name)

    from deeptutor.services.rag.service import RAGService

    results: list[tuple[GoldenItem, list[str]]] = []
    with _eval_fixture():
        svc = RAGService()
        for item in items:
            out = await svc.search(query=item.query, kb_name=rag_kb_name)
            results.append((item, _extract_retrieved_chunk_ids(out)))

    report = _format_baseline_report(results)
    print(report)
    os.makedirs("artifacts/rag_eval", exist_ok=True)
    sha = os.getenv("GIT_SHA", "local")
    with open(f"artifacts/rag_eval/baseline_{sha}.md", "w", encoding="utf-8") as f:
        f.write(report)

    assert results, "golden set produced no results"
