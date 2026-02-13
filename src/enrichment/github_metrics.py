"""GitHub metrics collector — star velocity, contributor count, issue engagement."""

from __future__ import annotations

import re

import httpx

from src.config import Config
from src.models import GitHubMetrics


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if Config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
    return h


async def enrich_github_metrics(repo_url: str) -> GitHubMetrics | None:
    """
    Given a GitHub repo URL, fetch detailed metrics via the API.
    Returns None if the URL is not a valid GitHub repo.
    """
    # Parse owner/repo from URL
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None

    owner, repo = match.group(1), match.group(2)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Repo metadata
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return None

            data = resp.json()

            # Contributor count (first page only for speed)
            contributors = 0
            contrib_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contributors",
                params={"per_page": 1, "anon": "true"},
                headers=_headers(),
            )
            if contrib_resp.status_code == 200:
                # GitHub returns total in Link header
                link = contrib_resp.headers.get("Link", "")
                last_match = re.search(r'page=(\d+)>; rel="last"', link)
                if last_match:
                    contributors = int(last_match.group(1))
                else:
                    contributors = len(contrib_resp.json())

            # README for enterprise signals
            readme = ""
            readme_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/readme",
                headers={**_headers(), "Accept": "application/vnd.github.raw+json"},
            )
            if readme_resp.status_code == 200:
                readme = readme_resp.text[:5000]

            # Detect enterprise signals in README
            enterprise_re = re.compile(
                r"\b(SAML|SOC\s?2|on-prem|RBAC|SSO|HIPAA|GDPR|audit.?log|"
                r"self-hosted|enterprise|compliance|multi-tenant)\b",
                re.IGNORECASE,
            )
            enterprise_signals = list(
                {m.group(0).upper() for m in enterprise_re.finditer(readme)}
            )

            return GitHubMetrics(
                repo_url=repo_url,
                stars=data.get("stargazers_count", 0),
                star_velocity_7d=0,  # requires stargazer history API or estimation
                contributors=contributors,
                open_issues=data.get("open_issues_count", 0),
                enterprise_signals=enterprise_signals,
                readme_snippet=readme[:1000] if readme else None,
            )

    except httpx.HTTPError:
        return None
