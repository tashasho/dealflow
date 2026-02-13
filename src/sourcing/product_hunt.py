"""Product Hunt B2B + AI tracker."""

from __future__ import annotations

from datetime import datetime

import httpx

from src.models import Deal, DealSource


PH_API_URL = "https://www.producthunt.com/frontend/graphql"

# GraphQL query for recent B2B AI posts
POSTS_QUERY = """
query {{
  posts(order: RANKING, topic: "artificial-intelligence", first: {limit}) {{
    edges {{
      node {{
        id
        name
        tagline
        votesCount
        website
        url
        createdAt
        topics {{
          edges {{
            node {{
              name
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

B2B_KEYWORDS = [
    "b2b", "enterprise", "saas", "api", "platform", "workflow",
    "automation", "compliance", "security", "operations", "devops",
    "infrastructure", "data", "analytics",
]


def _is_b2b(tagline: str, topics: list[str]) -> bool:
    text = f"{tagline} {' '.join(topics)}".lower()
    return any(kw in text for kw in B2B_KEYWORDS)


async def source_product_hunt(
    min_upvotes: int = 100,
    limit: int = 30,
) -> list[Deal]:
    """
    Fetch recent AI product launches from Product Hunt.
    Filter for B2B focus and upvote velocity.
    """
    deals: list[Deal] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                PH_API_URL,
                json={"query": POSTS_QUERY.format(limit=limit)},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            if resp.status_code != 200:
                # Product Hunt may require auth — fall back gracefully
                return deals

            data = resp.json()
            edges = (
                data.get("data", {})
                .get("posts", {})
                .get("edges", [])
            )

            for edge in edges:
                node = edge.get("node", {})
                votes = node.get("votesCount", 0)
                if votes < min_upvotes:
                    continue

                tagline = node.get("tagline", "")
                topics = [
                    t["node"]["name"]
                    for t in node.get("topics", {}).get("edges", [])
                ]

                if not _is_b2b(tagline, topics):
                    continue

                deal = Deal(
                    startup_name=node.get("name", "Unknown"),
                    website=node.get("website") or node.get("url"),
                    description=tagline,
                    source=DealSource.PRODUCT_HUNT,
                    source_url=node.get("url"),
                    discovered_at=datetime.utcnow(),
                )
                deals.append(deal)

    except httpx.HTTPError:
        # Non-fatal: return what we have
        pass

    return deals
