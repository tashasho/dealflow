"""LinkedIn sourcing via Phantombuster API."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from src.config import Config
from src.models import Deal, DealSource, Founder


class LinkedInScraper:
    """Client for Phantombuster LinkedIn Search Export."""

    BASE_URL = "https://api.phantombuster.com/api/v2/agents"

    def __init__(self):
        self.api_key = Config.PHANTOMBUSTER_API_KEY
        self.agent_id = Config.PHANTOMBUSTER_AGENT_ID

    async def launch_and_fetch(self) -> list[Deal]:
        """
        Launch the Phantombuster agent, wait for completion, and fetch results.
        Note: This is a synchronous blocking call in Phantombuster terms,
        so we poll for status.
        """
        if not self.api_key or not self.agent_id:
            print("Warning: Phantombuster credentials not set. Skipping LinkedIn.")
            return []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Launch Agent
            headers = {"X-Phantombuster-Key": self.api_key}
            launch_resp = await client.post(
                f"{self.BASE_URL}/{self.agent_id}/launch", headers=headers
            )
            if launch_resp.status_code != 200:
                print(f"Failed to launch Phantombuster agent: {launch_resp.text}")
                return []
            
            launch_data = launch_resp.json()
            container_id = launch_data.get("containerId")

            # 2. Poll for completion
            while True:
                await asyncio.sleep(10)  # Wait 10s between checks
                status_resp = await client.get(
                    f"https://api.phantombuster.com/api/v2/containers/{container_id}",
                    headers=headers
                )
                status_data = status_resp.json()
                status = status_data.get("status")
                
                if status == "finished":
                    break
                elif status in ["error", "canceled"]:
                    print(f"Phantombuster agent failed with status: {status}")
                    return []

            # 3. Fetch Output
            output_resp = await client.get(
                f"{self.BASE_URL}/{self.agent_id}/output", headers=headers
            )
            if output_resp.status_code != 200:
                print("Failed to fetch Phantombuster output")
                return []

            try:
                results = output_resp.json()
            except Exception:
                # Sometimes output is not JSON but a CSV URL or mixed content
                # For this implementation, we assume the agent is configured to return JSON
                print("Could not parse Phantombuster output as JSON")
                return []

            deals = []
            for item in results:
                # Map Phantombuster LinkedIn result to Deal model
                # This mapping depends heavily on the specific Phantom used (e.g. "LinkedIn Search Export")
                
                # Heuristic mapping
                name = item.get("companyName") or item.get("company_name") or "Unknown"
                if name == "Unknown":
                     # Try to derive from profile title if it's a person search
                     current_company = item.get("currentCompany")
                     if current_company:
                         name = current_company

                founders = []
                founder_name = item.get("fullName") or item.get("name")
                if founder_name:
                    founders.append(Founder(
                        name=founder_name,
                        linkedin_url=item.get("profileUrl") or item.get("url"),
                        background=item.get("jobTitle") or item.get("title")
                    ))
                
                deal = Deal(
                    startup_name=name,
                    source=DealSource.MANUAL, # Mapping to closest existing source or add new
                    source_url=item.get("profileUrl") or item.get("url"),
                    desc=item.get("jobTitle") or "",
                    founders=founders,
                    discovered_at=datetime.utcnow()
                )
                deals.append(deal)

            return deals


async def source_linkedin() -> list[Deal]:
    """Main entry point for LinkedIn sourcing."""
    scraper = LinkedInScraper()
    return await scraper.launch_and_fetch()
