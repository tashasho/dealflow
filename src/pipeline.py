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
from src.enrichment.crunchbase import enrich_crunchbase
from src.enrichment.apollo import enrich_contacts
from src.storage.airtable import sync_to_airtable
from src.models import Deal, DealPriority, ScoredDeal
from src.notifications.slack import post_deal_to_slack
from src.scoring.scorer import score_deal
from src.sourcing.github_trending import source_github
from src.sourcing.github_search import source_github_search
from src.sourcing.huggingface import source_huggingface
from src.sourcing.product_hunt import source_product_hunt
from src.sourcing.yc_batch import source_yc
from src.sourcing.arxiv import source_arxiv
from src.sourcing.linkedin import source_linkedin
from src.sourcing.twitter import source_twitter
from src.sourcing.hacker_news import source_hacker_news
from src.sourcing.hn_frontpage import source_hn_frontpage
from src.sourcing.reddit import source_reddit
from src.sourcing.rss import source_rss
from src.sourcing.indie_hackers import (
    source_indie_hackers,
    source_betalist,
    source_dev_to,
)
from src.storage.db import DealDatabase

console = Console()

# Map source names to functions
SOURCE_MAP = {
    "github": source_github,
    "github_search": source_github_search,
    "product_hunt": source_product_hunt,
    "yc": source_yc,
    "huggingface": source_huggingface,
    "arxiv": source_arxiv,
    "linkedin": source_linkedin,
    "twitter": source_twitter,
    "hacker_news": source_hacker_news,
    "hn_frontpage": source_hn_frontpage,
    "reddit": source_reddit,
    "rss": source_rss,
    "indie_hackers": source_indie_hackers,
    "betalist": source_betalist,
    "dev_to": source_dev_to,
}


async def _deduplicate(deals: list[Deal]) -> list[Deal]:
    """
    Remove duplicates by startup name or source URL.
    Prioritizes retaining the version with more info (e.g. description length).
    """
    unique_map: dict[str, Deal] = {}
    
    for deal in deals:
        # Create a composite key or try multiple keys
        # 1. Source URL (strongest signal if same source)
        # 2. Startup Name (normalized)
        
        keys = []
        if deal.source_url:
            keys.append(deal.source_url)
        
        name_key = deal.startup_name.lower().strip()
        keys.append(name_key)
        
        # Check if we've seen this deal
        existing = None
        used_key = None
        for k in keys:
            if k in unique_map:
                existing = unique_map[k]
                used_key = k
                break
        
        if existing:
            # Merge logic: keep the one with longer description or more founders
            if len(deal.description) > len(existing.description):
                unique_map[used_key] = deal
                # Update other keys to point to this new deal
                for k in keys:
                    unique_map[k] = deal
        else:
            # Add to map for all keys
            for k in keys:
                unique_map[k] = deal
                
    # Return unique values
    return list({id(d): d for d in unique_map.values()}.values())


