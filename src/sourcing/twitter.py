"""Twitter/X sourcing via Apify."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from apify_client import ApifyClientAsync

from src.config import Config
from src.models import Deal, DealSource, Founder


class TwitterScraper:
    """Client for Apify Twitter Scraper."""

    # Popular Twitter Scraper Actor ID (e.g., 'apidojo/tweet-scraper' or similar)
    # Using a generic placeholder ID for the "Tweet Scraper"
    ACTOR_ID = "heLL6fUla430wD3j" # Example ID for a tweet scraper

    def __init__(self):
        self.client = ApifyClientAsync(Config.APIFY_TOKEN)

    async def run_search(self, queries: list[str], max_items: int = 30) -> list[Deal]:
        """Run Twitter search for launch announcements."""
        if not Config.APIFY_TOKEN:
            print("Warning: Apify token not set. Skipping Twitter.")
            return []

        deals = []
        
        # Calculate time range (last 24h)
        since_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        for query in queries:
            run_input = {
                "searchTerms": [query],
                "maxItems": max_items,
                "sort": "Latest",
                "tweetLanguage": "en",
                # "startDate": since_date # Some actors support this
            }

            try:
                run = await self.client.actor(self.ACTOR_ID).call(run_input=run_input)
                
                # Fetch results from the default dataset
                dataset = self.client.dataset(run["defaultDatasetId"])
                
                async for item in dataset.iterate_items():
                    text = item.get("full_text") or item.get("text", "")
                    user = item.get("user", {})
                    
                    # Heuristic to extract company name or project
                    # This is noisy and requires the AI Scoring phase to clean up
                    
                    deal = Deal(
                        startup_name=f"Twitter Mention by @{user.get('screen_name')}",
                        description=text,
                        source=DealSource.MANUAL, # TODO: Add TWITTER to DealSource enum
                        source_url=item.get("url"),
                        founders=[Founder(
                            name=user.get("name", "Unknown"),
                            twitter_username=user.get("screen_name"),
                            background=user.get("description")
                        )],
                        discovered_at=datetime.utcnow()
                    )
                    deals.append(deal)

            except Exception as e:
                print(f"Error scraping Twitter for query '{query}': {e}")

        return deals

async def source_twitter(limit: int = 20) -> list[Deal]:
    """Scrape Twitter for launch announcements and stealth founders."""
    scraper = TwitterScraper()
    
    # Specific queries from Phase 1
    queries = [
        # C1: Launch Announcements
        '("excited to announce" OR "we\'re building" OR "we\'re launching" OR "just launched") (AI OR agent OR LLM OR "enterprise automation" OR "B2B") -filter:retweets min_faves:50',
        
        # C2: YC/Accelerator
        '("accepted to YC" OR "joined Y Combinator" OR "starting at YC" OR "Techstars") since:2025-01-01 min_faves:20 -filter:retweets',
        
        # C3: Stealth
        '("coming out of stealth" OR "excited to share what we\'ve been building") (AI OR enterprise OR B2B OR SaaS) since:2025-01-01 min_faves:30 -filter:retweets',
        
        # C4: Founder Bio Search (simulated via search, ideally bio search feature)
        'bio:"Founder" (bio:"ex-Stripe" OR bio:"ex-OpenAI" OR bio:"ex-Google" OR bio:"ex-Anthropic") (bio:"stealth" OR bio:"building")'
    ]
    
    return await scraper.run_search(queries)
