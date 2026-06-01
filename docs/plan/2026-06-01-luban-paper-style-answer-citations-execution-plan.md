# Luban Paper-Style Answer Citations Implementation Plan v1.1

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every user-visible final answer carries a server-generated citation state; every knowledge-bearing claim in teaching, grading, weak-point diagnosis, and next-step recommendation is traceable to a public-safe textbook / standard / question / learner-evidence source.

**Architecture:** Do not build a generic Nexus-like platform. Add a thin public citation projection over existing authorities: `RAGService.evidence_bundle`, source compiler spans, exact-question metadata, post-submit construction-grading evidence, and learning-evidence refs. The citation layer formats, redacts, validates, and audits final answers; it never scores, routes, rewrites learner state, or creates a second RAG authority.

**Tech Stack:** Python dataclasses, existing `StreamBus.sources`, existing `/api/v1/ws` result payloads, `RAGService.evidence_bundle`, `deeptutor/services/source_compiler/**`, `deeptutor/services/construction_grading/**`, pytest, benchmark shadow gate, `/wechat-harness`, `yousenwebview/packageDeeptutor`.

## Implementation Status — 2026-06-01

**Status:** local shadow implementation completed; production enablement is still blocked by human citation audit, WeChat DevTools / true mini-program regression, and live observability sampling.

Completed in this implementation:

1. Added `deeptutor/services/citations/` as the single citation projection authority for schema, source normalization, deterministic footer formatting, answer assembly, hidden-authority redaction, and quality validation.
2. Integrated citation assembly behind `DEEPTUTOR_ANSWER_CITATIONS_ENABLED` in `AgenticChatPipeline`, `TutorBotCapability`, and post-submit `DeepQuestionCapability`, with canonical `result.metadata.response` carrying the final cited response and `citation_bundle`.
3. Preserved compact public provenance fields in `RAGService.evidence_bundle.sources` via the Supabase pipeline: `source_id`, `source_table`, `stable_id`, `source_span`, `content_hash`, `quote_hash`, chapter, section, title/source type, and standard/article locators.
4. Added contract coverage for `result.metadata.citation_bundle` and RAG citation identity fields.
5. Added citation accuracy shadow benchmark fixture/helper and registered `answer_citation_shadow` as a non-gate benchmark suite.
6. Added WeChat / yousen renderer regression coverage to keep `〔n〕` markers and the final `依据` section visible as normal prose.

Verified locally:

```bash
pytest tests/services/citations tests/agents/chat/test_answer_citations.py tests/capabilities/test_tutorbot_answer_citations.py tests/capabilities/test_deep_question_answer_citations.py tests/api/test_unified_ws_answer_citations.py tests/api/test_unified_ws_public_redaction.py tests/services/rag/test_rag_pipelines.py::test_supabase_search_emits_evidence_bundle_and_respects_routing_metadata tests/services/rag/test_rag_pipelines.py::test_supabase_search_dedupes_duplicate_rendered_content_and_sources tests/services/benchmark/test_registry.py tests/services/benchmark/test_answer_citation_audit.py -q
node wx_miniprogram/tests/test_ai_message_state.js
node wx_miniprogram/tests/test_renderer_parity.js
node yousenwebview/tests/test_question_review_readonly_mcq.js
python -m compileall -q deeptutor/services/citations deeptutor/services/benchmark/answer_citation_audit.py deeptutor/agents/chat/agentic_pipeline.py deeptutor/capabilities/tutorbot.py deeptutor/capabilities/deep_question.py deeptutor/services/rag/pipelines/supabase.py
```

Not completed, and must remain production blockers:

1. 50-answer human citation audit and >=95% production citation accuracy sign-off.
2. WeChat DevTools / true mini-program regression after automated renderer tests.
3. Live Langfuse / ClickHouse citation metrics sampling after enabling the feature flag in a shadow environment.

---

## 0. v1.1 Review Fixes

This revision replaces v1 because the first draft had five execution blockers:

1. `deeptutor/services/citations/__init__.py` imported `assembler` before `assembler.py` existed.
2. The assembler only appended one marker at the end of the full answer; it did not support claim-level or paragraph-level evidence.
3. The chat integration test used nonexistent `StreamBus.history()` and the wrong `result.metadata["result"]["response"]` nesting.
4. Streaming could expose an uncited body before citations were assembled, leaving UI and canonical result out of sync.
5. The benchmark checked citation syntax, not citation accuracy against expected source ids / spans.

v1.1 makes those fixes mandatory before implementation starts.

## 1. Product Contract

### 1.1 Final Answer Shape

Knowledge-bearing answer:

```markdown
屋面防水等级应先按工程重要性、使用功能和渗漏后果确定〔1〕。案例题采分时，还要写出设防要求、材料和节点处理这些可判分要素〔2〕。

依据
〔1〕2026 建筑实务教材，防水工程 > 屋面防水等级，source_id=book_2026_roof_001，span=chapter:1.4.2，hash=...
〔2〕2023 一建建筑实务真题 Q4-2 评分点，source_id=question_2023_case_04，rubric_point=p2，hash=...
```

Non-knowledge answer:

```markdown
你好，我可以帮你复习。

依据
本轮未使用可公开引用的教材、规范、题库或学习证据；以上内容仅为通用对话说明，不进入学习事实或评分依据。
```

Rules:

1. Inline marker is `〔n〕`, not HTML superscript, so web, markdown, and WeChat render consistently.
2. Final section title is exactly `依据`.
3. Every final result has `citation_state`, even when no public source is used.
4. Full footnotes are required for knowledge-bearing claims; non-knowledge answers use the compact no-public-source footer.
5. If a claim cannot be cited, do not invent a source. Remove the claim, downgrade it to advice, or emit `citation_state=no_public_source`.
6. Public citations must never expose hidden grading authority before submit: `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, full private rubric, or private learner profile.

### 1.2 World-Class Gate

| Gate | Shadow target | Production target |
| --- | ---: | ---: |
| Final-answer citation state coverage | 100% answers | 100% answers |
| Knowledge-bearing claim citation coverage | >= 90% | >= 97% |
| Citation accuracy against expected source id/span | >= 90% | >= 95% |
| Hidden-authority leak rate | 0 | 0 |
| Orphan marker rate (`〔n〕` without footer row) | 0 | 0 |
| Footer row without visible marker | 0 for public rows | 0 for public rows |
| UI/canonical result mismatch | 0 sampled turns | 0 sampled turns |

## 2. Single Authority

One business fact:

> A public final answer is allowed to make a knowledge, grading, weak-point, or prescription claim only when that claim is traceable to a public-safe source ref, or explicitly marked non-authoritative / uncited.

Canonical authorities:

| Fact | Authority | Citation projection |
| --- | --- | --- |
| Online grounding | `RAGService.evidence_bundle` | `CitationSourceRef` |
| Source identity and span | source compiler / Supabase source metadata | `source_id`, `source_table`, `stable_id`, `source_span`, `content_hash` |
| Grading result | `CaseGradingSkillKernel` / post-submit `construction_grading_result` | public post-submit evidence refs only |
| Weak-point truth | `LearnerStateService` / learning synthesis | cited L1/L2 supporting event refs |
| Final answer | capability result payload `response` | cited canonical response |
| Public stream sources | `StreamBus.sources` | same public-safe citation refs |

Competing authorities to reject:

1. Prompt-only footnotes with no source id or locator.
2. Frontend-rendered citations reconstructed from plain text.
3. A second RAG lookup path just for citations.
4. A citation layer that changes scores, routes, standard answers, or learner state.
5. Copying private grading artifacts into public citation rows.

## 3. Source Readiness Gate

Do this before writing the citation package. If the source fields do not exist in live outputs, fix provenance first.

- [ ] **Step 3.1: Run source readiness audit**

Create a temporary script only if no existing fixture exposes these samples. The script must print 20 RAG / exact-question / grading / learning-evidence source records and verify these compact fields:

```text
source_type
title
source_id or stable_id
source_table when available
source_span or locator
content_hash when available
quote_hash when available
visibility/public-safe status
```

Run:

```bash
pytest \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/rag/test_provenance.py \
  tests/services/construction_grading/test_case_grading_kernel.py \
  -q
