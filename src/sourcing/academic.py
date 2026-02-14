"""Academic sourcing via arXiv API."""

from __future__ import annotations

from datetime import datetime, timedelta

import arxiv

from src.models import Deal, DealSource, Founder


class ArxivScraper:
    """Client for arXiv API."""

    def fetch_papers(self) -> list[Deal]:
        # Search for Enterprise AI / Agents in CS categories
        query = '(ti:enterprise OR ti:agent OR ti:workflow OR ti:"large language model") AND (cat:cs.AI OR cat:cs.CL OR cat:cs.LG)'
        
        search = arxiv.Search(
            query=query,
            max_results=20,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )

        deals = []
        # arXiv client is blocking
        for result in search.results():
            # Check if recent (last 3 days to be safe)
            if result.published.replace(tzinfo=None) < (datetime.utcnow() - timedelta(days=3)):
                continue

            # Heuristic: Check for code link or "commercial" hints
            # This is weak for arXiv, usually we look for authors moving to stealth
            
            deal = Deal(
                startup_name=f"Research: {result.title[:30]}...",
                description=f"{result.summary[:500]}...",
                source=DealSource.ARXIV,
                source_url=result.entry_id,
                founders=[Founder(name=a.name) for a in result.authors],
                discovered_at=datetime.utcnow()
            )
            deals.append(deal)
        
        return deals

async def source_academic() -> list[Deal]:
    scraper = ArxivScraper()
    # Run blocking call in executor
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scraper.fetch_papers)
