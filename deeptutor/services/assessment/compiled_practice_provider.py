"""编译轻练权威的组卷读侧聚合 provider（表单 v2 §6.2-v2 选型定稿）。

单一权威铁律：
- **读侧聚合，不是入库**——本模块只读 ``luban_lesson`` 的 compiled practice
  authority（``load_compiled_practice`` 全链闸：manifest 登记 + authority sha +
  公开投影 sha），不写 ``questions_bank``、不复制数据、不造第二题库。
- **资格谓词同一杆枪**——逐题资格由 ``practice_html._eligible``（双签结构 +
  五 checks + revoked）同一谓词裁决，本模块零平行判定；只取
  eligible∧signed 的 ``single_choice`` 成品题。
- **元数据透传**——pack / fact（leaf）/ skeleton / rule_group（采分点）/
  anchor（真题难度锚）原样进 ``source_meta``，供报告归因与 §6.5 等值配对
  判据消费；不读、不派生 ``questions_bank.difficulty``（该列量纲混乱，
  盘点 2026-08-06 实证不可用——难度权威是变体 anchor）。

blueprint sections 通过 ``question_source="compiled_practice"`` +
``compiled_packs=(...)`` 声明消费本读源；``SourceRoutedAssessmentQuestionProvider``
按 section 声明路由，questions_bank 语义零改动。
"""

from __future__ import annotations

import re
from typing import Any

from deeptutor.services.assessment.blueprint import (
    COMPILED_PRACTICE_QUESTION_SOURCE,
    COMPILED_PRACTICE_SOURCE_TYPE,
    AssessmentSection,
)
from deeptutor.services.assessment.blueprint_service import (
    AssessmentQuestionProvider,
    QuestionCandidate,
    _built_form_source,
    _select_diagnostic_candidates,
)

_OPTION_LETTERS = "ABCDEFGH"
_NODE_CODE_RE = re.compile(r"^(?:kc|ca|cc):(1A\d{6})")


def _candidate_from_compiled_item(
    pack_id: str, item: dict[str, Any], section: AssessmentSection
) -> QuestionCandidate | None:
    """authority 原行 → 组卷 candidate 的只读投影。

    只透出学员可见面（stem + 选项文本）与判分所需的正确项字母；选项级
    is_correct / temptation / loss_reason / fix 等答案面不进消费投影。
    单选合同 fail-closed：非恰好一个正确项 → 不供给。
    """
    stem = str(item.get("stem") or "").strip()
    variant_id = str(item.get("variant_id") or "").strip()
    raw_options = [opt for opt in list(item.get("options") or []) if isinstance(opt, dict)]
    if not stem or not variant_id or not (2 <= len(raw_options) <= len(_OPTION_LETTERS)):
        return None
    options: list[tuple[str, str]] = []
    correct_letters: list[str] = []
    # 报告面诊断:逐选项 temptation/loss_reason/fix 是签发权威里已审的教学内容,
    # 只做只读投影(不进 client,见 blueprint_service._build_scored_question)。
    option_diagnosis: dict[str, dict[str, str]] = {}
    for index, option in enumerate(raw_options):
        letter = _OPTION_LETTERS[index]
        text = str(option.get("text") or "").strip()
        if not text:
            return None
        options.append((letter, text))
        if option.get("is_correct") is True:
            correct_letters.append(letter)
        diagnosis = {
            "pitfall": str(option.get("temptation") or "").strip(),
            "why_missed": str(option.get("loss_reason") or "").strip(),
            "fix": str(option.get("fix") or "").strip(),
            "error_code": str(option.get("source_error_code") or "").strip(),
        }
        if any(diagnosis.values()):
            option_diagnosis[letter] = diagnosis
    if len(correct_letters) != 1:
        return None
    source_anchor = str(item.get("source_anchor") or "").strip()
    fact_id = str(item.get("fact_id") or "").strip()
    rule_group = str(item.get("rule_group") or "").strip()
    node_match = _NODE_CODE_RE.match(source_anchor)
    source_meta: dict[str, Any] = {
        "aggregation": "compiled_practice_readside",
        "pack_id": pack_id,
        "fact_id": fact_id,
        "skeleton_id": str(item.get("skeleton_id") or ""),
        "rule_group": rule_group,
        "probe_role": str(item.get("probe_role") or ""),
        "surface_id": str(item.get("surface_id") or ""),
        "source_anchor": source_anchor,
        "anchor": str(item.get("anchor") or ""),
        "content_sha256": str(item.get("content_sha256") or ""),
        "source_sha256": str(item.get("source_sha256") or ""),
        # §6.5 难度锚：变体 anchor（kc:leaf + 真题年份题号）是唯一难度权威，
        # 不读 questions_bank.difficulty。
        "difficulty_anchor": source_anchor,
        # 同 fact 的三件套（anchor/confirm/d1）在一张表单内互为近重复——
        # 以 fact 为语义签名，走既有 semantic_signature 去重通道。
        "semantic_signature": f"compiled:{pack_id}:{fact_id or variant_id}",
    }
    return QuestionCandidate(
        source_question_id=variant_id,
        question_stem=stem,
        question_type="single_choice",
        chapter=rule_group or section.label,
        options=tuple(options),
        answer=correct_letters[0],
        difficulty="medium",
        source_type=COMPILED_PRACTICE_SOURCE_TYPE,
        source_chunk_id="",
        node_code=node_match.group(1) if node_match else "",
        source_meta=source_meta,
        answer_diagnosis={
            "scoring_point": rule_group,
            "model_answer": str(item.get("model_answer") or "").strip(),
            "source": source_anchor,
            "options": option_diagnosis,
        },
    )