```

Expected:

```text
all selected tests pass, and sampled source payloads have enough public locator fields for citations
```

Stop condition:

```text
If most sampled RAG sources only contain flattened text/snippet without source_id/span/hash, implement Task 9 before Tasks 5-8.
```

## 4. File Structure

Create:

- `deeptutor/services/citations/__init__.py`
  Exports only completed modules for each task. During Task 5 it exports schema only; formatter/assembler are exported after those files exist.
- `deeptutor/services/citations/schema.py`
  Dataclasses for `CitationPolicy`, `CitationSourceRef`, `CitedClaim`, `CitationBundle`, and `CitedAnswer`.
- `deeptutor/services/citations/normalizer.py`
  Converts RAG sources, exact-question metadata, source compiler spans, construction-grading public evidence refs, and learning-evidence refs into public-safe `CitationSourceRef`.
- `deeptutor/services/citations/formatter.py`
  Deterministic marker and `依据` footer rendering.
- `deeptutor/services/citations/assembler.py`
  Builds paragraph/list-item level cited claims, inserts markers, appends footer, and returns `CitedAnswer`.
- `deeptutor/services/citations/quality.py`
  Validates hidden leaks, orphan markers, footer-marker consistency, and compact metadata.
- `deeptutor/services/benchmark/answer_citation_audit.py`
- `tests/fixtures/answer_citation_eval_cases.json`
- `tests/services/citations/test_schema.py`
- `tests/services/citations/test_normalizer.py`
- `tests/services/citations/test_formatter.py`
- `tests/services/citations/test_assembler.py`
- `tests/services/citations/test_quality.py`
- `tests/agents/chat/test_answer_citations.py`
- `tests/capabilities/test_tutorbot_answer_citations.py`
- `tests/capabilities/test_deep_question_answer_citations.py`
- `tests/api/test_unified_ws_answer_citations.py`
- `tests/services/benchmark/test_answer_citation_audit.py`

Modify:

- `deeptutor/agents/chat/agentic_pipeline.py`
  Assemble cited final responses in `_emit_sources_and_result(...)` before `_emit_result(...)`. Store `citation_bundle` directly in result metadata.
- `deeptutor/capabilities/tutorbot.py`
  Collect public tool sources, assemble the canonical final `visible_response`, and ensure the UI receives either the full final cited response or a citation suffix delta plus a canonical replacement result.
- `deeptutor/capabilities/deep_question.py`
  Assemble post-submit explanation citations using `grading_grounding_sources` and post-submit public evidence refs; never expose hidden grading keys.
- `deeptutor/services/rag/pipelines/supabase.py`
  Preserve compact source-span metadata in `evidence_bundle.sources` when present.
- `deeptutor/services/rag/service.py`
  Ensure fallback `evidence_bundle` still exposes source refs for citation normalization.
- `contracts/turn.md`
  Register `citation_bundle` / `citation_state` as final-answer public metadata and define canonical result behavior.
- `contracts/rag.md`
  Clarify that `evidence_bundle.sources` must preserve compact source identity fields.
- `contracts/index.yaml`
  Add citation tests to turn and rag domains when protected files change.
- `docs/plan/INDEX.md`
  Mark this plan as `Proposed v1.1`.

## 5. Task 0: Baseline And Contract Check

**Files:**
- Read: `CONTRACT.md`
- Read: `contracts/turn.md`
- Read: `contracts/rag.md`
- Read: `docs/plan/INDEX.md`

- [ ] **Step 0.1: Confirm current branch and dirty files**

Run:

```bash
git status --short --branch
```

Expected:

```text
Current branch and dirty files are visible. Do not reset, stash, or include unrelated files.
```

- [ ] **Step 0.2: Run targeted baseline tests**

Run:

```bash
pytest \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/rag/test_provenance.py \
  tests/agents/chat/test_agentic_parallel_tools.py \
  tests/core/test_capabilities_runtime.py \
  tests/api/test_unified_ws_public_redaction.py \
  -q
```

Expected:

```text
all selected tests pass
```

If baseline fails, stop and fix the pre-existing authority path first. Do not build citations on a broken RAG / turn / redaction baseline.

## 6. Task 1: Citation Schema

**Files:**
- Create: `deeptutor/services/citations/__init__.py`
- Create: `deeptutor/services/citations/schema.py`
- Test: `tests/services/citations/test_schema.py`

- [ ] **Step 1.1: Write schema tests**

Create `tests/services/citations/test_schema.py`:

```python
from deeptutor.services.citations.schema import (
    CitationBundle,
    CitationPolicy,
    CitationSourceRef,
    CitedClaim,
)


def test_public_ref_dict_is_compact_and_stable() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="textbook",
        title="2026 建筑实务教材",
        locator="防水工程 > 屋面防水等级",
        source_id="book_2026_001",
        source_table="kb_chunks",
        stable_id="book_2026_001:1.4",
        source_span={"chapter": "1", "section": "1.4", "page": 32},
        content_hash="abc123",
        quote_hash="def456",
        public_quote="防水等级应根据工程重要性确定。",
        visibility="public",
        authority_rank=45,
        evidence_level="direct",
    )

    assert ref.to_public_dict() == {
        "citation_id": "c1",
        "marker": "〔1〕",
        "source_type": "textbook",
        "title": "2026 建筑实务教材",
        "locator": "防水工程 > 屋面防水等级",
        "source_id": "book_2026_001",
        "source_table": "kb_chunks",
        "stable_id": "book_2026_001:1.4",
        "source_span": {"chapter": "1", "section": "1.4", "page": 32},
        "content_hash": "abc123",
        "quote_hash": "def456",
        "public_quote": "防水等级应根据工程重要性确定。",
        "authority_rank": 45,
        "evidence_level": "direct",
    }


