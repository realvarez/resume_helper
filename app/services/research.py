"""Optional live company research via the Tavily search API.

If no ``TAVILY_API_KEY`` is configured the pipeline degrades gracefully to
LLM-only knowledge (the generator is told research was unavailable).
"""
import asyncio
import logging

from app.config import TARGET_COUNTRY, get_settings
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

# (label, query template) — role/company are substituted at call time.
# Company-specific queries run only when a target company was provided; the
# market-norms query always runs.
COMPANY_QUERY_TEMPLATES = [
    ("COMPANY_OVERVIEW", "{company} company what they do products services customers"),
    ("INTERVIEW_PROCESS", "{company} interview process {role_words} hiring stages"),
    ("TECH_STACK", "{company} engineering tech stack blog"),
    ("CULTURE", "{company} company culture values careers"),
]
MARKET_NORMS_QUERY = (
    f"MARKET_NORMS_{TARGET_COUNTRY.upper()}",
    f"resume CV conventions and job application norms in {TARGET_COUNTRY}",
)


def _role_words(job_description: str, max_words: int = 12) -> str:
    """A short keyword slice of the JD to focus interview-process searches."""
    words = [w for w in job_description.split() if w.isascii()][:max_words]
    return " ".join(words)


def _format_results(label: str, results: list[dict]) -> str:
    lines = [f"### {label}"]
    for r in results:
        content = (r.get("content") or "").strip()
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = content[:1200]
        lines.append(f"- {title} ({url}): {snippet}" if url else f"- {title}: {snippet}")
    return "\n".join(lines)


def _search_sync(query: str) -> list[dict]:
    from tavily import TavilyClient  # imported lazily so the app runs without the package's key

    client = TavilyClient(get_settings().tavily_api_key)
    response = client.search(query=query, max_results=get_settings().tavily_max_results,
                             search_depth="basic")
    return response.get("results", [])


async def build_research_context(company: str, job_description: str) -> str:
    """Run all research queries in parallel; returns a formatted context block.

    Returns a short note instead when no API key is configured.
    """
    company_name = company.strip()
    if company_name:
        storage = get_storage()
        cached = storage.get_cached_research(company_name, max_age_days=14)
        if cached:
            logger.info("Using cached company research for %r", company_name)
            return cached

    settings = get_settings()
    if not settings.tavily_api_key:
        return (
            "WEB RESEARCH: unavailable (no TAVILY_API_KEY configured). "
            "Rely on your existing knowledge of the company, but be honest about uncertainty."
        )

    role_words = _role_words(job_description)
    queries = [
        (label, tpl.format(company=company, role_words=role_words))
        for label, tpl in COMPANY_QUERY_TEMPLATES
        if company_name
    ]
    queries.append(MARKET_NORMS_QUERY)

    async def safe_search(label: str, query: str) -> str | None:
        try:
            results = await asyncio.to_thread(_search_sync, query)
            return _format_results(label, results) if results else None
        except Exception as exc:  # noqa: BLE001 — one failed query must not kill the pipeline
            logger.warning("Research query failed (%s): %s", label, exc)
            return None

    sections = await asyncio.gather(*(safe_search(label, q) for label, q in queries))
    found = [s for s in sections if s]
    if not found:
        return (
            "WEB RESEARCH: all queries failed. "
            "Rely on your existing knowledge of the company, but be honest about uncertainty."
        )
    if company_name:
        header = f"WEB RESEARCH RESULTS (source snippets gathered just now for '{company}'):"
    else:
        header = f"WEB RESEARCH RESULTS ({TARGET_COUNTRY} job-market snippets gathered just now):"
    result_text = header + "\n\n" + "\n\n".join(found)
    if company_name:
        get_storage().cache_research(company_name, result_text)
    return result_text