class CompiledPracticeAssessmentQuestionProvider:
    """按 section 声明的 pack 车道读取编译轻练权威（只读聚合）。

    pack 级 fail-closed：任一 pack 的 authority 闸不过（登记缺失 / sha 漂移 /
    公开投影失配）即整包不供给，绝不半开；余下 pack 照常供给，section 不足
    额由上层 ``AssessmentBlueprintUnavailable`` 兜底。
    """

    def __init__(self) -> None:
        # 延迟绑定 luban_lesson，读取时才触碰 authority 文件。
        from deeptutor.services.luban_lesson import practice_html

        self._practice_html = practice_html

    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
        selection_seed: str = "",
        avoid_chapters: set[str] | None = None,
    ) -> list[QuestionCandidate]:
        candidates: list[QuestionCandidate] = []
        for pack in section.compiled_packs:
            pack_id = str(pack or "").strip().upper()
            if not pack_id:
                continue
            try:
                authority = self._practice_html.load_compiled_practice(pack_id)
            except self._practice_html.PracticeHtmlInvalid:
                continue  # fail-closed：闸不过的 pack 整包不供给
            if authority is None:
                continue
            for item in authority.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if not self._practice_html._eligible(item):
                    continue  # eligible∧signed 同一谓词，零平行判定
                if str(item.get("answer_type") or "") != "single_choice":
                    continue
                candidate = _candidate_from_compiled_item(pack_id, item, section)
                if candidate is None or candidate.source_question_id in exclude_source_ids:
                    continue
                candidates.append(candidate)
        return _select_diagnostic_candidates(
            candidates,
            section=section,
            limit=limit,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters or set(),
        )

    def question_bank_size(self) -> int:
        # 编译读源的规模依 section 声明而变，不给全局数；规模口径归默认供给面。
        return 0


class SourceRoutedAssessmentQuestionProvider:
    """按 section ``question_source`` 声明路由到编译读源或默认供给面。

    除 ``get_candidates`` 的路由外，其余能力（持久化表单 bank / 缓存 key /
    题库规模）全部委托默认 provider——不新建第二套持久化或缓存 authority。
    """

    def __init__(
        self,
        *,
        default_provider: AssessmentQuestionProvider,
        compiled_provider: CompiledPracticeAssessmentQuestionProvider | None = None,
    ) -> None:
        self._default = default_provider
        self._compiled = compiled_provider or CompiledPracticeAssessmentQuestionProvider()

    @property
    def form_source_label(self) -> str:
        return f"{_built_form_source(self._default)}+compiled_practice"

    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
        selection_seed: str = "",
        avoid_chapters: set[str] | None = None,
    ) -> list[QuestionCandidate]:
        provider: AssessmentQuestionProvider
        if section.question_source == COMPILED_PRACTICE_QUESTION_SOURCE:
            provider = self._compiled
        else:
            provider = self._default
        return provider.get_candidates(
            section,
            limit=limit,
            exclude_source_ids=exclude_source_ids,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._default, name)


__all__ = [
    "CompiledPracticeAssessmentQuestionProvider",
    "SourceRoutedAssessmentQuestionProvider",
]
