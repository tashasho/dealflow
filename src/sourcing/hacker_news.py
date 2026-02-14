"""Hacker News sourcing via Algolia API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx

from src.config import Config
from src.models import Deal, DealSource


class HackerNewsScraper:
    """Client for HN Algolia API."""

    BASE_URL = "http://hn.algolia.com/api/v1/search_by_date"

    async def fetch_show_hn(self) -> list[Deal]:
        """Fetch recent 'Show HN' posts with enterprise keywords."""
        
        # Enterprise/AI keywords
        query = '(enterprise OR B2B OR automation OR agent OR LLM) AND "Show HN"'
        
        # Last 24 hours
        yesterday_ts = int((datetime.utcnow() - timedelta(days=1)).timestamp())
        
        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{yesterday_ts},points>10", # Filter for some traction
            "hitsPerPage": 20
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"Error fetching HN: {e}")
                return []

        deals = []
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            if not title.startswith("Show HN"):
                continue

            deal = Deal(
                startup_name=title.replace("Show HN:", "").strip(),
                website=hit.get("url"),
                description=hit.get("story_text") or title,
                source=DealSource.MANUAL, # TODO: Add HN to DealSource
                source_url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                discovered_at=datetime.utcnow()
            )
            deals.append(deal)

        return deals

async def source_hacker_news() -> list[Deal]:
    scraper = HackerNewsScraper()
    return await scraper.fetch_show_hn()
