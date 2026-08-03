from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CitationState = Literal["supported", "partial", "no_public_source", "degraded"]
CitationSurface = Literal["student", "reviewer", "internal"]

# 「这条来源能不能给学生看」的**唯一事实源** = `HIDDEN_AUTHORITY_FIELDS` 命中
# (`citations/redaction.py`) × `CitationPolicy.surface` 语义,消费点只有一个:
# `normalizer._public_source_candidates` / `_is_hidden_source` —— 命中即**整条来源
# 丢弃**,压根不构造 ref。reviewer/internal 面故意不丢(审阅者本就该看到答案 key)。
#
# 历史包袱(2026-08-03 移除):`CitationSourceRef` 曾带一个 `visibility` 字段 +
# `is_public` + `to_public_dict()` 里的 `return {}` 分支。它**先天没有写入方**——
# 唯一构造点 `normalizer.py` 从不传该字段,数据面(supabase/migrations)也没有任何
# visibility/is_public 列,于是永远吃默认值 "public",脱敏分支在生产执行 0 次
# (runtime 插桩实证:58/58 次构造全部默认 public)。留着它的唯一效果是让审计者
# 误判"这里有一道活防线"(已实际误导过一次静态审计)。按单一权威原则删除;
# 要恢复"逐来源可见性"必须先在数据面定义权威,不能再靠一个默认值假装有门。
#
# 已知缺口(未修,推荐方向):`_public_quote()` 的取值链含 `value`,一旦上面那个
# 唯一消费点失效,答案值/采分点正文会原样进 public_quote,而 quality.py 与
# unified_ws `_redact_event_for_public` 都只匹配**字段名**、抓不到**字段值**。
# 真加固方向 = 给 public_quote 加值级溯源闸(必须追到非 hidden 字段的来源)。
# 该项改动引用装配语义,待 owner 拍板,勿在此处顺手加 fallback。


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
    authority_rank: int = 0
    evidence_level: str = ""

    def to_public_dict(self) -> dict[str, Any]:
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
            # refs 已在 normalizer 侧完成公开性裁剪(见本文件顶部注释),
            # 这里不再二次过滤 —— to_public_dict() 恒返回非空。
            "refs": [ref.to_public_dict() for ref in self.refs],
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