async def _enrich_deal(deal: Deal) -> Deal:
    """Enrich a single deal with website signals, GitHub metrics, founder data, and external APIs."""
    # Website signals
    if deal.website and not deal.website_signals:
        deal.website_signals = await extract_website_signals(deal.website)

    # GitHub metrics
    if deal.github and deal.github.repo_url and deal.github.stars == 0:
        enriched = await enrich_github_metrics(deal.github.repo_url)
        if enriched:
            deal.github = enriched

    # Crunchbase (Funding check)
    if deal.website:
        deal = await enrich_crunchbase(deal)

    # Founder enrichment (Apollo/Hunter)
    if deal.founders:
        deal = await enrich_contacts(deal)
        # Fallback to existing logic if needed, but let's assume enrich_contacts handles it
        # deal.founders = await enrich_founders(deal.founders) 
        # (Existing enrich_founders might be a placeholder or duplicate, keeping as comment for now)

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

        # In-batch dedupe (same name appearing in multiple sources this run)
        all_deals = await _deduplicate(all_deals)
        console.print(f"\n[bold]📋 {len(all_deals)} unique deals after intra-batch dedup[/]")

        # Cross-run dedupe: skip anything already saved in past runs
        before = len(all_deals)
        fresh_deals = [d for d in all_deals if not db.has_been_seen(d)]
        skipped = before - len(fresh_deals)
        if skipped:
            console.print(f"[dim]  (skipped {skipped} deals already seen in prior runs)[/]")

        # --- 2. ENRICH ---
        scored: list[ScoredDeal] = []
        scored_ids: list[int] = []  # parallel to `scored`, holds scored_deals.id

        if fresh_deals:
            console.print("\n[bold blue]🔍 Enriching deals…[/]")
            enriched: list[Deal] = []
            for deal in fresh_deals:
                try:
                    deal = await _enrich_deal(deal)
                except Exception as e:
                    console.print(f"  [yellow]⚠ Enrichment failed for {deal.startup_name}: {e}[/]")
                enriched.append(deal)

            # --- 3. SCORE ---
            console.print(f"\n[bold blue]🤖 Scoring {len(enriched)} deals…[/]")
            for i, deal in enumerate(enriched, 1):
                console.print(f"  [{i}/{len(enriched)}] {deal.startup_name}…", end=" ")
                try:
                    result = await score_deal(deal)
                    scored.append(result)
                    console.print(f"[bold]{result.total_score}/100[/]")
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]")

            # --- 4. STORE (early so dedup state captures everything we scored) ---
            console.print(f"\n[bold blue]💾 Storing {len(scored)} scored deals…[/]")
            for sd in scored:
                deal_id = db.save_deal(sd.deal)
                sd_row_id = db.save_scored_deal(deal_id, sd)
                scored_ids.append(sd_row_id)
        else:
            console.print("[yellow]All sourced deals are already in DB.[/]")

        # --- 5. PICK WHAT TO POST ---
        threshold = Config.SCORE_THRESHOLD
        # Filter the just-scored to those above threshold AND never posted before
        # (has_been_seen + immediate save above means we re-query has_been_posted on Deal).
        to_post: list[tuple[int, ScoredDeal]] = [
            (sd_id, sd)
            for sd_id, sd in zip(scored_ids, scored)
            if sd.total_score >= threshold and not db.has_been_posted(sd.deal)
        ]

        if scored:
            _print_results_table(scored)
            console.print(
                f"\n[bold green]✅ {len(to_post)} deals passed threshold "
                f"(≥{threshold}) and are unposted[/] of {len(scored)} scored"
            )

        # Fallback — if nothing fresh meets the bar, surface top unposted from past runs
        if not to_post:
            console.print(
                "\n[yellow]No fresh picks today — pulling top unposted from past runs[/]"
            )
            backfill_n = max(3, Config.SCORE_THRESHOLD // 10)  # ~3-8 items
            to_post = db.get_top_unposted(limit=backfill_n, min_score=0)
            if not to_post:
                console.print("[dim]Nothing in the backlog either. Channel stays quiet today.[/]")

        # --- 6. NOTIFY ---
        if to_post and not dry_run:
            console.print(f"\n[bold blue]📢 Posting {len(to_post)} deals to Slack…[/]")
            for sd_id, sd in to_post:
                try:
                    await post_deal_to_slack(sd, dry_run=dry_run)
                    db.mark_posted(sd_id)
                    console.print(f"  ✓ {sd.deal.startup_name}")
                except Exception as e:
                    console.print(f"  [red]✗ {sd.deal.startup_name}: {e}[/]")
        elif to_post and dry_run:
            console.print("\n[bold yellow]🏃 Dry run — Slack messages:[/]")
            for _sd_id, sd in to_post:
                text = await post_deal_to_slack(sd, dry_run=True)
                console.print(f"\n{'─' * 60}")
                console.print(text)

        # Sync to Airtable (only if scored anything new this run)
        if scored and not dry_run:
            console.print(f"  → Syncing to Airtable…")
            await sync_to_airtable(scored)

        console.print("[bold green]✅ Pipeline complete![/]\n")
        return scored

    finally:
        db.close()