def test_private_ref_is_not_public() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="hidden",
        locator="grading_key",
        visibility="private",
        public_quote="correct_answer: A",
    )

    assert ref.is_public is False
    assert ref.to_public_dict() == {}


def test_bundle_carries_claims_and_no_public_source_state() -> None:
    claim = CitedClaim(
        claim_id="claim_1",
        text="屋面防水等级应根据工程重要性确定。",
        citation_ids=["c1"],
        confidence=0.93,
    )
    bundle = CitationBundle(
        citation_state="supported",
        refs=[],
        claims=[claim],
        footer_text="依据",
    )

    assert bundle.claims[0].citation_ids == ["c1"]
    no_source = CitationBundle.no_public_source()
    assert no_source.citation_state == "no_public_source"
    assert no_source.refs == []
    assert "未使用可公开引用" in no_source.footer_text


def test_policy_defaults_to_student_surface() -> None:
    policy = CitationPolicy()

    assert policy.surface == "student"
    assert policy.require_footer is True
    assert policy.max_public_refs == 8
    assert policy.min_claim_ref_score == 0.18
```

- [ ] **Step 1.2: Run schema tests and verify they fail**

Run:

```bash
pytest tests/services/citations/test_schema.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.citations'
```

- [ ] **Step 1.3: Implement schema**

Create `deeptutor/services/citations/schema.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CitationState = Literal["supported", "partial", "no_public_source", "degraded"]
CitationSurface = Literal["student", "reviewer", "internal"]
CitationVisibility = Literal["public", "private"]


@dataclass(frozen=True)
class CitationPolicy:
    surface: CitationSurface = "student"
    require_footer: bool = True
    max_public_refs: int = 8
    min_claim_ref_score: float = 0.18
    max_public_quote_chars: int = 180


@dataclass(frozen=True)
class CitationSourceRef:
    citation_id: str
    marker: str
    source_type: str
    title: str
    locator: str
    source_id: str = ""
    source_table: str = ""
    stable_id: str = ""
    source_span: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    quote_hash: str = ""
    public_quote: str = ""
    visibility: CitationVisibility = "public"
    authority_rank: int = 0
    evidence_level: str = ""

    @property
    def is_public(self) -> bool:
        return self.visibility == "public"

    def to_public_dict(self) -> dict[str, Any]:
        if not self.is_public:
            return {}
        return {
            "citation_id": self.citation_id,
            "marker": self.marker,
            "source_type": self.source_type,
            "title": self.title,
            "locator": self.locator,
            "source_id": self.source_id,
            "source_table": self.source_table,
            "stable_id": self.stable_id,
            "source_span": dict(self.source_span),
            "content_hash": self.content_hash,
            "quote_hash": self.quote_hash,
            "public_quote": self.public_quote,
            "authority_rank": self.authority_rank,
            "evidence_level": self.evidence_level,
        }


@dataclass(frozen=True)
class CitedClaim:
    claim_id: str
    text: str
    citation_ids: list[str]
    confidence: float


@dataclass(frozen=True)
class CitationBundle:
    citation_state: CitationState
    refs: list[CitationSourceRef]
    claims: list[CitedClaim]
    footer_text: str

    @classmethod
    def no_public_source(cls) -> "CitationBundle":
        return cls(
            citation_state="no_public_source",
            refs=[],
            claims=[],
            footer_text=(
                "依据\n"
                "本轮未使用可公开引用的教材、规范、题库或学习证据；"
                "以上内容仅为通用对话说明，不进入学习事实或评分依据。"
            ),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "citation_state": self.citation_state,
            "refs": [item for ref in self.refs if (item := ref.to_public_dict())],
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "citation_ids": list(claim.citation_ids),
                    "confidence": claim.confidence,
                }
                for claim in self.claims
            ],
            "footer_text": self.footer_text,
        }


@dataclass(frozen=True)
class CitedAnswer:
    response: str
    bundle: CitationBundle
```

Create `deeptutor/services/citations/__init__.py`:

```python
from deeptutor.services.citations.schema import (
    CitationBundle,
    CitationPolicy,
    CitationSourceRef,
    CitedAnswer,
    CitedClaim,
)

__all__ = [
    "CitationBundle",
    "CitationPolicy",
    "CitationSourceRef",
    "CitedAnswer",
    "CitedClaim",
]
```

Do not export `assemble_cited_answer` in Task 1. That export is added in Task 3 after `assembler.py` exists.

- [ ] **Step 1.4: Run schema tests**

Run:

```bash
pytest tests/services/citations/test_schema.py -q
```

Expected:

```text
4 passed
```

## 7. Task 2: Source Normalizer

**Files:**
- Create: `deeptutor/services/citations/normalizer.py`
- Test: `tests/services/citations/test_normalizer.py`

- [ ] **Step 2.1: Write normalizer tests**

Create `tests/services/citations/test_normalizer.py`:

```python
from deeptutor.services.citations.normalizer import normalize_citation_sources
from deeptutor.services.citations.schema import CitationPolicy


