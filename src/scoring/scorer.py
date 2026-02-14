"""Gemini-powered AI scorecard — the brain of the deal flow system."""

from __future__ import annotations

import json
import re
from typing import Optional

from google import genai

from src.config import Config
from src.models import Deal, DealPriority, ScoreBreakdown, ScoredDeal


# ---------------------------------------------------------------------------
# The scoring prompt — maps exactly to the user's scorecard rubric
# ---------------------------------------------------------------------------

SCORECARD_PROMPT = """You are a seed-stage VC analyst evaluating Enterprise AI startups. Score 0-100.

IMPORTANT: Be CRITICAL. Average startups should score 50-70. Only exceptional opportunities score >85.

Analyze this startup based on the following weighted rubric:

1. PROBLEM SEVERITY (30 points)
   - 25-30: Mission-critical (compliance, security, fraud prevention, revenue operations). Ex: SOC2 automation.
   - 18-24: High-value efficiency (10x faster workflows, >$100k/year savings). Ex: Automated code review.
   - 10-17: Moderate pain point (2-5x improvement, nice-to-have).
   - 0-9: Unclear problem OR consumer-focused.

2. DIFFERENTIATION (25 points)
   - 20-25: Proprietary data/models, unique workflow IP, deep vertical integration.
   - 13-19: Novel application with defensibility (network effects, switching costs).
   - 6-12: Better UX/execution on existing solution.
   - 0-5: Obvious ChatGPT/Claude wrapper, no moat.

3. TEAM (25 points)
   - 20-25: PhD + domain expertise OR previous successful exit OR 10+ years in target vertical. Ex: Ex-FAANG Staff+.
   - 13-19: Strong senior IC at top companies (5-10 years relevant experience).
   - 6-12: Solid background but first-time founders, junior (<5 years).
   - 0-5: No relevant experience visible, career switchers without domain knowledge.

4. MARKET READINESS (20 points)
   - 16-20: Live product, paying customers, SOC2 started, "Book Demo" CTA.
   - 10-15: Beta with users, testimonials, "Join Beta" or "Request Access".
   - 4-9: Landing page only, "Join Waitlist", vague positioning.
   - 0-3: Blog/concept only, no product.

PENALTIES (Deduct from total score):
- Geographic arbitrage without technical depth: -10
- Buzzword-heavy without substance: -5
- Consumer pivot disguised as enterprise: -15
- No clear ICP (Ideal Customer Profile): -5

--- STARTUP DATA ---

Name: {name}
Website: {website}
Description: {description}

Founders:
{founders_text}

GitHub Metrics:
{github_text}

Website Signals:
{website_signals_text}

--- END DATA ---

You MUST respond with ONLY a valid JSON object in this exact format (no markdown):
{
  "problem_severity": <int 0-30>,
  "differentiation": <int 0-25>,
  "team": <int 0-25>,
  "market_readiness": <int 0-20>,
  "total_score": <int 0-100>,
  "summary": "<one concise sentence: what they do + for whom>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "red_flags": ["<red flag 1>"],
  "confidence": "high|medium|low"
}
"""


def _format_founders(deal: Deal) -> str:
    if not deal.founders:
        return "No founder data available"
    lines = []
    for f in deal.founders:
        parts = [f"- {f.name}"]
        if f.background:
            parts.append(f"  Background: {f.background}")
        if f.notable_companies:
            parts.append(f"  Companies: {', '.join(f.notable_companies)}")
        if f.has_phd:
            parts.append("  Has PhD: Yes")
        if f.has_exits:
            parts.append("  Has exits: Yes")
        if f.oss_contributions:
            parts.append(f"  OSS: {f.oss_contributions}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def _format_github(deal: Deal) -> str:
    if not deal.github:
        return "No GitHub data available"
    g = deal.github
    lines = [
        f"Repo: {g.repo_url}",
        f"Stars: {g.stars:,}",
        f"Star velocity (7d): +{g.star_velocity_7d}",
        f"Contributors: {g.contributors}",
        f"Open issues: {g.open_issues}",
    ]
    if g.enterprise_signals:
        lines.append(f"Enterprise signals: {', '.join(g.enterprise_signals)}")
    if g.readme_snippet:
        lines.append(f"README excerpt: {g.readme_snippet[:500]}")
    return "\n".join(lines)


def _format_website_signals(deal: Deal) -> str:
    if not deal.website_signals:
        return "No website data available"
    ws = deal.website_signals
    lines = [
        f"Has pricing page: {ws.has_pricing}",
        f"Has 'Book Demo': {ws.has_book_demo}",
        f"Has SOC2 badge: {ws.has_soc2_badge}",
        f"Has enterprise tier: {ws.has_enterprise_tier}",
    ]
    if ws.page_text:
        lines.append(f"Page text excerpt: {ws.page_text[:500]}")
    return "\n".join(lines)


def _parse_score_response(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown fences."""
    # Try to find JSON in the response
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


async def score_deal(deal: Deal) -> ScoredDeal:
    """
    Score a deal using Gemini AI against the enterprise AI scorecard.
    Returns a ScoredDeal with breakdown, summary, strengths, and red flags.
    """
    prompt = SCORECARD_PROMPT.format(
        name=deal.startup_name,
        website=deal.website or "N/A",
        description=deal.description,
        founders_text=_format_founders(deal),
        github_text=_format_github(deal),
        website_signals_text=_format_website_signals(deal),
    )

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    response = client.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=prompt,
    )

    result = _parse_score_response(response.text)

    if not result:
        # Fallback: return a low-confidence score
        return ScoredDeal(
            deal=deal,
            total_score=0,
            breakdown=ScoreBreakdown(),
            summary="⚠️ Scoring failed — could not parse LLM response",
            strengths=[],
            red_flags=["Automated scoring failed — needs manual review"],
            priority=DealPriority.LOW,
        )

    # Clamp values to valid ranges
    breakdown = ScoreBreakdown(
        problem_severity=min(max(result.get("problem_severity", 0), 0), 30),
        differentiation=min(max(result.get("differentiation", 0), 0), 25),
        team=min(max(result.get("team", 0), 0), 25),
        market_readiness=min(max(result.get("market_readiness", 0), 0), 20),
    )

    total = result.get("total_score", breakdown.total)
    total = min(max(total, 0), 100)

    scored = ScoredDeal(
        deal=deal,
        total_score=total,
        breakdown=breakdown,
        summary=result.get("summary", ""),
        strengths=result.get("strengths", [])[:2],
        red_flags=result.get("red_flags", [])[:2],
    )
    scored.priority = scored.classify()

    return scored
