"""Reddit sourcing via Apify."""

from __future__ import annotations

from datetime import datetime

from apify_client import ApifyClientAsync

from src.config import Config
from src.models import Deal, DealSource, Founder


class RedditScraper:
    """Client for Apify Reddit Scraper."""

    # Provide a valid Reddit Scraper Actor ID (e.g., 'trudax/reddit-scraper-lite')
    ACTOR_ID = "trudax/reddit-scraper-lite" # Example

    def __init__(self):
        self.client = ApifyClientAsync(Config.APIFY_TOKEN)

    async def run_search(self) -> list[Deal]:
        if not Config.APIFY_TOKEN:
            print("Warning: Apify token not set. Skipping Reddit.")
            return []

        deals = []
        # Monitoring these subreddits (Phase 1)
        subreddits = [
            "MachineLearning", "LocalLLaMA", "SaaS", "startups", 
            "ArtificialIntelligence", "LangChain"
        ]

        # Search patterns
        # "we built" OR "show off" OR "feedback on our" OR "just launched"
        # We'll need to construct this into what the actor expects. 
        # Assuming the actor takes a list of startUrls or a search query + subreddits.
        # If using 'trudax/reddit-scraper-lite', it typically takes `startUrls`.
        
        start_urls = []
        bases = [
            "search/?q=we+built&restrict_sr=1&t=week&sort=top",
            "search/?q=show+off&restrict_sr=1&t=week&sort=top",
            "search/?q=just+launched&restrict_sr=1&t=week&sort=top",
            "search/?q=feedback+on+our&restrict_sr=1&t=week&sort=top"
        ]
        
        for sub in subreddits:
            for base in bases:
                start_urls.append({"url": f"https://www.reddit.com/r/{sub}/{base}"})

        run_input = {
            "startUrls": start_urls,
            "maxItems": 30,
            "debug": False
        }

        try:
            run = await self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])

            async for item in dataset.iterate_items():
                title = item.get("title", "")
                self_text = item.get("body", "")
                
                # Basic engagement filter
                if item.get("upVotes", 0) < 10:
                    continue

                deal = Deal(
                    startup_name=f"Reddit Pick: {title[:30]}...",
                    description=f"{title}\n\n{self_text[:500]}...",
                    source=DealSource.MANUAL, # TODO: Add REDDIT enum
                    source_url=item.get("url"),
                    discovered_at=datetime.utcnow()
                )
                deals.append(deal)

        except Exception as e:
            # Actor specific errors
            print(f"Error scraping Reddit: {e}")

        return deals

async def source_reddit(limit: int = 20) -> list[Deal]:
    scraper = RedditScraper()
    # Could pass limit to scraper.run_search(limit)
    return await scraper.run_search()
