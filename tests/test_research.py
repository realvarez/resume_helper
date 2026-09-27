import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.research import (
    _format_results,
    _role_words,
    build_research_context,
)


def test_role_words_extraction():
    jd = "Senior Python Backend Engineer building distributed cloud systems at scale"
    assert _role_words(jd, max_words=4) == "Senior Python Backend Engineer"

    # Non-ascii filtered
    jd_mixed = "Senior Engineer 🚀 with Rust & Go skills"
    assert "🚀" not in _role_words(jd_mixed)


def test_format_results():
    results = [
        {"title": "Shopify Tech Blog", "url": "https://shopify.engineering", "content": "Our Kafka architecture"},
        {"title": "Glassdoor", "url": "", "content": "Great engineering culture"},
    ]
    formatted = _format_results("TECH_STACK", results)
    assert "### TECH_STACK" in formatted
    assert "- Shopify Tech Blog (https://shopify.engineering): Our Kafka architecture" in formatted
    assert "- Glassdoor: Great engineering culture" in formatted


@pytest.mark.asyncio
async def test_build_research_context_no_api_key():
    with patch("app.services.research.get_settings") as mock_settings:
        mock_settings.return_value.tavily_api_key = None
        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH: unavailable (no TAVILY_API_KEY configured)" in context


@pytest.mark.asyncio
async def test_build_research_context_success():
    fake_results = [
        {"title": "Overview", "url": "https://example.com", "content": "E-commerce platform"}
    ]

    with patch("app.services.research.get_settings") as mock_settings, \
         patch("app.services.research._search_sync", return_value=fake_results):
        mock_settings.return_value.tavily_api_key = "fake-key"
        mock_settings.return_value.tavily_max_results = 2

        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH RESULTS (source snippets gathered just now for 'Shopify'):" in context
        assert "Overview (https://example.com): E-commerce platform" in context


@pytest.mark.asyncio
async def test_build_research_context_all_queries_fail():
    with patch("app.services.research.get_settings") as mock_settings, \
         patch("app.services.research._search_sync", side_effect=RuntimeError("Network error")):
        mock_settings.return_value.tavily_api_key = "fake-key"

        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH: all queries failed" in context


@pytest.mark.asyncio
async def test_build_research_context_uses_cache(monkeypatch, tmp_path):
    from app.services.storage import StorageRepository
    test_storage = StorageRepository(tmp_path / "research_cache.db")
    test_storage.cache_research("Acme Corp", "Cached Acme Dossier")
    monkeypatch.setattr("app.services.research.get_storage", lambda: test_storage)

    called_search = False

    def fake_search(*args, **kwargs):
        nonlocal called_search
        called_search = True
        return []

    monkeypatch.setattr("app.services.research._search_sync", fake_search)
    result = await build_research_context("Acme Corp", "Some JD")
    assert result == "Cached Acme Dossier"
    assert called_search is False

