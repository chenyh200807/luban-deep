#!/usr/bin/env python3
"""Per-leaf subsection slicing for RichLeaf compilation (编译单位 = 召回单位 = leaf).

Root cause this module closes: the RichLeaf compiler passed the WHOLE chunk
``content_markdown`` to ``_compile_context`` keyed only on ``chunk_id``. Any two
leaves under the same chunk therefore received byte-identical compiled_context —
名实不符 pollution (e.g. a 天窗 leaf and a 门 leaf both filled with the whole
门和窗 chunk).

The fix is a single deterministic seam: given a chunk's markdown, a leaf name,
and the cores of the OTHER co-located leaves, locate the markdown subsection that
belongs to THIS leaf and return only that span. The compiler then compiles each
leaf from its OWN span, so distinct leaves under one chunk get distinct content.

Discipline (root-cause / less-is-more):

- **Deterministic only.** No fuzzy/LLM guessing — a wrong slice is a NEW
  pollution, worse than abstain. Every accepted span must pass BOTH a positive
  check (the leaf's own core anchors the span) AND a negative check (no OTHER
  co-located sibling leaf's core anchors a heading inside the span). Either check
  failing -> abstain (return None -> caller quarantines).
- **Single rule for every lane.** Textbook and lecture lanes both go through this
  one seam; neither falls back to the whole chunk. ``None`` always means
  quarantine.
- **Parent leaves keep only their preamble.** When a leaf owns a parent heading
  whose body also contains a sibling leaf's sub-heading, the parent leaf's span is
  the parent heading + intro text UP TO the first sibling sub-heading, never the
  whole parent (which would re-mint the sibling's content as pollution).

This module owns slicing only. Bucket classification and the fail-closed
collision gate live in the compile script.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

# A markdown ATX heading line: leading #'s (1..6) then the title text.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# A bold-only "heading" line — sources frequently mark a subsection title as a
# standalone bold paragraph (``**（3）门窗（包括天窗）节能施工材料复验要求**``)
# instead of an ATX heading. Treated as a level-7 (deepest) heading candidate so
# ATX headings still win on level ordering.
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*\s*(.+?)\s*\*\*\s*$", re.MULTILINE)

# An enumerated paragraph line that opens a subsection (``（3）……`` / ``3）……``
# / ``3. ……``). Many chunks have NO ATX/bold headings at all — only enumerated
# paragraphs. These are level-8 (below bold) heading candidates: the LAST resort,
# consulted only when no ATX/bold heading anchors the leaf, so a real heading
# always wins.
_ENUM_LINE_RE = re.compile(
    r"^\s*(?:"
    r"[（(]\s*\d+\s*[)）]"          # （1） (1)
    r"|\d+\s*[、）)．.]"             # 1、 1) 1． 1.
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]"   # ① circled
    r")\s*\S",
    re.MULTILINE,
)

_ATX_LEVEL_BOLD = 7   # bold-only heading pseudo-level (deeper than any ATX)
_ATX_LEVEL_ENUM = 8   # enumerated-paragraph pseudo-level (deepest)

# Leading enumerator forms stripped from BOTH heading titles and leaf-name cores
# before matching, so "4. 天窗的设置规定" matches leaf "天窗的设置规定".
_ENUM_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[（(]\s*\d+\s*[)）]"          # （1） (1)
    r"|\d+(?:\.\d+)+\s*"           # 1.2.4 (dotted section number)
    r"|\d+\s*[、）).．.]"            # 1、 1) 1． 1.
    r"|[一二三四五六七八九十]+\s*[、）).]"  # 一、 二）
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]"   # ① circled
    r")\s*"
)

# Separator / structural punctuation that differs only in WRITING FORM between a
# heading and a leaf name for the SAME topic (heading ``一类土：松软土`` vs leaf core
# ``一类土（松软土）`` — identical discriminators 一类土/松软土, only the separator
# differs: ``：`` vs ``（）``). Stripping these before EXACT/FORWARD comparison lets
# the same topic match across punctuation variants. NARROW BY DESIGN: only
# separators/brackets/spaces are removed — no synonym, edit-distance, or tokenized
# fuzzing — so two genuinely different topics still cannot collide.
_SEP_PUNCT_RE = re.compile(r"[：:（）()【】「」『』，,、；;／/\s·]+")


def _normalize_separators(text: str) -> str:
    """Drop separator/structural punctuation so the SAME topic written with
    different separators compares equal (一类土：松软土 == 一类土（松软土）).

    Only separators are removed — discriminative characters are untouched — so
    this stays a writing-form normalization, never a semantic loosening."""
    return _SEP_PUNCT_RE.sub("", str(text or ""))


# Generic words that, alone, must NOT be treated as a discriminative match —
# mirrors the detector's stop-word list so "建筑设计要求" can't match on 要求 only.
_GENERIC_TOKENS = frozenset(
    {"工程", "施工", "质量", "通病", "防治", "管理", "问题", "要点", "技术", "要求", "规定", "构造", "设计"}
)

# Trailing qualifier words a leaf name appends to a shorter source heading
# (全站仪 -> 全站仪测量, 防火堵料 -> 防火堵料分类与应用). When a HEADING is a prefix
# of the leaf core and the only remainder is one of these qualifiers, the heading
# is the same topic stated more tersely — a SAFE reverse match. Any other
# remainder means the heading is a different (often broader) sibling topic.
_QUALIFIER_TAIL_RE = re.compile(
    r"^(?:的)?(?:"
    r"分类|应用|测量|计算|特点|特征|要求|规定|内容|依据|编制|与应用|分类与应用|"
    r"构造与施工|与施工|与计算|及应用|及计算|体系|的应用|的特点|的要求|的规定"
    r")+$"
)


@dataclass(frozen=True)
class Subsection:
    """One markdown subsection located for a leaf: its own heading + body span."""

    heading_title: str
    heading_level: int
    text: str  # the leaf's OWN span (heading line + body, up to next sibling/higher heading)


def _strip_enumerator(text: str) -> str:
    return _ENUM_PREFIX_RE.sub("", str(text or "")).strip()


def leaf_name_core(leaf_name: str) -> str:
    """The discriminative core of a leaf name: the last segment after a ``——`` /
    ``・`` qualifier (e.g. 结构设计——圈梁 -> 圈梁), enumerator stripped."""
    core = str(leaf_name or "").strip()
    for sep in ("——", "--", "・", "·"):
        if sep in core:
            core = core.split(sep)[-1]
    return _strip_enumerator(core).strip()


def _is_discriminative(core: str) -> bool:
    """A core is discriminative only if, after removing generic tokens, something
    of length >= 2 remains. Pure-generic names ('建筑设计要求') cannot anchor a
    distinct subsection and must abstain rather than match loosely."""
    tokens = [t for t in re.split(r"[、/()（）\s—·,，:：和与及的]+", core) if len(t) >= 2]
    meaningful = [t for t in tokens if t not in _GENERIC_TOKENS]
    return bool(meaningful)


def _parse_headings(markdown: str) -> list[tuple[int, int, int, str]]:
    """Return [(start_offset, level, title_end_offset, normalized_title)] for each
    heading-like anchor, in document order.

    Three anchor kinds, in descending precedence (lower level number = wins):
    - ATX ``#{1,6}`` headings (levels 1..6) — the authoritative structure;
    - bold-only title lines (``**…**`` on their own line) — pseudo-level 7;
    - enumerated paragraph openers (``（N）…`` / ``N) …`` / ``① …``) — pseudo-level
      8, the last-resort anchor for chunks that carry no ATX/bold headings.

    A line that already matched a higher-precedence kind is never re-emitted as a
    lower-precedence one (offsets are de-duplicated by line)."""
    out: list[tuple[int, int, int, str]] = []
    seen_starts: set[int] = set()

    for m in _HEADING_RE.finditer(markdown):
        level = len(m.group(1))
        title = _strip_enumerator(m.group(2))
        out.append((m.start(), level, m.end(), title))
        seen_starts.add(_line_start(markdown, m.start()))

    for m in _BOLD_HEADING_RE.finditer(markdown):
        ls = _line_start(markdown, m.start())
        if ls in seen_starts:
            continue
        title = _strip_enumerator(m.group(1))
        out.append((m.start(), _ATX_LEVEL_BOLD, m.end(), title))
        seen_starts.add(ls)

    for m in _ENUM_LINE_RE.finditer(markdown):
        ls = _line_start(markdown, m.start())
        if ls in seen_starts:
            continue
        # Title = the enumerated line's text with its enumerator stripped.
        line_end = markdown.find("\n", m.start())
        line_end = len(markdown) if line_end == -1 else line_end
        title = _strip_enumerator(markdown[m.start():line_end])
        out.append((m.start(), _ATX_LEVEL_ENUM, m.end(), title))
        seen_starts.add(ls)

    out.sort(key=lambda h: h[0])
    return out


def _line_start(markdown: str, offset: int) -> int:
    nl = markdown.rfind("\n", 0, offset)
    return 0 if nl == -1 else nl + 1


def _section_span(markdown: str, headings: list[tuple[int, int, int, str]], idx: int) -> str:
    """Text from heading ``idx`` up to the next heading of same-or-higher level."""
    start, level, _, _ = headings[idx]
    end = len(markdown)
    for nxt_start, nxt_level, _, _ in headings[idx + 1 :]:
        if nxt_level <= level:
            end = nxt_start
            break
    return markdown[start:end].strip()


def _preamble_span(markdown: str, headings: list[tuple[int, int, int, str]], idx: int) -> str:
    """Parent heading + intro text UP TO the first deeper child heading.

    A parent leaf must NOT swallow a child sibling leaf's subsection. Its span is
    only the heading line plus the preamble paragraph(s) before the first heading
    of a strictly deeper level. If there is no deeper child, this equals
    ``_section_span``."""
    start, level, _, _ = headings[idx]
    end = len(markdown)
    for nxt_start, nxt_level, _, _ in headings[idx + 1 :]:
        if nxt_level <= level:  # sibling or higher -> normal section end
            end = nxt_start
            break
        # deeper child heading -> parent preamble stops here
        end = nxt_start
        break
    return markdown[start:end].strip()


def _title_matches_core(title: str, core: str) -> int:
    """Match tier between a heading title and a leaf core. Higher = more specific.

    3 EXACT   — title == core.
    2 FORWARD — core appears inside the title (the trustworthy direction: the
                heading is more specific than the leaf, e.g. core 混凝土 in title
                混凝土的强度).
    1 REVERSE — title is a SAFE terser form of the core: title is a prefix of core
                and the only remainder is a qualifier tail (全站仪 ⊂ 全站仪测量).
                Plain substring reverse (窗 ⊂ 天窗) is REJECTED — that is the
                wrong-slice trap.
    0         — no match.
    """
    if not title or not core:
        return 0
    # EXACT / FORWARD compare on separator-normalized forms so the SAME topic
    # written with different separators still matches (一类土：松软土 vs
    # 一类土（松软土）). NARROW: normalization is separators-only and is applied
    # ONLY to these two safe tiers — it never reaches the reverse-prefix logic
    # below, so the unsafe-substring-reverse guard (窗 ⊂ 天窗) is unchanged.
    n_title = _normalize_separators(title)
    n_core = _normalize_separators(core)
    if n_title and n_core:
        if n_title == n_core:
            return 3
        if n_core in n_title:
            return 2
    if len(title) >= 2 and core.startswith(title):
        remainder = core[len(title):]
        if _QUALIFIER_TAIL_RE.match(remainder):
            return 1
    return 0


def _span_hosts_sibling(span: str, leaf_core: str, sibling_cores: list[str]) -> bool:
    """Negative check: does ``span`` contain a HEADING that belongs to some OTHER
    co-located leaf rather than to this one? If so, the span is not purely this
    leaf's — abstain.

    Only heading-anchored sibling presence counts (a sibling core merely mentioned
    in prose is fine — cross-references are normal). A heading is attributed to a
    sibling only when that sibling matches it STRICTLY MORE SPECIFICALLY than the
    leaf's own core does. This rejects the false positive where the leaf's own
    heading superstrings a sibling name (天窗的设置规定 superstrings 窗的设置规定):
    the leaf core EXACT-matches its own heading (tier 3) while the sibling only
    forward-matches it (tier 2), so the leaf — not the sibling — owns it.
    """
    if not sibling_cores:
        return False
    for _, _level, _, title in _parse_headings(span):
        if not title:
            continue
        leaf_tier = _title_matches_core(title, leaf_core)
        for sib in sibling_cores:
            if not sib:
                continue
            if _title_matches_core(title, sib) > leaf_tier:
                return True
    return False


def slice_leaf_subsection(
    markdown: str,
    leaf_name: str,
    *,
    chunk_hosts_multiple_leaves: bool,
    sibling_cores: tuple[str, ...] = (),
) -> Subsection | None:
    """Locate the subsection that belongs to ``leaf_name`` inside ``markdown``.

    Returns a ``Subsection`` (the leaf's OWN span) on a deterministic match, or
    ``None`` when no distinct subsection can be located. ``None`` MUST be treated
    by the caller as quarantine — never as "use the whole chunk".

    ``sibling_cores`` are the discriminative cores of the OTHER leaves co-located
    under the same chunk. They drive the negative check: an accepted span must not
    host any sibling's heading.

    Deterministic rules (abstain-on-doubt):

    1. ``core`` = discriminative core of the leaf name. Non-discriminative
       (pure-generic) core -> ``None`` immediately.
    2. Score every heading anchor by ``_title_matches_core`` (EXACT > FORWARD >
       safe-REVERSE; unsafe substring reverse scores 0). Keep the highest tier.
       Zero matches -> rule 5. Ambiguous tie at the best tier -> ``None``.
    3. For the unique best heading, take its section span. If that span still hosts
       a sibling's heading (i.e. the leaf owns a PARENT whose children belong to
       siblings), narrow to the parent preamble (heading + intro before the first
       child).
    4. POSITIVE check: the leaf core must appear in the chosen span. NEGATIVE
       check: no sibling core may anchor a heading in the chosen span. Either
       check failing -> ``None``.
    5. No heading match -> ``None`` (quarantine), for EVERY lane. There is no
       whole-chunk fallback: "core appears in body" does not prove the chunk is
       solely about this leaf, so returning the whole chunk would re-mint the
       original pollution. ``chunk_hosts_multiple_leaves`` only guards the
       defense-in-depth check in rule 3 — a heading whose section IS the whole
       chunk distinguishes nothing under a multi-leaf chunk (abstain) but is the
       legitimate own-span of a 1:1 leaf↔chunk (keep).
    """
    md = str(markdown or "")
    core = leaf_name_core(leaf_name)
    if not core or not _is_discriminative(core):
        return None

    sibs = [s for s in (sibling_cores or ()) if s and s != core]
    headings = _parse_headings(md)

    scored: list[tuple[int, int]] = []  # (tier, idx)
    for idx, (_, _level, _, title) in enumerate(headings):
        tier = _title_matches_core(title, core)
        if tier:
            scored.append((tier, idx))

    if not scored:
        # No heading matched the leaf name -> no distinct subsection can be
        # located. ABSTAIN, uniformly for every lane. There is NO whole-chunk
        # fallback: "the leaf core appears in the body" does NOT prove the chunk
        # is solely about this leaf (the core may be merely mentioned while the
        # chunk covers several topics), so handing back the whole chunk re-mints
        # the original 名实不符 pollution. A 1:1 leaf↔chunk is not a license for a
        # looser rule than the multi-leaf lane gets — None always means quarantine
        # (see module docstring "Single rule for every lane").
        return None

    best_tier = max(t for t, _ in scored)
    best = [idx for t, idx in scored if t == best_tier]
    if len(best) != 1:
        return None  # ambiguous -> never guess

    idx = best[0]
    _, level, _, title = headings[idx]
    span = _section_span(md, headings, idx)

    # If the leaf's own section still hosts a sibling heading, the leaf owns a
    # PARENT whose children belong to siblings — narrow to the parent preamble.
    if _span_hosts_sibling(span, core, sibs):
        span = _preamble_span(md, headings, idx)

    # Defense-in-depth (holds even when ``sibling_cores`` is empty): under a
    # multi-leaf chunk, a span that IS the whole chunk does NOT distinguish this
    # leaf from its co-located siblings — handing it over is the original
    # whole-chunk pollution. Abstain. Legitimate parent leaves have already been
    # narrowed to their preamble above, so this only fires for chunks with no
    # internal structure to slice (genuinely unsliceable -> quarantine).
    if chunk_hosts_multiple_leaves and span.strip() == md.strip():
        return None

    # Positive + negative gate.
    # POSITIVE: the matched heading is the leaf's own anchor (established by tier
    # above) and must still be present in the (possibly preamble-narrowed) span.
    # We assert the matched HEADING TITLE — not the raw core — because a safe
    # reverse match (全站仪 ⊂ 全站仪测量) anchors on a terser heading whose exact
    # leaf core never appears verbatim in the prose.
    if title and title not in span:
        return None
    # NEGATIVE: no OTHER co-located sibling may anchor a heading inside the span.
    if _span_hosts_sibling(span, core, sibs):
        return None
    return Subsection(heading_title=title, heading_level=level, text=span)


__all__ = [
    "Subsection",
    "leaf_name_core",
    "slice_leaf_subsection",
]
