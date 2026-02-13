"""HuggingFace organization monitor — finds enterprise-focused ML orgs."""

from __future__ import annotations

from datetime import datetime

import httpx

from src.models import Deal, DealSource


HF_API = "https://huggingface.co/api"

ENTERPRISE_DATASET_KEYWORDS = [
    "pii",
    "redaction",
    "document",
    "invoice",
    "contract",
    "compliance",
    "medical",
    "legal",
    "finance",
    "enterprise",
    "ocr",
]


async def source_huggingface(
    min_downloads: int = 10_000,
    limit: int = 30,
) -> list[Deal]:
    """
    Monitor HuggingFace for new orgs with high-download models
    or enterprise-focused datasets.
    """
    deals: list[Deal] = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Search for trending models
            resp = await client.get(
                f"{HF_API}/models",
                params={
                    "sort": "downloads",
                    "direction": "-1",
                    "limit": limit,
                    "filter": "text-generation",
                },
            )
            if resp.status_code != 200:
                return deals

            models = resp.json()
            seen_orgs: set[str] = set()

            for model in models:
                model_id: str = model.get("modelId", "")  # e.g. "org/model-name"
                downloads = model.get("downloads", 0)

                if "/" not in model_id:
                    continue  # skip user-level models

                org = model_id.split("/")[0]
                if org in seen_orgs:
                    continue
                seen_orgs.add(org)

                if downloads < min_downloads:
                    continue

                # Check for enterprise signals in tags/description
                tags = model.get("tags", [])
                pipeline_tag = model.get("pipeline_tag", "")

                deal = Deal(
                    startup_name=org,
                    website=f"https://huggingface.co/{org}",
                    description=(
                        f"HuggingFace org with {downloads:,}+ model downloads. "
                        f"Pipeline: {pipeline_tag}. Tags: {', '.join(tags[:5])}"
                    ),
                    source=DealSource.HUGGINGFACE,
                    source_url=f"https://huggingface.co/{model_id}",
                    discovered_at=datetime.utcnow(),
                )
                deals.append(deal)

            # Also check enterprise-focused datasets
            ds_resp = await client.get(
                f"{HF_API}/datasets",
                params={
                    "sort": "downloads",
                    "direction": "-1",
                    "limit": 20,
                },
            )
            if ds_resp.status_code == 200:
                datasets = ds_resp.json()
                for ds in datasets:
                    ds_id: str = ds.get("id", "")
                    ds_name = ds_id.lower()
                    if any(kw in ds_name for kw in ENTERPRISE_DATASET_KEYWORDS):
                        org = ds_id.split("/")[0] if "/" in ds_id else ds_id
                        if org not in seen_orgs:
                            seen_orgs.add(org)
                            deal = Deal(
                                startup_name=org,
                                website=f"https://huggingface.co/{org}",
                                description=f"Enterprise dataset: {ds_id}",
                                source=DealSource.HUGGINGFACE,
                                source_url=f"https://huggingface.co/datasets/{ds_id}",
                                discovered_at=datetime.utcnow(),
                            )
                            deals.append(deal)

    except httpx.HTTPError:
        pass

    return deals
