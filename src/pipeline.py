"""Main pipeline orchestrator — source → enrich → score → filter → notify → store."""

from __future__ import annotations

import asyncio
from typing import Optional

from rich.console import Console
from rich.table import Table

from src.config import Config
from src.enrichment.founders import enrich_founders
from src.enrichment.github_metrics import enrich_github_metrics
from src.enrichment.website import extract_website_signals
from src.models import Deal, DealPriority, ScoredDeal
from src.notifications.slack import post_deal_to_slack
from src.scoring.scorer import score_deal
from src.sourcing.github_trending import source_github
from src.sourcing.huggingface import source_huggingface
from src.sourcing.product_hunt import source_product_hunt
from src.sourcing.yc_batch import source_yc
from src.sourcing.arxiv import source_arxiv
from src.storage.db import DealDatabase

console = Console()

# Map source names to functions
SOURCE_MAP = {
    "github": source_github,
    "product_hunt": source_product_hunt,
    "yc": source_yc,
    "huggingface": source_huggingface,
    "arxiv": source_arxiv,
}


async def _deduplicate(deals: list[Deal]) -> list[Deal]:
    """Remove duplicates by startup name (case-insensitive)."""
    seen: set[str] = set()
    unique: list[Deal] = []
    for deal in deals:
        key = deal.startup_name.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(deal)
    return unique


async def _enrich_deal(deal: Deal) -> Deal:
    """Enrich a single deal with website signals, GitHub metrics, and founder data."""
    # Website signals
    if deal.website and not deal.website_signals:
        deal.website_signals = await extract_website_signals(deal.website)

    # GitHub metrics
    if deal.github and deal.github.repo_url and deal.github.stars == 0:
        enriched = await enrich_github_metrics(deal.github.repo_url)
        if enriched:
            deal.github = enriched

    # Founder enrichment
    if deal.founders:
        deal.founders = await enrich_founders(deal.founders)

    return deal


def _print_results_table(scored_deals: list[ScoredDeal]) -> None:
    """Pretty-print scored deals as a rich table."""
    table = Table(
        title="🎯 Deal Flow Results",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Startup", style="cyan", no_wrap=True)
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Priority", style="bold")
    table.add_column("Summary", max_width=50)
    table.add_column("Source", style="dim")

    for sd in sorted(scored_deals, key=lambda x: x.total_score, reverse=True):
        # Color the priority
        if sd.priority == DealPriority.HIGH:
            priority = "[green]🔥 HIGH[/green]"
            score_style = "[bold green]"
        elif sd.priority == DealPriority.WORTH_WATCHING:
            priority = "[yellow]📌 WATCH[/yellow]"
            score_style = "[bold yellow]"
        else:
            priority = "[dim]🗑️ LOW[/dim]"
            score_style = "[dim]"

        table.add_row(
            sd.deal.startup_name,
            f"{score_style}{sd.total_score}/100[/]",
            priority,
            sd.summary[:50] + "…" if len(sd.summary) > 50 else sd.summary,
            sd.deal.source.value,
        )

    console.print(table)


async def run_pipeline(
    sources: Optional[list[str]] = None,
    dry_run: bool = False,
    limit: int = 20,
) -> list[ScoredDeal]:
    """
    Execute the full deal flow pipeline:
    1. Source  — pull deals from configured sources
    2. Enrich — website signals + GitHub metrics + founder data
    3. Score  — Gemini AI scorecard (0-100)
    4. Filter — threshold at ≥ SCORE_THRESHOLD
    5. Notify — post high-scoring deals to Slack
    6. Store  — persist all deals + scores to SQLite
    """
    Config.ensure_dirs()
    db = DealDatabase(Config.DB_PATH)

    try:
        # --- 1. SOURCE ---
        active_sources = sources or list(SOURCE_MAP.keys())
        console.print(
            f"\n[bold blue]📡 Sourcing from:[/] {', '.join(active_sources)}"
        )

        all_deals: list[Deal] = []
        for name in active_sources:
            if name not in SOURCE_MAP:
                console.print(f"[yellow]⚠ Unknown source: {name}[/]")
                continue

            console.print(f"  → Scraping {name}…", end=" ")
            try:
                deals = await SOURCE_MAP[name](limit=limit)
                console.print(f"[green]{len(deals)} deals found[/]")
                all_deals.extend(deals)
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")

        # Deduplicate
        all_deals = await _deduplicate(all_deals)
        console.print(f"\n[bold]📋 {len(all_deals)} unique deals after dedup[/]")

        if not all_deals:
            console.print("[yellow]No deals found. Try different sources.[/]")
            return []

        # --- 2. ENRICH ---
        console.print("\n[bold blue]🔍 Enriching deals…[/]")
        enriched: list[Deal] = []
        for deal in all_deals:
            try:
                deal = await _enrich_deal(deal)
            except Exception as e:
                console.print(f"  [yellow]⚠ Enrichment failed for {deal.startup_name}: {e}[/]")
            enriched.append(deal)

        # --- 3. SCORE ---
        console.print(f"\n[bold blue]🤖 Scoring {len(enriched)} deals with Gemini…[/]")
        scored: list[ScoredDeal] = []
        for i, deal in enumerate(enriched, 1):
            console.print(f"  [{i}/{len(enriched)}] {deal.startup_name}…", end=" ")
            try:
                result = await score_deal(deal)
                scored.append(result)
                console.print(f"[bold]{result.total_score}/100[/]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")

        # --- 4. FILTER & DISPLAY ---
        threshold = Config.SCORE_THRESHOLD
        high_priority = [s for s in scored if s.total_score >= threshold]
        _print_results_table(scored)

        console.print(
            f"\n[bold green]✅ {len(high_priority)} deals passed threshold "
            f"(≥{threshold})[/] of {len(scored)} scored"
        )

        # --- 5. NOTIFY ---
        if high_priority and not dry_run:
            console.print(f"\n[bold blue]📢 Posting {len(high_priority)} deals to Slack…[/]")
            for sd in high_priority:
                try:
                    await post_deal_to_slack(sd, dry_run=dry_run)
                    console.print(f"  ✓ {sd.deal.startup_name}")
                except Exception as e:
                    console.print(f"  [red]✗ {sd.deal.startup_name}: {e}[/]")
        elif high_priority and dry_run:
            console.print("\n[bold yellow]🏃 Dry run — Slack messages:[/]")
            for sd in high_priority:
                text = await post_deal_to_slack(sd, dry_run=True)
                console.print(f"\n{'─' * 60}")
                console.print(text)

        # --- 6. STORE ---
        console.print(f"\n[bold blue]💾 Storing {len(scored)} scored deals…[/]")
        for sd in scored:
            deal_id = db.save_deal(sd.deal)
            db.save_scored_deal(deal_id, sd)

        console.print("[bold green]✅ Pipeline complete![/]\n")
        return scored

    finally:
        db.close()
