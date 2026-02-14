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
                "category": "tech", # Filter usually happens in post-processing
            }
            
            run = await self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])

            async for item in dataset.iterate_items():
                topics = item.get("topics", [])
                
                # Filter for B2B/AI
                relevant_topics = ["Artificial Intelligence", "B2B", "Developer Tools", "SaaS", "Productivity"]
                if not any(t in relevant_topics for t in topics):
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

async def source_product_hunt() -> list[Deal]:
    scraper = ProductHuntScraper()
    return await scraper.get_todays_launches()