def test_normalizes_textbook_source_span() -> None:
    refs = normalize_citation_sources(
        [
            {
                "chunk_id": "book-1",
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_001",
                    "source_table": "kb_chunks",
                    "stable_id": "book_2026_001:1.4",
                    "source_span": {"chapter": "1", "section": "1.4", "page": 32},
                    "content_hash": "hash1",
                    "quote_hash": "quote1",
                    "chapter_name": "建筑工程防水",
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        policy=CitationPolicy(),
    )

    assert refs[0].marker == "〔1〕"
    assert refs[0].source_type == "textbook"
    assert refs[0].locator == "第 1 章 第 1.4 节 p.32"
    assert refs[0].source_id == "book_2026_001"
    assert refs[0].source_table == "kb_chunks"
    assert refs[0].stable_id == "book_2026_001:1.4"
    assert refs[0].public_quote == "屋面防水等级应根据工程重要性确定。"


def test_filters_hidden_grading_authority_for_student_surface() -> None:
    refs = normalize_citation_sources(
        [
            {"source_type": "questions_bank", "field": "correct_answer", "value": "A"},
            {"source_type": "questions_bank", "field": "knowledge_point", "value": "屋面防水"},
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert len(refs) == 1
    assert refs[0].public_quote == "屋面防水"


def test_deduplicates_same_source_and_span() -> None:
    refs = normalize_citation_sources(
        [
            {"chunk_id": "c1", "source_type": "standard", "standard_code": "GB 50345-2012", "article_code": "3.0.1"},
            {"chunk_id": "c1", "source_type": "standard", "standard_code": "GB 50345-2012", "article_code": "3.0.1"},
        ],
        policy=CitationPolicy(),
    )

    assert len(refs) == 1
    assert refs[0].locator == "GB 50345-2012 第 3.0.1 条"
```

- [ ] **Step 2.2: Implement normalizer**

Create `deeptutor/services/citations/normalizer.py` using deterministic helpers. Requirements:

```python
_HIDDEN_FIELDS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "official_answer",
}
```

Implementation rules:

1. Ignore non-dict sources.
2. For `surface="student"`, drop any source whose field/key/name matches `_HIDDEN_FIELDS`.
3. Read compact metadata from either top-level keys or `metadata`.
4. Prefer `source_id`, `source_table`, `stable_id`, `source_span`, `content_hash`, `quote_hash`.
5. Build locators in this order:
   - standard article: `GB 50345-2012 第 3.0.1 条`
   - textbook span: `第 1 章 第 1.4 节 p.32`
   - question span: `2023 真题 Q4-2`
   - fallback: source type
6. Deduplicate by `(source_id or stable_id or chunk_id, locator)`.
7. Assign markers sequentially after filtering and deduplication.

- [ ] **Step 2.3: Run normalizer tests**

Run:

```bash
pytest tests/services/citations/test_normalizer.py -q
```

Expected:

```text
3 passed
```

## 8. Task 3: Formatter And Claim-Level Assembler

**Files:**
- Create: `deeptutor/services/citations/formatter.py`
- Create: `deeptutor/services/citations/assembler.py`
- Modify: `deeptutor/services/citations/__init__.py`
- Test: `tests/services/citations/test_formatter.py`
- Test: `tests/services/citations/test_assembler.py`

- [ ] **Step 3.1: Write formatter and assembler tests**

Create `tests/services/citations/test_formatter.py`:

```python
from deeptutor.services.citations.formatter import format_citation_footer
from deeptutor.services.citations.schema import CitationSourceRef


def test_formats_paper_style_footer() -> None:
    footer = format_citation_footer(
        [
            CitationSourceRef(
                citation_id="c1",
                marker="〔1〕",
                source_type="textbook",
                title="2026 建筑实务教材",
                locator="第 1 章 第 1.4 节",
                source_id="book_2026_001",
                public_quote="屋面防水等级应根据工程重要性确定。",
            )
        ]
    )

    assert footer == (
        "依据\n"
        "〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。"
        "摘录：屋面防水等级应根据工程重要性确定。"
    )
```

Create `tests/services/citations/test_assembler.py`:

```python
from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.schema import CitationPolicy


def test_assembles_markers_on_multiple_knowledge_lines() -> None:
    cited = assemble_cited_answer(
        "屋面防水等级应根据工程重要性确定。\n\n设防要求要结合渗漏后果判断。",
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_roof_level",
                    "source_span": {"chapter": "1", "section": "1.4"},
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            },
            {
                "source_type": "standard",
                "title": "屋面工程技术规范",
                "standard_code": "GB 50345-2012",
                "article_code": "3.0.1",
                "rag_content": "设防要求应结合渗漏后果判断。",
            },
        ],
        policy=CitationPolicy(),
    )

    assert "屋面防水等级应根据工程重要性确定。〔1〕" in cited.response
    assert "设防要求要结合渗漏后果判断。〔2〕" in cited.response
    assert "\n\n依据\n〔1〕2026 建筑实务教材" in cited.response
    assert "〔2〕屋面工程技术规范，GB 50345-2012 第 3.0.1 条" in cited.response
    assert cited.bundle.citation_state == "supported"
    assert len(cited.bundle.claims) == 2


def test_assembles_no_public_source_footer_without_fake_marker() -> None:
    cited = assemble_cited_answer("你好，我可以帮你复习。", sources=[], policy=CitationPolicy())

    assert cited.response.startswith("你好，我可以帮你复习。")
    assert "本轮未使用可公开引用" in cited.response
    assert "〔1〕" not in cited.response
    assert cited.bundle.citation_state == "no_public_source"
```

- [ ] **Step 3.2: Implement formatter**

Create `deeptutor/services/citations/formatter.py`:

```python
from __future__ import annotations

from deeptutor.services.citations.schema import CitationSourceRef


def format_citation_footer(refs: list[CitationSourceRef]) -> str:
    if not refs:
        return (
            "依据\n"
            "本轮未使用可公开引用的教材、规范、题库或学习证据；"
            "以上内容仅为通用对话说明，不进入学习事实或评分依据。"
        )
    lines = ["依据"]
    for ref in refs:
        locator = f"，{ref.locator}" if ref.locator else ""
        source_id = f"，source_id={ref.source_id}" if ref.source_id else ""
        quote = f"。摘录：{ref.public_quote}" if ref.public_quote else ""
        lines.append(f"{ref.marker}{ref.title}{locator}{source_id}{quote}")
    return "\n".join(lines)
```

- [ ] **Step 3.3: Implement paragraph/list-item level assembler**

Create `deeptutor/services/citations/assembler.py`. It must:

1. Strip any pre-existing `依据` footer.
2. Split body into non-empty paragraphs/list items.
3. Match each segment to the public ref with the highest lexical overlap against `public_quote`, `title`, and `locator`.
4. Insert the matched marker at the end of that segment when score >= `policy.min_claim_ref_score`.
5. If refs exist but no segment reaches threshold, mark `citation_state="partial"` and attach the highest-authority marker to the final knowledge paragraph; never claim full coverage.
6. Return `no_public_source` when no public refs survive normalization.

Core implementation sketch:

```python
from __future__ import annotations

import re

from deeptutor.services.citations.formatter import format_citation_footer
from deeptutor.services.citations.normalizer import normalize_citation_sources
from deeptutor.services.citations.schema import CitationBundle, CitationPolicy, CitedAnswer, CitedClaim, CitationSourceRef


_FOOTER_RE = re.compile(r"\n{1,2}依据\n", re.MULTILINE)
_MARKER_RE = re.compile(r"〔\d+〕$")


def _strip_existing_footer(answer: str) -> str:
    text = str(answer or "").strip()
    match = _FOOTER_RE.search(text)
    return text[: match.start()].strip() if match else text


def _segments(answer: str) -> list[str]:
    return [part.strip() for part in re.split(r"(\n{2,}|(?<=。)\n)", answer) if part.strip()]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text))


def _score(segment: str, ref: CitationSourceRef) -> float:
    source_text = " ".join([ref.public_quote, ref.title, ref.locator])
    a = _tokens(segment)
    b = _tokens(source_text)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), 1)


