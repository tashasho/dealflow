"""Weekly digest generator — Monday morning summary for the partnership."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.models import ScoredDeal, WeeklyDigest
from src.notifications.slack import post_text_to_slack
from src.storage.db import DealDatabase


def _format_digest(digest: WeeklyDigest) -> str:
    """Format the weekly digest per the user's template."""
    lines = [
        "📊 *This Week in Enterprise AI Deal Flow*",
        "",
        f"✅ Reviewed: {digest.total_reviewed} startups",
        f"🔥 High Priority (≥85): {digest.high_priority}",
        f"📌 Worth Watching (75-84): {digest.worth_watching}",
        f"🗑️ Auto-Filtered: {digest.auto_filtered}",
        "",
    ]

    if digest.top_deals:
        lines.append("*Top Deals to Discuss:*")
        for i, deal in enumerate(digest.top_deals[:3], 1):
            lines.append(
                f"{i}. *{deal.deal.startup_name}* — {deal.total_score}/100 — {deal.summary}"
            )
        lines.append("")

    lines.append(
        f"_Period: {digest.week_start.strftime('%b %d')} – "
        f"{digest.week_end.strftime('%b %d, %Y')}_"
    )

    return "\n".join(lines)


def generate_digest(db: DealDatabase) -> WeeklyDigest:
    """Build a weekly digest from stored scored deals."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    all_scored = db.get_scored_deals_since(week_ago, min_score=0)

    high = [d for d in all_scored if d.total_score >= 85]
    watching = [d for d in all_scored if 75 <= d.total_score < 85]
    filtered = [d for d in all_scored if d.total_score < 75]

    # Top deals sorted by score
    top = sorted(all_scored, key=lambda d: d.total_score, reverse=True)[:3]

    return WeeklyDigest(
        week_start=week_ago,
        week_end=now,
        total_reviewed=len(all_scored),
        high_priority=len(high),
        worth_watching=len(watching),
        auto_filtered=len(filtered),
        top_deals=top,
    )


async def send_digest(
    db: DealDatabase,
    dry_run: bool = False,
) -> str:
    """Generate and send the weekly digest to Slack."""
    digest = generate_digest(db)
    text = _format_digest(digest)

    # Persist digest
    db.save_digest(digest)

    result = await post_text_to_slack(text, dry_run=dry_run)
    return result
