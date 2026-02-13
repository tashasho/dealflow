"""Founder enrichment via Apollo API (with Clay fallback stub)."""

from __future__ import annotations

import os
import re

import httpx

from src.models import Founder


APOLLO_API_BASE = "https://api.apollo.io/api/v1"


def _get_apollo_key() -> str:
    return os.getenv("APOLLO_API_KEY", "")


def _get_clay_key() -> str:
    return os.getenv("CLAY_API_KEY", "")


async def _enrich_via_apollo(founder: Founder) -> Founder:
    """
    Enrich a founder using the Apollo.io People API.

    Apollo endpoints used:
    - /people/match: Match by name + company
    - /people/{id}: Get full profile

    Returns the enriched Founder with updated fields.
    """
    api_key = _get_apollo_key()
    if not api_key:
        return founder

    async with httpx.AsyncClient(timeout=15) as client:
        # --- Step 1: Match person ---
        match_params: dict = {
            "api_key": api_key,
            "name": founder.name,
        }
        # If we have a LinkedIn URL, use it directly (most reliable)
        if founder.linkedin_url:
            match_params["linkedin_url"] = founder.linkedin_url

        try:
            resp = await client.post(
                f"{APOLLO_API_BASE}/people/match",
                json=match_params,
            )
            if resp.status_code != 200:
                return founder

            data = resp.json()
            person = data.get("person")
            if not person:
                return founder

            # --- Step 2: Extract enrichment data ---

            # LinkedIn
            if not founder.linkedin_url and person.get("linkedin_url"):
                founder.linkedin_url = person["linkedin_url"]

            # Headline / background
            headline = person.get("headline", "")
            title = person.get("title", "")
            org_name = person.get("organization", {}).get("name", "")
            if headline:
                founder.background = headline
            elif title and org_name:
                founder.background = f"{title} at {org_name}"

            # Notable companies from employment history
            employment = person.get("employment_history", [])
            notable = set(founder.notable_companies)
            top_companies = {
                "google", "meta", "facebook", "apple", "amazon", "microsoft",
                "openai", "anthropic", "deepmind", "stripe", "palantir",
                "nvidia", "tesla", "netflix", "uber", "airbnb",
                "databricks", "snowflake", "datadog", "cloudflare",
                "coinbase", "figma", "notion", "vercel",
            }
            for job in employment:
                comp_name = job.get("organization_name", "")
                if comp_name and comp_name.lower() in top_companies:
                    notable.add(comp_name)
            founder.notable_companies = list(notable)

            # Education — detect PhD
            education = person.get("education", [])
            for edu in education:
                degree = (edu.get("degree", "") or "").lower()
                if "phd" in degree or "ph.d" in degree or "doctor" in degree:
                    founder.has_phd = True
                    break

            # Detect exits via keywords in bio/headline
            bio = f"{headline} {title}".lower()
            if any(kw in bio for kw in ["ex-", "former", "acquired", "exited", "founded"]):
                # Could indicate an exit, but needs more signal
                if any(kw in bio for kw in ["acquired", "exited", "exit"]):
                    founder.has_exits = True

            # OSS contributions from GitHub
            github_url = person.get("github_url", "")
            if github_url:
                founder.oss_contributions = github_url

        except (httpx.HTTPError, KeyError, TypeError):
            pass

    return founder


async def _enrich_via_clay(founder: Founder) -> Founder:
    """
    Enrich a founder using the Clay API.

    Clay is a waterfall enrichment platform that tries multiple
    data providers (Apollo, Clearbit, PeopleDataLabs, etc.)

    Clay's API uses table-based enrichment. This integration
    uses the direct enrichment endpoint.
    """
    api_key = _get_clay_key()
    if not api_key:
        return founder

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            # Clay's enrichment API
            resp = await client.post(
                "https://api.clay.com/v1/enrich/person",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "name": founder.name,
                    "linkedin_url": founder.linkedin_url or "",
                },
            )
            if resp.status_code != 200:
                return founder

            data = resp.json()
            person = data.get("person", data)

            # LinkedIn URL
            if not founder.linkedin_url:
                founder.linkedin_url = person.get("linkedin_url", founder.linkedin_url)

            # Background
            headline = person.get("headline") or person.get("title", "")
            if headline:
                founder.background = headline

            # Notable companies
            companies = person.get("companies", [])
            if companies:
                notable = set(founder.notable_companies)
                for c in companies:
                    name = c if isinstance(c, str) else c.get("name", "")
                    if name:
                        notable.add(name)
                founder.notable_companies = list(notable)

            # Education
            education = person.get("education", [])
            for edu in education:
                degree = str(edu.get("degree", "")).lower()
                if "phd" in degree or "ph.d" in degree or "doctor" in degree:
                    founder.has_phd = True

        except (httpx.HTTPError, KeyError, TypeError):
            pass

    return founder


async def enrich_founders(founders: list[Founder]) -> list[Founder]:
    """
    Enrich founders using available APIs.

    Priority order:
    1. Apollo (if APOLLO_API_KEY is set)
    2. Clay (if CLAY_API_KEY is set, as fallback/supplement)
    3. Pass-through (if neither key is available)
    """
    apollo_key = _get_apollo_key()
    clay_key = _get_clay_key()

    if not apollo_key and not clay_key:
        # No enrichment APIs configured — pass through
        return founders

    enriched: list[Founder] = []
    for founder in founders:
        result = founder

        # Try Apollo first (cheaper, most common)
        if apollo_key:
            result = await _enrich_via_apollo(result)

        # Try Clay as supplement if Apollo didn't find enough
        if clay_key and not result.linkedin_url:
            result = await _enrich_via_clay(result)

        enriched.append(result)

    return enriched