def _best_ref(segment: str, refs: list[CitationSourceRef]) -> tuple[CitationSourceRef | None, float]:
    scored = [(ref, _score(segment, ref)) for ref in refs]
    if not scored:
        return None, 0.0
    return max(scored, key=lambda item: (item[1], item[0].authority_rank))


def assemble_cited_answer(
    answer: str,
    *,
    sources: list[dict],
    policy: CitationPolicy | None = None,
) -> CitedAnswer:
    active_policy = policy or CitationPolicy()
    clean_answer = _strip_existing_footer(answer)
    refs = normalize_citation_sources(sources, policy=active_policy)
    if not refs:
        bundle = CitationBundle.no_public_source()
        return CitedAnswer(response=f"{clean_answer}\n\n{bundle.footer_text}".strip(), bundle=bundle)

    rendered_segments: list[str] = []
    claims: list[CitedClaim] = []
    matched_count = 0
    for index, segment in enumerate(_segments(clean_answer), start=1):
        ref, score = _best_ref(segment, refs)
        if ref and score >= active_policy.min_claim_ref_score and not _MARKER_RE.search(segment):
            rendered_segments.append(f"{segment}{ref.marker}")
            claims.append(CitedClaim(f"claim_{index}", segment, [ref.citation_id], round(score, 4)))
            matched_count += 1
        else:
            rendered_segments.append(segment)

    if matched_count == 0 and refs and rendered_segments:
        ref = refs[0]
        rendered_segments[-1] = f"{rendered_segments[-1]}{ref.marker}"
        claims.append(CitedClaim("claim_fallback_1", rendered_segments[-1], [ref.citation_id], 0.0))

    citation_state = "supported" if matched_count == len([s for s in rendered_segments if s]) else "partial"
    footer = format_citation_footer(refs)
    bundle = CitationBundle(citation_state=citation_state, refs=refs, claims=claims, footer_text=footer)
    body = "\n\n".join(rendered_segments)
    return CitedAnswer(response=f"{body}\n\n{footer}".strip(), bundle=bundle)
```

- [ ] **Step 3.4: Export assembler after it exists**

Modify `deeptutor/services/citations/__init__.py`:

```python
from deeptutor.services.citations.assembler import assemble_cited_answer
from deeptutor.services.citations.schema import (
    CitationBundle,
    CitationPolicy,
    CitationSourceRef,
    CitedAnswer,
    CitedClaim,
)

__all__ = [
    "assemble_cited_answer",
    "CitationBundle",
    "CitationPolicy",
    "CitationSourceRef",
    "CitedAnswer",
    "CitedClaim",
]
```

- [ ] **Step 3.5: Run formatter and assembler tests**

Run:

```bash
pytest \
  tests/services/citations/test_formatter.py \
  tests/services/citations/test_assembler.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 9. Task 4: Citation Quality Guard

**Files:**
- Create: `deeptutor/services/citations/quality.py`
- Test: `tests/services/citations/test_quality.py`

- [ ] **Step 4.1: Write quality tests**

Create `tests/services/citations/test_quality.py`:

```python
import pytest

from deeptutor.services.citations.quality import CitationQualityError, validate_cited_answer
from deeptutor.services.citations.schema import CitationBundle, CitationSourceRef, CitedAnswer


def _answer(response: str, refs: list[CitationSourceRef]) -> CitedAnswer:
    return CitedAnswer(
        response=response,
        bundle=CitationBundle(citation_state="supported", refs=refs, claims=[], footer_text="依据"),
    )


def test_rejects_orphan_marker() -> None:
    with pytest.raises(CitationQualityError, match="orphan citation marker"):
        validate_cited_answer(_answer("正文〔2〕\n\n依据\n〔1〕来源", []))


def test_rejects_footer_row_without_visible_marker() -> None:
    ref = CitationSourceRef("c1", "〔1〕", "textbook", "教材", "第 1 章")
    with pytest.raises(CitationQualityError, match="footer row without visible marker"):
        validate_cited_answer(_answer("正文\n\n依据\n〔1〕教材", [ref]))


def test_rejects_hidden_public_quote() -> None:
    ref = CitationSourceRef(
        citation_id="c1",
        marker="〔1〕",
        source_type="questions_bank",
        title="题库",
        locator="Q1",
        public_quote="correct_answer: A",
    )
    with pytest.raises(CitationQualityError, match="hidden authority"):
        validate_cited_answer(_answer("正文〔1〕\n\n依据\n〔1〕题库", [ref]))


def test_accepts_no_public_source_footer() -> None:
    answer = CitedAnswer(
        response=(
            "你好\n\n依据\n"
            "本轮未使用可公开引用的教材、规范、题库或学习证据；"
            "以上内容仅为通用对话说明，不进入学习事实或评分依据。"
        ),
        bundle=CitationBundle.no_public_source(),
    )

    validate_cited_answer(answer)
```

- [ ] **Step 4.2: Implement quality guard**

Create `deeptutor/services/citations/quality.py`:

```python
from __future__ import annotations

import re

from deeptutor.services.citations.schema import CitedAnswer


class CitationQualityError(ValueError):
    pass


_MARKER_RE = re.compile(r"〔(\d+)〕")
_HIDDEN_TEXT_RE = re.compile(r"(correct_answer|grading_key|scoring_points|minimal_rationale|answer_key)", re.I)


def validate_cited_answer(answer: CitedAnswer) -> None:
    response = str(answer.response or "")
    markers = {int(match.group(1)) for match in _MARKER_RE.finditer(response)}
    expected = set(range(1, len(answer.bundle.refs) + 1))
    if answer.bundle.citation_state == "no_public_source":
        if markers:
            raise CitationQualityError("no-public-source answer cannot contain citation markers")
        return
    if markers - expected:
        raise CitationQualityError("orphan citation marker")
    if expected - markers:
        raise CitationQualityError("footer row without visible marker")
    for ref in answer.bundle.refs:
        public_text = " ".join([ref.public_quote, ref.title, ref.locator, ref.source_id, ref.stable_id])
        if _HIDDEN_TEXT_RE.search(public_text):
            raise CitationQualityError("hidden authority found in public citation")
```

Integration policy:

```text
Hidden leak / orphan marker / footer mismatch: block public citation row and emit no_public_source footer, unless this is an internal test where raising is required.
No source for knowledge claim: partial or no_public_source, never fabricated source.
```

- [ ] **Step 4.3: Run quality tests**

Run:

```bash
pytest tests/services/citations/test_quality.py -q
```

Expected:

```text
4 passed
```

## 10. Task 5: Chat Pipeline Integration

**Files:**
- Modify: `deeptutor/agents/chat/agentic_pipeline.py`
- Test: `tests/agents/chat/test_answer_citations.py`

