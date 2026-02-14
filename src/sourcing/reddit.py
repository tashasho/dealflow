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
        # Monitoring these subreddits
        subreddits = [
            "MachineLearning",
            "LocalLLaMA",
            "SaaS",
            "startups",
            "ArtificialIntelligence",
            "LangChain"
        ]

        # Searching for "launch" type keywords
        searches = ["we built", "show off", "just launched", "feedback"]

        run_input = {
            "searches": searches,
            "subreddits": subreddits,
            "sort": "new",
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

async def source_reddit() -> list[Deal]:
    scraper = RedditScraper()
    return await scraper.run_search()
