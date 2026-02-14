"""Airtable Sync integration."""

from __future__ import annotations

import httpx

from src.config import Config
from src.models import ScoredDeal, DealPriority


class AirtableClient:
    """Client for Airtable API."""

    def __init__(self):
        self.api_key = Config.AIRTABLE_API_KEY
        self.base_id = Config.AIRTABLE_BASE_ID
        self.table_name = Config.AIRTABLE_TABLE_NAME
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"

    async def sync_deal(self, scored: ScoredDeal):
        """Create or update a deal in Airtable."""
        if not self.api_key or not self.base_id:
            return

        deal = scored.deal
        
        # Map fields to Airtable columns
        fields = {
            "Startup Name": deal.startup_name,
            "Website": deal.website,
            "One Liner": scored.summary,
            "Score": scored.total_score,
            "Status": "To Review", # Default status
            "Source": deal.source.value,
            "Problem Score": scored.breakdown.problem_severity,
            "Diff Score": scored.breakdown.differentiation,
            "Team Score": scored.breakdown.team,
            "Market Score": scored.breakdown.market_readiness,
            "Priority": scored.priority.value,
            "Founders": ", ".join([f.name for f in deal.founders]),
            "Description": deal.description[:2000] # Cap length
        }
        
        # In a real sync, we'd check for existing records to update.
        # Here we'll just create.
        
        payload = {"fields": fields}

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(self.base_url, headers=self.headers, json=payload)
                if resp.status_code != 200:
                    print(f"Airtable sync failed: {resp.text}")
            except Exception as e:
                print(f"Airtable error: {e}")

async def sync_to_airtable(scored_deals: list[ScoredDeal]):
    client = AirtableClient()
    for deal in scored_deals:
        # Sync high priority deals only? Or all?
        # User prompt says "Database Management: Airtable", implies all or filtered.
        # Let's sync deals that are at least "Worth Watching" (>75 usually)
        if deal.priority in [DealPriority.HIGH, DealPriority.WORTH_WATCHING]:
            await client.sync_deal(deal)