- [ ] **Step 5.1: Write chat integration test**

Create `tests/agents/chat/test_answer_citations.py`:

```python
import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline, ToolTrace
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


@pytest.mark.asyncio
async def test_chat_emit_sources_and_result_appends_paper_style_citations() -> None:
    stream = StreamBus()
    pipeline = AgenticChatPipeline(language="zh")
    trace = ToolTrace(
        name="rag",
        arguments={"query": "屋面防水等级"},
        result="context",
        success=True,
        sources=[
            {
                "source_type": "textbook",
                "title": "2026 建筑实务教材",
                "metadata": {
                    "source_id": "book_2026_001",
                    "source_span": {"chapter": "1", "section": "1.4"},
                },
                "rag_content": "屋面防水等级应根据工程重要性确定。",
            }
        ],
        metadata={},
    )

    await pipeline._emit_sources_and_result(
        stream=stream,
        responding_trace={},
        tool_traces=[trace],
        final_response="屋面防水等级应根据工程重要性确定。",
        observation="",
    )

    result = next(event for event in stream._history if event.type == StreamEventType.RESULT)
    response = result.metadata["response"]
    assert "屋面防水等级应根据工程重要性确定。〔1〕" in response
    assert "\n\n依据\n〔1〕2026 建筑实务教材" in response
    assert result.metadata["citation_bundle"]["citation_state"] in {"supported", "partial"}
```

This deliberately uses `stream._history` because existing tests already use it; do not invent `StreamBus.history()`.

- [ ] **Step 5.2: Modify chat result assembly**

In `deeptutor/agents/chat/agentic_pipeline.py`, import:

```python
from deeptutor.services.citations import CitationPolicy, assemble_cited_answer
from deeptutor.services.citations.quality import CitationQualityError, validate_cited_answer
```

Inside `_emit_sources_and_result(...)`, after `all_sources` is built and before `result_payload`, add:

```python
        cited_answer = assemble_cited_answer(
            final_response,
            sources=all_sources,
            policy=CitationPolicy(surface="student"),
        )
        try:
            validate_cited_answer(cited_answer)
        except CitationQualityError:
            cited_answer = assemble_cited_answer(
                final_response,
                sources=[],
                policy=CitationPolicy(surface="student"),
            )
        final_response = cited_answer.response
```

Then add to `result_payload`:

```python
            "citation_bundle": cited_answer.bundle.to_public_dict(),
```

Keep existing `stream.sources(...)` behavior unchanged.

- [ ] **Step 5.3: Run chat citation tests**

Run:

```bash
pytest \
  tests/agents/chat/test_answer_citations.py \
  tests/agents/chat/test_agentic_parallel_tools.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 11. Task 6: TutorBot Integration And Streaming Consistency

**Files:**
- Modify: `deeptutor/capabilities/tutorbot.py`
- Test: `tests/capabilities/test_tutorbot_answer_citations.py`

- [ ] **Step 6.1: Write TutorBot citation behavior test**

Create `tests/capabilities/test_tutorbot_answer_citations.py`:

```python
from deeptutor.services.citations import CitationPolicy, assemble_cited_answer


