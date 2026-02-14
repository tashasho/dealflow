"""GitHub Advanced Search sourcing."""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from src.config import Config
from src.models import Deal, DealSource, Founder, GitHubMetrics


class GitHubSearcher:
    """Client for GitHub Search API."""

    API_BASE = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json"}
        if Config.GITHUB_TOKEN:
            h["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
        return h

    async def search_new_enterprise_repos(self) -> list[Deal]:
        """Search for recently created enterprise repos."""
        
        # Created since beginning of year or last 30 days
        since_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        query = f"created:>{since_date} stars:>50 topic:enterprise-ai OR topic:b2b-saas OR topic:llm-orchestration"
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.API_BASE}/search/repositories", headers=self._headers(), params=params)
            if resp.status_code != 200:
                print(f"GitHub Search failed: {resp.text}")
                return []
            
            data = resp.json()

        deals = []
        for item in data.get("items", []):
            full_name = item.get("full_name")
            desc = item.get("description") or ""
            url = item.get("html_url")
            stars = item.get("stargazers_count", 0)
            
            # Basic validation
            if not desc:
                continue

            owner = item.get("owner", {})
            founders = []
            if owner.get("type") == "User":
                founders.append(Founder(
                    name=owner.get("login"),
                    background=owner.get("html_url")
                ))

            deal = Deal(
                startup_name=full_name.split("/")[-1],
                website=item.get("homepage") or url,
                description=desc,
                founders=founders,
                github=GitHubMetrics(
                    repo_url=url,
                    stars=stars,
                    open_issues=item.get("open_issues_count", 0)
                ),
                source=DealSource.GITHUB,
                source_url=url,
                discovered_at=datetime.utcnow()
            )
            deals.append(deal)

        return deals

async def source_github_search() -> list[Deal]:
    searcher = GitHubSearcher()
    return await searcher.search_new_enterprise_repos()
