"""Hacker News front-page sourcing via Algolia (top points, last 48h).

Different from `hacker_news.py` (which is Show HN). This pulls broad HN front-page
items so the pipeline catches launch announcements, fundraising posts, and
notable open-source projects that aren't tagged Show HN.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from src.models import Deal, DealSource


HN_API = "https://hn.algolia.com/api/v1/search"


async def source_hn_frontpage(limit: int = 30) -> list[Deal]:
    cutoff = int((datetime.utcnow() - timedelta(days=2)).timestamp())
    params = {
        "tags": "front_page",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": limit,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(HN_API, params=params)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as e:
            print(f"HN front_page fetch failed: {e}")
            return []

    deals: list[Deal] = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        url = hit.get("url")
        oid = hit.get("objectID", "")
        deals.append(
            Deal(
                startup_name=title[:120],
                website=url,
                description=hit.get("story_text") or title,
                source=DealSource.HN_FRONTPAGE,
                source_url=f"https://news.ycombinator.com/item?id={oid}",
                discovered_at=datetime.utcnow(),
            )
        )
    return deals
