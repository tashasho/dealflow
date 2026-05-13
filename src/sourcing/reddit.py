"""Reddit sourcing via public JSON endpoints (no API key needed).

Pulls top posts from startup-relevant subreddits over the last week.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from src.models import Deal, DealSource


SUBREDDITS = [
    "SideProject",
    "SaaS",
    "startups",
    "EntrepreneurRideAlong",
    "LocalLLaMA",
    "MachineLearning",
    "LangChain",
    "ArtificialIntelligence",
]

UA = "dealflow-bot/1.0 (+https://github.com/tashasho/dealflow)"


async def source_reddit(limit: int = 10) -> list[Deal]:
    deals: list[Deal] = []
    async with httpx.AsyncClient(
        timeout=15.0, headers={"User-Agent": UA}, follow_redirects=True
    ) as client:
        for sub in SUBREDDITS:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit={limit}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                children = resp.json().get("data", {}).get("children", [])
            except Exception as e:
                print(f"Reddit r/{sub} failed: {e}")
                continue

            for c in children:
                d = c.get("data", {})
                if d.get("stickied"):
                    continue
                title = (d.get("title") or "").strip()
                if not title:
                    continue
                external = d.get("url_overridden_by_dest")
                permalink = f"https://reddit.com{d.get('permalink', '')}"
                deals.append(
                    Deal(
                        startup_name=title[:120],
                        website=external if external and external.startswith("http") else None,
                        description=(d.get("selftext") or title)[:600],
                        source=DealSource.REDDIT,
                        source_url=permalink,
                        discovered_at=datetime.utcnow(),
                    )
                )
    return deals
