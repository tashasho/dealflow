"""Indie Hackers + BetaList + DevTo — RSS-based sourcing.

These are public RSS feeds, no API keys needed. Each function returns deals
tagged with its specific DealSource enum so the pipeline can attribute origin.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import feedparser
import httpx

from src.models import Deal, DealSource


UA = "dealflow-bot/1.0 (+https://github.com/tashasho/dealflow)"


async def _fetch_feed_bytes(url: str) -> bytes:
    """Use httpx (which bundles certifi) instead of feedparser's urllib."""
    async with httpx.AsyncClient(
        timeout=15.0, headers={"User-Agent": UA}, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _entries_from_bytes(content: bytes) -> list:
    parsed = feedparser.parse(content)
    return list(parsed.entries)


async def _pull(url: str, source: DealSource, lookback_days: int, limit: int) -> list[Deal]:
    try:
        content = await _fetch_feed_bytes(url)
    except Exception as e:
        print(f"{source.value} feed fetch failed: {e}")
        return []

    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _entries_from_bytes, content)

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    deals: list[Deal] = []
    for entry in entries[: limit * 2]:  # over-fetch; we may filter some
        title = (getattr(entry, "title", "") or "").strip()
        link = getattr(entry, "link", None)
        if not title or not link:
            continue

        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6])
        elif getattr(entry, "updated_parsed", None):
            published = datetime(*entry.updated_parsed[:6])
        if published and published < cutoff:
            continue

        summary = getattr(entry, "summary", "") or ""
        deals.append(
            Deal(
                startup_name=title[:120],
                website=link,
                description=summary[:600],
                source=source,
                source_url=link,
                discovered_at=datetime.utcnow(),
            )
        )
        if len(deals) >= limit:
            break
    return deals


async def source_indie_hackers(limit: int = 15) -> list[Deal]:
    return await _pull(
        "https://www.indiehackers.com/feed.xml", DealSource.INDIE_HACKERS, 7, limit
    )


async def source_betalist(limit: int = 15) -> list[Deal]:
    return await _pull(
        "https://feeds.feedburner.com/BetaList", DealSource.BETALIST, 7, limit
    )


async def source_dev_to(limit: int = 15) -> list[Deal]:
    # Dev.to top-week feed
    return await _pull(
        "https://dev.to/feed/top/week", DealSource.DEV_TO, 7, limit
    )
