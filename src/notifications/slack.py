"""Slack webhook integration — formatted deal cards and notifications."""

from __future__ import annotations

import json

import httpx

from src.config import Config
from src.models import ScoredDeal


def _format_deal_card(scored: ScoredDeal) -> str:
    """
    Format a scored deal into the Slack notification card.
    Matches the user's specified format exactly.
    """
    deal = scored.deal

    # Header
    lines = [
        f"🔥 *High-Signal Deal: {deal.startup_name}* — Score: {scored.total_score}/100",
        "",
        f"📝 *One-Liner:* {scored.summary}",
        "",
    ]

    # Strengths
    lines.append("✅ *Why It's Hot:*")
    for s in scored.strengths:
        lines.append(f"  • {s}")
    lines.append("")

    # Red flags
    if scored.red_flags:
        lines.append("⚠️ *Red Flags:*")
        for rf in scored.red_flags:
            lines.append(f"  • {rf}")
        lines.append("")

    # Score breakdown
    b = scored.breakdown
    lines.append(
        f"📊 *Breakdown:* Problem: {b.problem_severity}/30 | "
        f"Diff: {b.differentiation}/25 | "
        f"Team: {b.team}/25 | "
        f"Market: {b.market_readiness}/20"
    )
    lines.append("")

    # Links
    link_parts = []
    if deal.website:
        link_parts.append(f"<{deal.website}|Website>")
    if deal.github and deal.github.repo_url:
        link_parts.append(f"<{deal.github.repo_url}|GitHub>")
    if deal.source_url and deal.source_url != deal.website:
        link_parts.append(f"<{deal.source_url}|Source>")
    if link_parts:
        lines.append(f"🔗 *Links:* {' | '.join(link_parts)}")

    return "\n".join(lines)


async def post_deal_to_slack(
    scored: ScoredDeal,
    dry_run: bool = False,
) -> str:
    """
    Post a formatted deal card to the configured Slack channel.
    If dry_run=True, returns the formatted text without posting.
    """
    text = _format_deal_card(scored)

    if dry_run:
        return text

    payload = {
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            Config.SLACK_WEBHOOK_URL,
            json=payload,
        )
        resp.raise_for_status()

    return text


async def post_text_to_slack(text: str, dry_run: bool = False) -> str:
    """Post raw text to Slack (used for digests, etc.)."""
    if dry_run:
        return text

    payload = {"text": text, "unfurl_links": False}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            Config.SLACK_WEBHOOK_URL,
            json=payload,
        )
        resp.raise_for_status()

    return text
