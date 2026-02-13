"""Website content extraction for AI scoring."""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from src.models import WebsiteSignals


async def extract_website_signals(url: str) -> WebsiteSignals:
    """
    Fetch a startup's website and extract signals relevant for scoring:
    pricing, demo CTAs, SOC2 badges, enterprise tiers, and raw text.
    """
    signals = WebsiteSignals()

    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 DealFlow/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script/style noise
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()

            page_text = soup.get_text(separator=" ", strip=True)

            # Clean up whitespace
            page_text = re.sub(r"\s+", " ", page_text)

            # Cap text for LLM context
            signals.page_text = page_text[:4000]

            text_lower = page_text.lower()

            # Detect key signals
            signals.has_pricing = any(
                kw in text_lower
                for kw in ["pricing", "plans", "per month", "/mo", "free tier"]
            )
            signals.has_book_demo = any(
                kw in text_lower
                for kw in ["book a demo", "book demo", "request demo", "schedule demo"]
            )
            signals.has_soc2_badge = "soc 2" in text_lower or "soc2" in text_lower
            signals.has_enterprise_tier = any(
                kw in text_lower
                for kw in ["enterprise", "custom pricing", "contact sales"]
            )

    except (httpx.HTTPError, Exception):
        pass

    return signals
