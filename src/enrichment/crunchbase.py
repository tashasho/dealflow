"""Crunchbase Data Enrichment."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from src.config import Config
from src.models import Deal


class CrunchbaseEnricher:
    """Client for Crunchbase API."""

    BASE_URL = "https://api.crunchbase.com/api/v4/entities/organizations"

    def __init__(self):
        self.api_key = Config.CRUNCHBASE_API_KEY

    async def enrich(self, deal: Deal) -> Deal:
        """Fetch funding data and filter if >$5M raised."""
        if not self.api_key or not deal.website:
            return deal

        # Normalize domain for lookup
        domain = deal.website.replace("https://", "").replace("http://", "").split("/")[0]

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Search by domain
                payload = {
                    "field_ids": [
                        "name",
                        "website",
                        "funding_total",
                        "num_funding_rounds",
                        "last_funding_at",
                        "funding_stage",
                        "num_employees_enum",
                        "location_identifiers"
                    ],
                    "query": [
                        {
                            "type": "predicate",
                            "field_id": "website_url",
                            "operator_id": "includes",
                            "values": [domain]
                        }
                    ],
                    "limit": 1
                }
                
                resp = await client.post(
                    self.BASE_URL,
                    headers={"X-cb-user-key": self.api_key},
                    json=payload
                )
                
                if resp.status_code != 200:
                    return deal

                data = resp.json()
                entities = data.get("entities", [])
                
                if not entities:
                    return deal
                
                org = entities[0]
                props = org.get("properties", {})
                
                # Check funding
                funding_total = props.get("funding_total", {}).get("value_usd", 0)
                
                # Add enrichment data to deal object (assuming we extend Deal or put in metadata)
                # For now, let's just use it for filtering: if > $5M, we might flag it.
                # The user request asks to filter. 
                # Let's add a `funding_total` field to Deal model? Or just keep it loosely typed.
                # For this implementation, I'll assume we want to attach this info.
                
                # We need to extend the Deal model to hold this if we want to store it.
                # Since I can't easily change the `src/models.py` repeatedly without risk,
                # I'll rely on the existing fields if any, or just print log.
                # Wait, I checked `src/models.py` earlier, it doesn't have funding fields.
                # I should probably add them or specific "enrichment" dict.
                
                # For now, I'll just skip adding fields I can't store, but returns the deal.
                # However, the requirement is "Filter by funding (<$5M)". 
                # So if funding > 5M, I should probably return None or flag it?
                # But enrich signature is Deal -> Deal.
                
                # Let's add a dynamic attribute for now until I modify models.
                deal.funding_raised = funding_total
                deal.funding_stage = props.get("funding_stage")
                deal.employee_count = props.get("num_employees_enum")
                
                locations = props.get("location_identifiers", [])
                if locations:
                    deal.hq_location = locations[0].get("value")

            except Exception as e:
                print(f"Crunchbase enrichment failed for {domain}: {e}")

        # Check funding < $5M (Phase 3 Requirement)
        if deal.funding_raised and deal.funding_raised > 5_000_000:
             # Tag as low priority or just mark it
             # The system specs say "Filter by funding". 
             # We will handle the actual filtering (excluding from list) in the pipeline 
             # or by setting a flag. 
             # Let's add a "pass" reason directly?
             deal.triage_status = "Pass"
             deal.rejection_reason = "Raised > $5M"

        return deal

async def enrich_crunchbase(deal: Deal) -> Deal:
    enricher = CrunchbaseEnricher()
    return await enricher.enrich(deal)
