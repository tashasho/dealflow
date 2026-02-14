"""Website content extraction via Jina AI Reader."""

from __future__ import annotations

import httpx

from src.config import Config
from src.models import WebsiteSignals


async def extract_website_signals(url: str) -> WebsiteSignals:
    """
    Fetch a startup's website using Jina AI Reader and extract signals.
    """
    signals = WebsiteSignals()

    if not url:
        return signals

    # Use Jina AI Reader
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "application/json",
        "X-With-Images-Summary": "true",
        "X-With-Links-Summary": "true"
    }

    if Config.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {Config.JINA_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(jina_url, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("content", "") or data.get("text", "") # Jina response format varies
                title = data.get("title", "")
                
                # Combine title and content
                full_text = f"{title}\n\n{content}"
                
                # Cap text for LLM context (Jina usually returns markdown)
                signals.page_text = full_text[:6000]

                text_lower = full_text.lower()

                # Detect key signals from text
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
                    for kw in ["enterprise", "custom pricing", "contact sales", "talk to sales"]
                )
            else:
                # Fallback to basic scraping if Jina fails (or just return empty)
                print(f"Jina AI failed for {url}: {resp.status_code}")

    except Exception as e:
        print(f"Error fetching website {url}: {e}")

    return signals
