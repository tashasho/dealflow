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

SCORECARD_PROMPT = """You are an expert VC analyst at an early-stage micro-fund that writes seed checks of $500K–$2M into enterprise AI startups.

IMPORTANT CONTEXT:
- We invest at PRE-SEED and SEED stage — we are looking for EARLY startups, not established companies.
- We want to find founders building enterprise AI before they raise Series A.
- High GitHub stars + strong technical founders = strong signal, even without revenue.
- We value: scrappy teams, novel technical approaches, PhD/ex-FAANG founders, OSS traction.
- We do NOT penalize for: lack of SOC2, no pricing page, pre-revenue, small team size.
- Large established companies (OpenAI, Meta, Google) are NOT investable — score them LOW.

Analyze this startup and score it 0-100 based on the following rubric:

1. Problem Severity (30 pts)
   - 25-30: Mission-critical enterprise pain (compliance, security, revenue ops, data infra)
   - 15-24: High-value efficiency (reducing manual work in core workflows)
   - 0-14: Nice-to-have, consumer-focused, or unclear enterprise ROI

2. Differentiation (25 pts)
   - 20-25: Proprietary models/data, unique technical approach, novel research
   - 10-19: Novel application but relies on off-the-shelf models with smart integration
   - 0-9: Thin wrapper around GPT/Claude with no defensibility

3. Team (25 pts)
   - 20-25: Technical founders with PhD, exits, major OSS contributions, or ex-FAANG
   - 10-19: Strong IC experience at good companies, or active OSS contributors
   - 0-9: No technical depth, no domain expertise, or this is a large corporation (not investable)

4. Market Readiness (20 pts)
   - 15-20: Live product/beta with users, GitHub traction, or "book demo" CTA
   - 8-14: Working prototype, waitlist, early community
   - 0-7: Concept stage only — BUT don't over-penalize seed-stage startups for this

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

SCORING GUIDELINES:
- If this is a LARGE CORPORATION (OpenAI, Meta, Google, HuggingFace org), score VERY LOW (0-20) — we can't invest in them.
- If this is an early-stage startup with strong technical signal, score GENEROUSLY (50-80+).
- A pre-revenue startup with great founders and novel tech should score 60-75.
- Only score 80+ if everything aligns: great team + novel tech + clear enterprise pain + early traction.

You MUST respond with ONLY a valid JSON object in this exact format (no markdown, no extra text):
{{
  "problem_severity": <int 0-30>,
  "differentiation": <int 0-25>,
  "team": <int 0-25>,
  "market_readiness": <int 0-20>,
  "total_score": <int 0-100>,
  "summary": "<one-line summary of what this startup does>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "red_flags": ["<red flag 1>"],
  "confidence": "high|medium|low"
}}
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
