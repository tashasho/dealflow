"""Apollo/Hunter Contact Enrichment."""

from __future__ import annotations

import httpx

from src.config import Config
from src.models import Deal


class ApolloEnricher:
    """Client for Apollo.io API."""

    URL = "https://api.apollo.io/v1/people/match"

    def __init__(self):
        self.api_key = Config.APOLLO_API_KEY

    async def enrich_founder_email(self, deal: Deal) -> Deal:
        if not self.api_key or not deal.founders:
            return deal

        # Try to enrich the first founder
        founder = deal.founders[0]
        if not founder.linkedin_url:
            return deal

        payload = {
            "api_key": self.api_key,
            "linkedin_url": founder.linkedin_url,
            "reveal_personal_emails": True
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    self.URL,
                    headers={"Content-Type": "application/json"},
                    json=payload
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    person = data.get("person")
                    if person:
                        email = person.get("email")
                        if email:
                            # Add dynamic attribute for now
                            founder.email = email
                            deal.founder_email = email # Convenience
            except Exception as e:
                print(f"Apollo enrichment failed: {e}")

        return deal

async def enrich_contacts(deal: Deal) -> Deal:
    enricher = ApolloEnricher()
    return await enricher.enrich_founder_email(deal)
