"""GitHub Trending scraper — finds enterprise AI repos with viral breakout signals."""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.config import Config
from src.models import Deal, DealSource, Founder, GitHubMetrics


# Keywords that flag enterprise-focused repos
ENTERPRISE_KEYWORDS = re.compile(
    r"\b(SAML|SOC\s?2|on-prem|RBAC|SSO|HIPAA|GDPR|audit.?log|self-hosted|"
    r"enterprise|compliance|multi-tenant)\b",
    re.IGNORECASE,
)

# Topic keywords we care about
TOPIC_KEYWORDS = [
    "agent",
    "llm-ops",
    "llmops",
    "enterprise-automation",
    "rag",
    "agentic",
    "ai-agent",
    "langchain",
    "llamaindex",
]

TRENDING_URL = "https://github.com/trending"
API_BASE = "https://api.github.com"


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if Config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
    return h


def _matches_topics(description: str, topics: list[str]) -> bool:
    """Check if description or topics overlap with our keywords."""
    text = " ".join([description.lower()] + [t.lower() for t in topics])
    return any(kw in text for kw in TOPIC_KEYWORDS)


def _extract_enterprise_signals(readme: str) -> list[str]:
    """Pull enterprise keywords from a README."""
    return list({m.group(0).upper() for m in ENTERPRISE_KEYWORDS.finditer(readme)})


async def scrape_trending(language: str = "", since: str = "weekly") -> list[dict]:
    """Scrape the GitHub trending page for repos."""
    params: dict[str, str] = {}
    if language:
        params["language"] = language
    if since:
        params["since"] = since

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(TRENDING_URL, params=params)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    repos: list[dict] = []

    for article in soup.select("article.Box-row"):
        # Repo name
        name_el = article.select_one("h2 a")
        if not name_el:
            continue
        full_name = name_el.get("href", "").strip("/")  # e.g. "owner/repo"
        if not full_name:
            continue

        # Description
        desc_el = article.select_one("p")
        desc = desc_el.get_text(strip=True) if desc_el else ""

        # Stars today
        stars_text = ""
        stars_el = article.select_one("span.d-inline-block.float-sm-right")
        if stars_el:
            stars_text = stars_el.get_text(strip=True)
        weekly_stars = 0
        m = re.search(r"([\d,]+)\s+stars?\s+", stars_text)
        if m:
            weekly_stars = int(m.group(1).replace(",", ""))

        # Total stars
        total_stars = 0
        star_links = article.select("a.Link--muted")
        for sl in star_links:
            href = sl.get("href", "")
            if "/stargazers" in href:
                st = sl.get_text(strip=True).replace(",", "")
                if st.isdigit():
                    total_stars = int(st)
                break

        repos.append({
            "full_name": full_name,
            "description": desc,
            "stars": total_stars,
            "weekly_stars": weekly_stars,
            "url": f"https://github.com/{full_name}",
        })

    return repos


async def _get_repo_details(client: httpx.AsyncClient, full_name: str) -> dict:
    """Fetch repo metadata + README from the GitHub API."""
    resp = await client.get(f"{API_BASE}/repos/{full_name}", headers=_headers())
    if resp.status_code != 200:
        return {}
    data = resp.json()

    # Fetch README
    readme = ""
    readme_resp = await client.get(
        f"{API_BASE}/repos/{full_name}/readme",
        headers={**_headers(), "Accept": "application/vnd.github.raw+json"},
    )
    if readme_resp.status_code == 200:
        readme = readme_resp.text[:5000]  # cap to avoid huge READMEs

    return {
        "topics": data.get("topics", []),
        "description": data.get("description", ""),
        "stargazers_count": data.get("stargazers_count", 0),
        "open_issues_count": data.get("open_issues_count", 0),
        "contributors_url": data.get("contributors_url", ""),
        "readme": readme,
        "owner": data.get("owner", {}),
    }


async def source_github(limit: int = 20) -> list[Deal]:
    """
    Main entry point: scrape trending, filter for enterprise AI repos,
    enrich with API data, and return Deal objects.
    """
    trending = await scrape_trending()
    deals: list[Deal] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for repo in trending[:limit]:
            details = await _get_repo_details(client, repo["full_name"])
            if not details:
                continue

            topics = details.get("topics", [])
            desc = details.get("description", "") or repo["description"]

            # Filter: must match our topic keywords
            if not _matches_topics(desc, topics):
                continue

            # Enterprise signals
            readme = details.get("readme", "")
            enterprise_signals = _extract_enterprise_signals(readme)

            # Viral breakout: 500+ stars in a week
            weekly_stars = repo.get("weekly_stars", 0)

            github_metrics = GitHubMetrics(
                repo_url=repo["url"],
                stars=details.get("stargazers_count", repo["stars"]),
                star_velocity_7d=weekly_stars,
                open_issues=details.get("open_issues_count", 0),
                enterprise_signals=enterprise_signals,
                readme_snippet=readme[:1000] if readme else None,
            )

            # Build founder stub from repo owner
            owner = details.get("owner", {})
            founders = []
            if owner.get("type") == "User":
                founders.append(Founder(
                    name=owner.get("login", "unknown"),
                    linkedin_url=None,
                    background=f"GitHub: {owner.get('html_url', '')}",
                ))

            deal = Deal(
                startup_name=repo["full_name"].split("/")[-1],
                website=repo["url"],
                description=desc,
                founders=founders,
                github=github_metrics,
                source=DealSource.GITHUB,
                source_url=repo["url"],
                discovered_at=datetime.utcnow(),
            )
            deals.append(deal)

    return deals