def test_tutorbot_visible_response_can_be_cited_from_tool_sources() -> None:
    cited = assemble_cited_answer(
        "施工现场临时用电应编制专项方案。",
        sources=[
            {
                "source_type": "standard",
                "standard_code": "JGJ 46-2005",
                "article_code": "3.1.1",
                "title": "施工现场临时用电安全技术规范",
                "rag_content": "临时用电组织设计应包含用电负荷计算。",
            }
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert "〔1〕" in cited.response
    assert "JGJ 46-2005 第 3.1.1 条" in cited.response
```

- [ ] **Step 6.2: Preserve canonical result as the UI authority**

In `deeptutor/capabilities/tutorbot.py`:

1. Collect public tool sources into `citation_sources: list[dict[str, Any]]`.
2. Before emitting `result_payload`, assemble `visible_response` through `assemble_cited_answer(...)`.
3. Set `result_payload["response"] = cited_answer.response`.
4. Set `result_payload["citation_bundle"] = cited_answer.bundle.to_public_dict()`.
5. If public content deltas already emitted the uncited answer body, stream a final public delta containing the missing citation suffix and `依据` footer, and ensure the renderer replaces the displayed message with `result.metadata.response`.

Stop condition:

```text
If renderer cannot replace displayed content from result.metadata.response, do not enable public citation mode. Either delay public body deltas for citation-enforced turns or add an explicit final replacement event in the existing /api/v1/ws contract.
```

- [ ] **Step 6.3: Run TutorBot tests**

Run:

```bash
pytest \
  tests/capabilities/test_tutorbot_answer_citations.py \
  tests/core/test_capabilities_runtime.py::test_tutorbot_agent_loop_retries_when_final_response_has_no_visible_content \
  -q
```

Expected:

```text
all selected tests pass
```

## 12. Task 7: Deep Question Post-Submit Integration

**Files:**
- Modify: `deeptutor/capabilities/deep_question.py`
- Test: `tests/capabilities/test_deep_question_answer_citations.py`

- [ ] **Step 7.1: Write post-submit citation test**

Create `tests/capabilities/test_deep_question_answer_citations.py`:

```python
from deeptutor.services.citations import CitationPolicy, assemble_cited_answer


def test_post_submit_explanation_uses_public_grading_evidence_refs() -> None:
    cited = assemble_cited_answer(
        "你漏写了专家论证程序，这是本题主要采分点。",
        sources=[
            {
                "source_type": "case_rubric",
                "title": "2023 一建建筑实务案例题 Q4",
                "field": "knowledge_point",
                "value": "专家论证程序",
                "metadata": {
                    "source_id": "question_2023_q4",
                    "source_span": {"question": "Q4", "sub_question": "2"},
                },
            }
        ],
        policy=CitationPolicy(surface="student"),
    )

    assert "专家论证程序，这是本题主要采分点。〔1〕" in cited.response
    assert "2023 一建建筑实务案例题 Q4" in cited.response
```

- [ ] **Step 7.2: Assemble citations from public post-submit evidence**

Before `await stream.result(result_payload, source=self.name)` in the post-submit path:

```python
            citation_sources = []
            citation_sources.extend(item for item in result_payload.get("grading_grounding_sources") or [] if isinstance(item, dict))
            grading_result = result_payload.get("construction_grading_result")
            if isinstance(grading_result, dict):
                citation_sources.extend(item for item in grading_result.get("evidence_refs") or [] if isinstance(item, dict))

            cited_answer = assemble_cited_answer(
                str(result_payload.get("response") or ""),
                sources=citation_sources,
                policy=CitationPolicy(surface="student"),
            )
            try:
                validate_cited_answer(cited_answer)
            except CitationQualityError:
                cited_answer = assemble_cited_answer(
                    str(result_payload.get("response") or ""),
                    sources=[],
                    policy=CitationPolicy(surface="student"),
                )
            result_payload["response"] = cited_answer.response
            result_payload["citation_bundle"] = cited_answer.bundle.to_public_dict()
```

Do not cite raw `grading_key.scoring_points` directly. Only cite public post-submit evidence refs or source spans that pass normalizer redaction.

- [ ] **Step 7.3: Run deep-question tests**

Run:

```bash
pytest tests/capabilities/test_deep_question_answer_citations.py -q
```

Expected:

```text
1 passed
```

## 13. Task 8: Turn Contract And Public Redaction

**Files:**
- Modify: `contracts/turn.md`
- Modify: `contracts/rag.md`
- Modify: `contracts/index.yaml`
- Test: `tests/api/test_unified_ws_answer_citations.py`
- Test: `tests/api/test_unified_ws_public_redaction.py`

- [ ] **Step 8.1: Write public redaction test**

Create `tests/api/test_unified_ws_answer_citations.py`:

```python
from deeptutor.services.citations import CitationPolicy, assemble_cited_answer


def test_public_citation_bundle_does_not_include_hidden_grading_authority() -> None:
    cited = assemble_cited_answer(
        "这题考查屋面防水。",
        sources=[
            {"source_type": "questions_bank", "field": "correct_answer", "value": "A"},
            {"source_type": "questions_bank", "field": "knowledge_point", "value": "屋面防水"},
        ],
        policy=CitationPolicy(surface="student"),
    )

    payload = cited.bundle.to_public_dict()
    text = str(payload)
    assert "correct_answer" not in text
    assert "grading_key" not in text
    assert "屋面防水" in text
```

- [ ] **Step 8.2: Update contracts**

In `contracts/turn.md`, add:

```markdown
- `citation_bundle`
- `citation_bundle.citation_state`
- `citation_bundle.refs`
- `citation_bundle.claims`
```

Add a hard constraint:

```markdown
Public final answers must append server-side paper-style citations before `result.metadata.response` is materialized. Citation rows are public projections over existing RAG / source / grading evidence and must not expose hidden grading authority or become a routing, scoring, or learner-state writer. If live content deltas differ from `result.metadata.response`, the renderer must treat the result payload as the canonical displayed answer.
```

In `contracts/rag.md`, add:

```markdown
`evidence_bundle.sources` must preserve compact source identity fields needed by public citations (`source_id`, `source_table`, `stable_id`, `source_span`, `content_hash`, `quote_hash`, source type, title, standard/article locators) when available. It must not expose private learner projections or hidden grading authority.
```

In `contracts/index.yaml`, add these tests to relevant domains:

```yaml
- tests/api/test_unified_ws_answer_citations.py
- tests/services/citations/test_quality.py
- tests/services/citations/test_normalizer.py
```

- [ ] **Step 8.3: Run contract and redaction tests**

Run:

```bash
pytest \
  tests/api/test_unified_ws_answer_citations.py \
  tests/api/test_unified_ws_public_redaction.py \
  tests/services/citations/test_quality.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 14. Task 9: RAG Source Span Preservation

**Files:**
- Modify: `deeptutor/services/rag/pipelines/supabase.py`
- Modify: `deeptutor/services/rag/service.py`
- Test: `tests/services/rag/test_rag_pipelines.py`
- Test: `tests/services/rag/test_provenance.py`

- [ ] **Step 9.1: Add source-span regression test**

Add to `tests/services/rag/test_rag_pipelines.py`:

```python
def test_evidence_bundle_sources_preserve_citation_span() -> None:
    source = {
        "chunk_id": "book-1",
        "source_type": "textbook",
        "metadata": {
            "source_id": "book_2026_001",
            "source_table": "kb_chunks",
            "stable_id": "book_2026_001:1.4",
            "source_span": {"chapter": "1", "section": "1.4", "page": 32},
            "content_hash": "hash1",
            "quote_hash": "quote1",
        },
    }

    from deeptutor.services.citations.normalizer import normalize_citation_sources
    from deeptutor.services.citations.schema import CitationPolicy

    refs = normalize_citation_sources([source], policy=CitationPolicy())

    assert refs[0].source_span == {"chapter": "1", "section": "1.4", "page": 32}
    assert refs[0].source_table == "kb_chunks"
    assert refs[0].stable_id == "book_2026_001:1.4"
    assert refs[0].content_hash == "hash1"
    assert refs[0].quote_hash == "quote1"
```

- [ ] **Step 9.2: Preserve compact source metadata**

In `deeptutor/services/rag/pipelines/supabase.py`, when mapping retrieval rows into `sources`, preserve these keys if present:

```python
{
    "source_id": metadata.get("source_id") or row.get("source_id"),
    "source_table": metadata.get("source_table") or row.get("source_table"),
    "stable_id": metadata.get("stable_id") or row.get("stable_id"),
    "source_span": metadata.get("source_span") or row.get("source_span"),
    "content_hash": metadata.get("content_hash") or row.get("content_hash"),
    "quote_hash": metadata.get("quote_hash") or row.get("quote_hash"),
    "chapter": metadata.get("chapter"),
    "chapter_name": metadata.get("chapter_name"),
    "section": metadata.get("section"),
    "page": metadata.get("page"),
}
```

Keep full raw metadata out of public result if it contains private learner projection or hidden grading fields.

- [ ] **Step 9.3: Run RAG tests**

Run:

```bash
pytest \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/rag/test_provenance.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 15. Task 10: Citation Accuracy Benchmark And Release Gate

**Files:**
- Create: `tests/fixtures/answer_citation_eval_cases.json`
- Create: `deeptutor/services/benchmark/answer_citation_audit.py`
- Test: `tests/services/benchmark/test_answer_citation_audit.py`
- Modify: `deeptutor/services/benchmark/fixtures/benchmark_phase1_registry.json`

- [ ] **Step 10.1: Create accuracy eval fixture**

Create `tests/fixtures/answer_citation_eval_cases.json`:

```json
{
  "suite": "answer_citation_eval_v1",
  "cases": [
    {
      "case_id": "textbook_roof_waterproofing",
      "answer": "屋面防水等级应根据工程重要性确定。〔1〕\n\n依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节，source_id=book_2026_001。摘录：屋面防水等级应根据工程重要性确定。",
      "citation_bundle": {
        "citation_state": "supported",
        "refs": [
          {
            "citation_id": "c1",
            "marker": "〔1〕",
            "source_type": "textbook",
            "source_id": "book_2026_001",
            "source_span": {"chapter": "1", "section": "1.4"}
          }
        ],
        "claims": [
          {
            "claim_id": "claim_1",
            "text": "屋面防水等级应根据工程重要性确定。",
            "citation_ids": ["c1"]
          }
        ]
      },
      "expected_claim_refs": [
        {
          "claim_text": "屋面防水等级应根据工程重要性确定。",
          "expected_source_ids": ["book_2026_001"],
          "expected_source_span": {"chapter": "1", "section": "1.4"}
        }
      ],
      "forbidden_terms": ["correct_answer", "grading_key", "scoring_points"]
    }
  ]
}
```

- [ ] **Step 10.2: Implement audit helper**

Create `deeptutor/services/benchmark/answer_citation_audit.py` with checks for:

1. `依据` footer exists.
2. Every public marker has a footer row.
3. No forbidden terms appear in answer or `citation_bundle`.
4. Each `expected_claim_refs` item is supported by a citation ref whose `source_id` and required `source_span` match.
5. Return `citation_accuracy`, `footer_coverage`, `hidden_leak_count`, and per-case failure reasons.

- [ ] **Step 10.3: Write and run benchmark test**

Create `tests/services/benchmark/test_answer_citation_audit.py`:

```python
from pathlib import Path

from deeptutor.services.benchmark.answer_citation_audit import audit_answer_citation_cases


def test_answer_citation_audit_fixture_passes_accuracy_checks() -> None:
    result = audit_answer_citation_cases(Path("tests/fixtures/answer_citation_eval_cases.json"))

    assert result["suite"] == "answer_citation_eval_v1"
    assert result["citation_accuracy"] == 1.0
    assert result["footer_coverage"] == 1.0
    assert result["hidden_leak_count"] == 0
```

Run:

```bash
pytest tests/services/benchmark/test_answer_citation_audit.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 10.4: Register non-gate shadow suite**

Add `answer_citation_eval_v1` to `deeptutor/services/benchmark/fixtures/benchmark_phase1_registry.json` as a non-gate suite first. It becomes a release gate only after shadow data proves accuracy and no-leak stability.

## 16. Task 11: WeChat / Renderer Compatibility

**Files:**
- Test: `wx_miniprogram/tests/test_ai_message_state.js`
- Test: `yousenwebview/packageDeeptutor/**`
- Modify only if tests prove rendering strips citation markers or the canonical result replacement fails.

- [ ] **Step 11.1: Add renderer fixture test**

Add a fixture message:

```javascript
const citedMessage = "屋面防水等级应根据工程重要性确定。〔1〕\n\n依据\n〔1〕2026 建筑实务教材，第 1 章 第 1.4 节。";
```

Assert:

```javascript
expect(renderedText).toContain("〔1〕");
expect(renderedText).toContain("依据");
expect(renderedText).toContain("2026 建筑实务教材");
```

- [ ] **Step 11.2: Run renderer tests**

Run the actual project-local command for these suites. Try:

```bash
npm test -- wx_miniprogram/tests/test_ai_message_state.js
```

Then run the package surface test used by `yousenwebview/packageDeeptutor`. If the repo uses a different runner, use the package script already defined in that package's `package.json`; do not skip renderer validation.

- [ ] **Step 11.3: Run surface QA order**

Required order:

```text
1. /wechat-harness shadow QA
2. yousenwebview/packageDeeptutor primary package check
3. WeChat DevTools smoke for the true mini-program path
```

Pass criteria:

```text
Markers render.
The final 依据 footer is visible or collapsed behind an explicit references affordance.
Long source rows do not overflow mobile width.
The rendered message reconciles with result.metadata.response.
```

## 17. Task 12: Rollout And Observability

**Files:**
- Modify: project-local config helper only if a matching feature-flag pattern already exists.
- Modify: Langfuse / ClickHouse metadata emitters only if they already accept final result metadata.
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 12.1: Add feature flag**

Use one flag:

```text
DEEPTUTOR_ANSWER_CITATIONS_ENABLED
```

Runtime policy:

| Phase | Flag | Public footer | Internal audit |
| --- | --- | --- | --- |
| Shadow | false | no forced footer | emit `citation_bundle_candidate` |
| Internal | true for internal users | yes | audit |
| Cohort | true for cohort | yes | audit + sample review |
| Production | true globally | yes | release gate |

Default:

```text
false in production until shadow accuracy gate passes; explicit true in local/test citation suites
```

- [ ] **Step 12.2: Add compact trace fields**

Each final answer should expose compact metadata:

```json
{
  "citation_state": "supported",
  "citation_ref_count": 2,
  "citation_claim_count": 2,
  "citation_source_types": ["textbook", "standard"],
  "citation_quality": {
    "orphan_marker_count": 0,
    "hidden_leak_detected": false,
    "footer_marker_mismatch": false
  }
}
```

Do not log full private learner projection or hidden grading keys.

- [ ] **Step 12.3: Run final targeted gate**

Run:

```bash
pytest \
  tests/services/citations \
  tests/agents/chat/test_answer_citations.py \
  tests/capabilities/test_tutorbot_answer_citations.py \
  tests/capabilities/test_deep_question_answer_citations.py \
  tests/api/test_unified_ws_answer_citations.py \
  tests/api/test_unified_ws_public_redaction.py \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/benchmark/test_answer_citation_audit.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 18. Release Gates

Do not enable globally until all are true:

- [ ] Unit tests for citations pass.
- [ ] Existing RAG / turn / TutorBot / deep_question targeted tests pass.
- [ ] Public redaction proves zero hidden grading authority leaks.
- [ ] Shadow benchmark has 100% citation-state coverage.
- [ ] Shadow benchmark has citation accuracy >= 90% against expected source id/span before internal rollout.
- [ ] Human audit samples at least 50 cited answers; citation accuracy >= 95% before production rollout.
- [ ] WeChat renderer displays `〔n〕` markers and final `依据` section without overlap or truncation.
- [ ] Canonical `result.metadata.response` matches what the user sees in Web / WeChat.
- [ ] Langfuse / ClickHouse trace contains compact citation metrics.
- [ ] No new WebSocket route, no new RAG entry, no second learner-state writer.

## 19. Self-Review Checklist

- [ ] Every citation row has a source id, stable id, or clear locator.
- [ ] Every public marker has a footer row.
- [ ] No footer row exists without a public marker, except the no-public-source footer.
- [ ] `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, and private learner profile never appear in public citations.
- [ ] Non-knowledge answers append the compact no-public-source footer, not fake references.
- [ ] Weak-point claims cite L1/L2 supporting event refs, not a single chat impression.
- [ ] Exact-question and grading authority remain unchanged.
- [ ] Citation quality failure fails closed: keep the answer with no-public-source footer or block the bad source row; never hallucinate a source.
- [ ] Benchmark verifies source accuracy, not only citation syntax.
- [ ] `/wechat-harness`, `yousenwebview/packageDeeptutor`, and WeChat DevTools have all been checked before production enablement.
