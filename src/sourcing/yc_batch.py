"""YC batch scraper — finds B2B + AI companies from Y Combinator."""

from __future__ import annotations

from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models import Deal, DealSource


YC_API_URL = "https://api.ycombinator.com/v0.1/companies"

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml",
    "llm", "nlp", "deep learning", "neural", "agent",
    "automation", "rag",
]


def _is_ai_b2b(description: str, tags: list[str]) -> bool:
    text = f"{description} {' '.join(tags)}".lower()
    has_ai = any(kw in text for kw in AI_KEYWORDS)
    has_b2b = "b2b" in text or "enterprise" in text or "saas" in text
    return has_ai and has_b2b


async def source_yc(limit: int = 50) -> list[Deal]:
    """
    Fetch companies from YC's public API, filter for AI + B2B.
    """
    deals: list[Deal] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # YC's public API supports pagination and filtering
            resp = await client.get(
                YC_API_URL,
                params={"q": "AI", "page": 1},
            )
            if resp.status_code != 200:
                return deals

            data = resp.json()
            companies = data.get("companies", [])

            for co in companies[:limit]:
                name = co.get("name", "")
                desc = co.get("one_liner", "") or co.get("long_description", "")
                tags = co.get("tags", [])
                website = co.get("website", "")
                batch = co.get("batch", "")

                if not _is_ai_b2b(desc, tags):
                    continue

                # Check for live product signals
                has_live_product = False
                if website:
                    try:
                        site_resp = await client.get(
                            website,
                            follow_redirects=True,
                            timeout=10,
                        )
                        page_text = site_resp.text.lower()
                        has_live_product = any(
                            sig in page_text
                            for sig in [
                                "book a demo",
                                "book demo",
                                "get started",
                                "sign up",
                                "pricing",
                                "free trial",
                            ]
                        )
                    except (httpx.HTTPError, Exception):
                        pass

                deal = Deal(
                    startup_name=name,
                    website=website or None,
                    description=f"[YC {batch}] {desc}" if batch else desc,
                    source=DealSource.YC,
                    source_url=f"https://www.ycombinator.com/companies/{co.get('slug', '')}",
                    discovered_at=datetime.utcnow(),
                )
                deals.append(deal)

    except httpx.HTTPError:
        pass

    return deals
