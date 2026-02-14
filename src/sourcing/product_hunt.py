"""Product Hunt sourcing via Apify."""

from __future__ import annotations

from datetime import datetime

from apify_client import ApifyClientAsync

from src.config import Config
from src.models import Deal, DealSource, Founder


class ProductHuntScraper:
    """Client for Apify Product Hunt Scraper."""

    # Example Actor ID for Product Hunt
    ACTOR_ID = "hMvNspz39a" # Placeholder ID

    def __init__(self):
        self.client = ApifyClientAsync(Config.APIFY_TOKEN)

    async def get_todays_launches(self) -> list[Deal]:
        if not Config.APIFY_TOKEN:
            print("Warning: Apify token not set. Skipping Product Hunt.")
            return []

        deals = []
        try:
            # Run actor for "today"
            run_input = {
                "maxItems": 20,
                "category": "tech",
            }
            
            run = await self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])

            async for item in dataset.iterate_items():
                topics = item.get("topics", [])
                description = (item.get("description", "") + " " + item.get("tagline", "")).lower()
                
                # Filter D: B2B/AI + Keywords
                # "enterprise" OR "B2B" OR "teams" OR "automation" OR "agent" OR "workflow"
                keywords = ["enterprise", "b2b", "teams", "automation", "agent", "workflow"]
                if not any(k in description for k in keywords):
                    continue

                # Exclude wrappers checking logic usually goes here or in scoring
                
                # Upvote velocity check (simulated by total votes for now)
                if item.get("votesCount", 0) < 80:
                    continue

                deal = Deal(
                    startup_name=item.get("name"),
                    website=item.get("url"), # This is usually the PH link, separate enrich needed for real URL
                    description=item.get("tagline") + "\n" + item.get("description", ""),
                    source=DealSource.PRODUCT_HUNT,
                    source_url=item.get("url"),
                    founders=[Founder(name=maker.get("name"), background=maker.get("username")) for maker in item.get("makers", [])],
                    discovered_at=datetime.utcnow()
                )
                deals.append(deal)

        except Exception as e:
            print(f"Error scraping Product Hunt: {e}")

        return deals

async def source_product_hunt(limit: int = 20) -> list[Deal]:
    scraper = ProductHuntScraper()
    return await scraper.get_todays_launches()
