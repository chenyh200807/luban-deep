from __future__ import annotations

from deeptutor.services.tutorbot.manager import _append_web_search_sources_if_missing


def test_append_web_search_sources_when_model_omits_urls() -> None:
    response = "2026年一级建造师考试时间为9月12日、13日。"
    sources = [
        {
            "title": "2026年度专业技术人员职业资格考试工作计划",
            "url": "https://example.gov/plan.pdf",
        }
    ]

    result = _append_web_search_sources_if_missing(response, sources)

    assert "### 联网来源" in result
    assert "https://example.gov/plan.pdf" in result


def test_append_web_search_sources_skips_when_url_already_present() -> None:
    response = "来源：https://example.gov/plan.pdf"
    sources = [
        {
            "title": "2026年度专业技术人员职业资格考试工作计划",
            "url": "https://example.gov/plan.pdf",
        }
    ]

    result = _append_web_search_sources_if_missing(response, sources)

    assert result == response
