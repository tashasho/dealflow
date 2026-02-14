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
        start_year = "2025-01-01"

        # Queries from Phase 1
        # Queries from Phase 1
        # B2: GitHub Advanced Search (New Enterprise Repos)
        topics = ["enterprise-ai", "b2b-saas", "llm-orchestration"]
        
        all_items = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for topic in topics:
                query = f"created:>{start_year} stars:>100 topic:{topic}"
                params = {"q": query, "sort": "stars", "order": "desc", "per_page": 20}

                resp = await client.get(f"{self.API_BASE}/search/repositories", headers=self._headers(), params=params)
                if resp.status_code != 200:
                    print(f"GitHub Search failed for topic {topic}: {resp.text}")
                    continue
                
                data = resp.json()
                all_items.extend(data.get("items", []))

        # Deduplicate items by ID
        seen_ids = set()
        unique_items = []
        for item in all_items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                unique_items.append(item)

        # Limit to requested limit (approx)
        data = {"items": unique_items} # Mock structure to reuse loop below
        items = unique_items

        deals = []
        for item in items:
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

async def source_github_search(limit: int = 20) -> list[Deal]:
    searcher = GitHubSearcher()
    # We could pass limit to searcher methods too, but for now just signature fix
    return await searcher.search_new_enterprise_repos()
