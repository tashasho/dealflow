"""RSS Feed sourcing for Newsletters and Indian Tech News."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import feedparser

from src.models import Deal, DealSource


class RSSScraper:
    """Simple RSS reader."""

    FEEDS = [
        # India Tech News
        "https://inc42.com/feed/",
        "https://yourstory.com/feed",
        "https://entrackr.com/feed/",
        
        # AI Newsletters (if they have RSS, otherwise need specialized scraper)
        "https://www.bensbites.co/feed",
        # Add more valid RSS feeds here
    ]

    async def fetch_feeds(self) -> list[Deal]:
        deals = []
        # Feedparser is blocking, so we'd ideally run in executor
        # For simplicity in this async function:
        loop = asyncio.get_event_loop()
        
        futures = [
            loop.run_in_executor(None, feedparser.parse, url)
            for url in self.FEEDS
        ]
        
        results = await asyncio.gather(*futures)
        
        yesterday = datetime.utcnow() - timedelta(days=1)

        for feed in results:
            for entry in feed.entries:
                # Check date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                     published = datetime(*entry.published_parsed[:6])
                
                if published and published < yesterday:
                    continue
                
                # Filter for B2B/Funding/AI keywords in title/summary
                content = (entry.title + " " + entry.description).lower()
                keywords = ["funding", "raised", "seed", "pre-seed", "enterprise", "b2b", "ai agent"]
                
                if not any(k in content for k in keywords):
                    continue

                deal = Deal(
                    startup_name=entry.title, # Often title is "Company raises $X..."
                    description=entry.description,
                    source=DealSource.MANUAL, # TODO: Add RSS enum
                    source_url=entry.link,
                    discovered_at=datetime.utcnow()
                )
                deals.append(deal)

        return deals

async def source_rss(limit: int = 20) -> list[Deal]:
    scraper = RSSScraper()
    # We could restrict results to limit in fetch_feeds
    return await scraper.fetch_feeds()
