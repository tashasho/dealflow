"""Slack webhook integration — formatted deal cards and notifications."""

from __future__ import annotations

import json
import httpx

from src.config import Config
from src.models import ScoredDeal, DealPriority


def _create_deal_blocks(scored: ScoredDeal) -> list[dict]:
    """Create Slack Block Kit layout for a deal."""
    deal = scored.deal
    
    # Emoji based on priority
    if scored.priority == DealPriority.HIGH:
        header_text = f"🔥 High Signal: {deal.startup_name} ({scored.total_score}/100)"
    else:
        header_text = f"📌 Worth Watching: {deal.startup_name} ({scored.total_score}/100)"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{scored.summary}*\n{deal.description[:200]}..."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Problem*\n{scored.breakdown.problem_severity}/30"},
                {"type": "mrkdwn", "text": f"*Differentiation*\n{scored.breakdown.differentiation}/25"},
                {"type": "mrkdwn", "text": f"*Team*\n{scored.breakdown.team}/25"},
                {"type": "mrkdwn", "text": f"*Market*\n{scored.breakdown.market_readiness}/20"}
            ]
        }
    ]

    # Strengths Section
    if scored.strengths:
        strengths_text = "• " + "\n• ".join(scored.strengths)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*✅ Strengths:*\n{strengths_text}"
            }
        })

    # Red Flags Section
    if scored.red_flags:
        flags_text = "• " + "\n• ".join(scored.red_flags)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚠️ Red Flags:*\n{flags_text}"
            }
        })

    # Context & Links
    context_elements = [
        {"type": "mrkdwn", "text": f"Source: {deal.source.value}"}
    ]
    if deal.website:
        context_elements.append({"type": "mrkdwn", "text": f"<{deal.website}|Website>"})
    if deal.github:
        context_elements.append({"type": "mrkdwn", "text": f"<{deal.github.repo_url}|GitHub ({deal.github.stars}★)>"})
    if deal.founders:
        founders_str = ", ".join([f.name for f in deal.founders[:2]])
        context_elements.append({"type": "mrkdwn", "text": f"Founders: {founders_str}"})

    blocks.append({
        "type": "context",
        "elements": context_elements
    })

    # Actions
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Add to Pipeline", "emoji": True},
                "style": "primary",
                "value": "add_pipeline"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Research", "emoji": True},
                "value": "research"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Pass", "emoji": True},
                "style": "danger",
                "value": "pass"
            }
        ]
    })

    return blocks


async def post_deal_to_slack(scored: ScoredDeal, dry_run: bool = False) -> str:
    """Post deal to the appropriate Slack channel using Block Kit."""
    
    blocks = _create_deal_blocks(scored)
    
    if dry_run:
        return json.dumps(blocks, indent=2)

    # Determine channel (conceptually - for webhook we assume one URL or mapped in config)
    # The user asked for routing to different channels. 
    # Since we only have one SLACK_WEBHOOK_URL in config, we might need another one or use the same.
    # For now, we'll post to the main webhook but we could configure overrides.
    
    payload = {
        "blocks": blocks,
        "text": f"New Deal: {scored.deal.startup_name}", # Fallback notification text
        "unfurl_links": False
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(Config.SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        except Exception as e:
            print(f"Failed to post to Slack: {e}")

    return "Posted to Slack"


async def post_text_to_slack(text: str, dry_run: bool = False) -> str:
    """Post raw text to Slack."""
    if dry_run:
        return text

    payload = {"text": text}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(Config.SLACK_WEBHOOK_URL, json=payload)
        except Exception:
            pass
    return text
