"""arXiv paper monitor — tracks enterprise AI research from top labs."""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models import Deal, DealSource, Founder


# arXiv API base
ARXIV_API = "http://export.arxiv.org/api/query"

# Research topics mapped to search queries
RESEARCH_QUERIES = [
    # Enterprise RAG architectures
    'all:"retrieval augmented generation" AND all:enterprise',
    'all:"RAG" AND (all:enterprise OR all:production OR all:deployment)',
    # Agentic workflow orchestration
    'all:"agentic" AND (all:workflow OR all:orchestration OR all:multi-agent)',
    'all:"tool use" AND all:"large language model" AND all:agent',
    # Privacy-preserving ML
    'all:"federated learning" AND all:enterprise',
    'all:"differential privacy" AND all:"language model"',
    'all:"privacy preserving" AND all:"machine learning"',
    # Enterprise AI general
    'all:"enterprise AI" AND (all:deployment OR all:production)',
]

# University labs we want to track — authors affiliated with these
TRACKED_LABS = {
    "stanford": "Stanford HAI",
    "stanford.edu": "Stanford HAI",
    "mit.edu": "MIT CSAIL",
    "csail": "MIT CSAIL",
    "cmu.edu": "CMU",
    "carnegie mellon": "CMU",
    "berkeley": "UC Berkeley",
    "google": "Google Research",
    "deepmind": "DeepMind",
    "meta": "Meta FAIR",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "microsoft": "Microsoft Research",
}


def _detect_lab_affiliation(authors: list[dict]) -> list[str]:
    """Detect if any authors are from tracked labs."""
    affiliations: set[str] = set()
    for author in authors:
        full_text = f"{author.get('name', '')} {author.get('affiliation', '')}".lower()
        for keyword, lab_name in TRACKED_LABS.items():
            if keyword in full_text:
                affiliations.add(lab_name)
    return list(affiliations)


def _has_enterprise_focus(title: str, summary: str) -> bool:
    """Check if the paper has enterprise/production focus."""
    text = f"{title} {summary}".lower()
    enterprise_signals = [
        "enterprise", "production", "deployment", "industry",
        "real-world", "scalab", "on-premise", "compliance",
        "security", "privacy", "audit", "regulation",
        "workflow", "automation", "orchestrat",
    ]
    return sum(1 for s in enterprise_signals if s in text) >= 2


def _parse_arxiv_response(xml_text: str) -> list[dict]:
    """Parse arXiv Atom XML response into paper dicts."""
    soup = BeautifulSoup(xml_text, "html.parser")
    papers: list[dict] = []

    for entry in soup.find_all("entry"):
        title_el = entry.find("title")
        summary_el = entry.find("summary")
        id_el = entry.find("id")
        published_el = entry.find("published")

        if not title_el or not id_el:
            continue

        title = re.sub(r"\s+", " ", title_el.get_text(strip=True))
        summary = re.sub(r"\s+", " ", summary_el.get_text(strip=True)) if summary_el else ""
        paper_url = id_el.get_text(strip=True)
        published = published_el.get_text(strip=True) if published_el else ""

        # Extract authors
        authors: list[dict] = []
        for author_el in entry.find_all("author"):
            name_el = author_el.find("name")
            aff_el = author_el.find("arxiv:affiliation") or author_el.find("affiliation")
            if name_el:
                authors.append({
                    "name": name_el.get_text(strip=True),
                    "affiliation": aff_el.get_text(strip=True) if aff_el else "",
                })

        # Categories
        categories = []
        for cat_el in entry.find_all("category"):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)

        papers.append({
            "title": title,
            "summary": summary,
            "url": paper_url,
            "published": published,
            "authors": authors,
            "categories": categories,
        })

    return papers


async def source_arxiv(limit: int = 20) -> list[Deal]:
    """
    Search arXiv for enterprise AI research papers from tracked labs.
    Papers are converted into Deal objects representing potential
    founder/researcher talent signals.
    """
    deals: list[Deal] = []
    seen_urls: set[str] = set()

    async with httpx.AsyncClient(timeout=30) as client:
        for query in RESEARCH_QUERIES:
            try:
                resp = await client.get(
                    ARXIV_API,
                    params={
                        "search_query": query,
                        "start": 0,
                        "max_results": 10,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                if resp.status_code != 200:
                    continue

                papers = _parse_arxiv_response(resp.text)

                for paper in papers:
                    paper_url = paper["url"]
                    if paper_url in seen_urls:
                        continue
                    seen_urls.add(paper_url)

                    title = paper["title"]
                    summary = paper["summary"]

                    # Skip papers without enterprise focus
                    if not _has_enterprise_focus(title, summary):
                        continue

                    # Detect lab affiliations
                    lab_affiliations = _detect_lab_affiliation(paper["authors"])

                    # Build founders from paper authors
                    founders = []
                    for author in paper["authors"][:5]:  # cap at 5 authors
                        founders.append(Founder(
                            name=author["name"],
                            background=author.get("affiliation", ""),
                            notable_companies=[a for a in lab_affiliations],
                            has_phd=True,  # arXiv authors typically have PhDs
                        ))

                    # Build description
                    desc_parts = [summary[:500]]
                    if lab_affiliations:
                        desc_parts.append(f"Labs: {', '.join(lab_affiliations)}")
                    if paper["categories"]:
                        desc_parts.append(f"Topics: {', '.join(paper['categories'][:3])}")

                    deal = Deal(
                        startup_name=f"[Research] {title[:80]}",
                        website=paper_url,
                        description=" | ".join(desc_parts),
                        founders=founders,
                        source=DealSource.ARXIV,
                        source_url=paper_url,
                        discovered_at=datetime.utcnow(),
                    )
                    deals.append(deal)

                    if len(deals) >= limit:
                        return deals

            except httpx.HTTPError:
                continue

    return deals
